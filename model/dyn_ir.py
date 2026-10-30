"""
Dynamic blind reconciliation: the firmware-side rate controller (golden model) on top of the IR core.

The IR core itself is unchanged by "dynamic" mode: it still decodes one attempt at a time and reports
converged / n_usc / ERRCNT. What changes is how the CPU drives it:

  basic   : code from a fixed QBER table, every attempt starts with all of D punctured (r0 = 0),
            reveal step = d / 4 after each failure.
  dynamic : 1) QBER estimate: PE sample (PE_SAMPLE bits) fused with the exact QBER of earlier blocks (ERRCNT)
               when both agree, PE sample alone after a level jump; upper confidence bound of that estimate.
            2) target rate R* = 1 - f_adj * h(q), f_adj self-tuning from the attempt counts.
            3) code = the mother code whose window [R_min, R_max] contains R* with the most shortening
               (highest R0); r0 = number of D bits Alice reveals together with the syndrome so that the
               first attempt runs at R*  (no extra round trip: the reveals travel with the syndrome; RTL: HOLD).
            4) after a failure, reveal delta = clamp(alpha * n_usc, delta_min, remaining) bits.
            5) early discard above q_abort (no decoder time spent on blocks that cannot give a secret key).
  both    : D = puncture.order(code) (grouping & sorting, reveal hardest first) when gs=True, else random.

leak = m - d + (all revealed bits), f = leak / ((n - d) h(Q_block)).

Every decode uses ir_model.decode_attempt, i.e. exactly what the RTL computes.
"""
import math

import numpy as np

import ir_model as m
import layer_sched
import pa_model as pa
import puncture as pu

ZC = 128
N = m.NCOL * ZC
DELTA = 0.10
D = int(round(DELTA * N))
NKEY = N - D

# core configuration used in every attempt (CFG / CFG2)
ITER_MAX = 50
PP = (1, 2, 16)          # pp_rounds, pp_min_usc, pp_max_usc
ET = 12                  # early-termination patience

# timing model: decoder cycles per iteration per code and layer schedule (layer_sched.py, RTL sim matches within
# the ~30-cycle load), per-attempt overhead (load, USC pass, key output) and classical-channel round trip
CYC_ATTEMPT = 300


def cyc_per_it(codes, schedule):
    """overlap (RTL since 2026-10-11): sum (2 deg + 5) + 7; serial (2026-10-10): 2 E + 12 mb."""
    return {n: layer_sched.iteration_cycles(b, schedule) for n, b in codes.items()}


CYC_PER_IT = {s: cyc_per_it(m.load_codes(ZC), s) for s in ("overlap", "serial")}


def code_window(name):
    mb = m.CODE_MB[name]
    m_bits = mb * ZC
    r_max = 1 - (m_bits - D) / NKEY
    r_min = 1 - m_bits / NKEY
    return r_min, r_max


def basic_code(q):
    """Fixed table used by the basic mode (same thresholds as eval_csv.pick_code)."""
    if q <= 0.008:
        return "r56"
    if q <= 0.022:
        return "r34"
    if q <= 0.045:
        return "r23"
    return "r12"


class Controller:
    """Firmware policy. mode = 'basic' or 'dynamic'.

    Both modes get the same per-block QBER estimate q_pe from parameter estimation (PE: Alice and Bob compare a
    random sample of PE_SAMPLE bits of the block, as every BB84 stack does).
      basic   : code = basic_code(q_pe), r0 = 0, reveal step d/4, never discards early.
      dynamic : q_use = q_pe + PE_Z * sigma (upper confidence bound), target rate R* = 1 - f_adj * h(q_use),
                code = window containing R* with the most shortening, r0 bits revealed with the syndrome,
                reveal delta after a failure = clamp(alpha * n_usc, delta_min, remaining),
                early discard when q_pe > q_abort (no secret key above ~11 % QBER for BB84),
                a code is only used if it keeps room for reveals: with f_safe set, R_min (all of D revealed)
                must reach 1 - f_safe * h(q_use), i.e. the block can still be rescued up to f = f_safe
                (f_safe = None: old rule R* >= R_min + win_margin, which failed blocks at 2-5 % QBER),
                f_adj self-tunes: x F_DOWN after a first-attempt success, x F_UP after any failed attempt.
    ERRCNT of each successful block (exact QBER) feeds q_ewma, reported for monitoring / PE calibration.
    """

    def __init__(self, mode="dynamic", f_target=1.15, alpha=1.0, delta_min=16, pe_z=1.0, q_abort=0.11,
                 f_min=1.05, f_max=1.8, f_down=0.98, f_up=1.04, lam=0.5, basic_step=None, win_margin=0.03,
                 fuse=False, fuse_k=2.0, f_safe=None, abort_basic=False, basic_z=0.0, schedule="overlap"):
        self.mode = mode
        self.f_adj = f_target
        self.alpha = alpha
        self.delta_min = delta_min
        self.pe_z = pe_z
        self.q_abort = q_abort
        self.f_min, self.f_max, self.f_down, self.f_up = f_min, f_max, f_down, f_up
        self.lam = lam
        self.win_margin = win_margin        # R* must sit at least this far above the window bottom (reveal room)
        self.f_safe = f_safe                # rescue room: R_min <= 1 - f_safe h(q_use) (overrides win_margin)
        self.abort_basic = abort_basic      # basic mode also discards early above q_abort (no secret key there)
        self.basic_z = basic_z              # basic mode picks its code from q_pe + basic_z * sigma (0: point)
        self.schedule = schedule            # decoder layer schedule for the timing model ("serial": 2026-10-10)
        self.q_ewma = None
        self.n_ewma = 0                     # bits behind q_ewma (for its standard deviation)
        self.fuse = fuse                    # use ERRCNT history in the QBER estimate
        self.fuse_k = fuse_k                # PE and history agree when |q_pe - q_ewma| <= fuse_k * sigma
        self.basic_step = basic_step or -(-D // 4)

    def estimate(self, q_pe, n_pe):
        """(q, sigma) used for the code choice. History = exact QBER of the last successful blocks (ERRCNT)."""
        sig_pe = math.sqrt(max(q_pe, 1.0 / n_pe) * (1 - q_pe) / n_pe)
        if not self.fuse or self.q_ewma is None:
            return q_pe, sig_pe
        sig_h = math.sqrt(max(self.q_ewma, 1.0 / self.n_ewma) * (1 - self.q_ewma) / self.n_ewma)
        if abs(q_pe - self.q_ewma) > self.fuse_k * math.hypot(sig_pe, sig_h):
            return q_pe, sig_pe                                  # level jump: trust the fresh sample only
        w_pe, w_h = 1 / sig_pe ** 2, 1 / sig_h ** 2              # inverse-variance weighting
        q = (w_pe * q_pe + w_h * self.q_ewma) / (w_pe + w_h)
        return q, math.sqrt(1 / (w_pe + w_h))

    # -- block start ------------------------------------------------------------------------------
    def plan(self, q_pe, n_pe):
        """Returns (code name, r0) or (None, 0) for an early discard."""
        if self.mode == "basic":
            if self.abort_basic and q_pe > self.q_abort:
                return None, 0
            sig = math.sqrt(max(q_pe, 1.0 / n_pe) * (1 - q_pe) / n_pe)
            return basic_code(q_pe + self.basic_z * sig), 0
        if q_pe > self.q_abort:                              # point estimate: do not drop blocks on PE noise
            return None, 0
        q_hat, sig = self.estimate(q_pe, n_pe)
        q_use = q_hat + self.pe_z * sig
        r_star = 1 - self.f_adj * m.h2(q_use)
        best = None
        for name in reversed(m.CODE_ORDER):                  # r56 first: most shortening wins
            r_min, r_max = code_window(name)
            if self.f_safe is not None:
                room = r_min <= 1 - self.f_safe * m.h2(q_use)
                if room and r_star >= r_min:
                    best = name                              # R* > R_max: start at R_max (r0 = 0)
                    break
            elif r_min + self.win_margin <= r_star <= r_max:
                best = name
                break
        if best is None:
            best = "r56" if r_star > code_window("r56")[1] else "r12"
        mb = m.CODE_MB[best]
        r0 = math.ceil(NKEY * (1 - r_star) - (mb * ZC - D))
        return best, int(min(D, max(0, r0)))

    # -- after a failed attempt -------------------------------------------------------------------
    def next_reveal(self, n_usc, remaining):
        if self.mode == "basic":
            return min(self.basic_step, remaining)
        return int(min(remaining, max(self.delta_min, round(self.alpha * n_usc))))

    # -- block end --------------------------------------------------------------------------------
    def update(self, success, errcnt, attempts):
        if success:
            q_meas = errcnt / NKEY
            self.q_ewma = q_meas if self.q_ewma is None else (1 - self.lam) * self.q_ewma + self.lam * q_meas
            # effective sample size of the EWMA: n / (lam / (2 - lam)) bits
            self.n_ewma = int(NKEY * (2 - self.lam) / self.lam)
        if self.mode == "dynamic" and attempts > 0:
            if success and attempts == 1:
                self.f_adj = max(self.f_min, self.f_adj * self.f_down)
            else:
                self.f_adj = min(self.f_max, self.f_adj * self.f_up ** (attempts - 1 if success else attempts))


def prepare_block(alice, bob, seed, pos_d=None):
    """Channel / syndrome data of one block. pos_d: D in reveal order (puncture.order), None = random."""
    rng = np.random.default_rng(seed)
    pos_d = rng.choice(N, D, replace=False) if pos_d is None else np.asarray(pos_d)
    key_pos = np.setdiff1d(np.arange(N), pos_d)
    v = np.zeros(N, dtype=np.int64)
    v[key_pos] = alice
    v[pos_d] = rng.integers(0, 2, D)
    ch_bit = np.zeros(N, dtype=np.int64)
    ch_bit[key_pos] = bob
    return {"pos_d": pos_d, "key_pos": key_pos, "v": v, "ch_bit": ch_bit, "alice": alice, "bob": bob}


def run_block(blk, codes, name, r0, ctrl, collect_vectors=False):
    """One block: initial reveals r0, then attempts until success or D exhausted. Returns a result dict."""
    base = codes[name]
    pos_d, key_pos, v = blk["pos_d"], blk["key_pos"], blk["v"]
    ch_type = np.zeros((1, N), dtype=np.int64)
    ch_type[0, pos_d] = m.T_PUNCT
    ch_bit = blk["ch_bit"].reshape(1, N).copy()
    syn = m.syndrome(base, v.reshape(1, m.NCOL, ZC), ZC)
    sym0 = np.where(ch_type[0] == m.T_PUNCT, 2, ch_bit[0])        # what the DMA streams (before reveals)

    revs, trace = [], []
    r = 0

    def reveal(cnt):
        nonlocal r
        nxt = pos_d[r:r + cnt]
        r += len(nxt)
        ch_type[0, nxt] = m.T_SHORT
        ch_bit[0, nxt] = v[nxt]
        revs.extend(int(p) | (int(v[p]) << 16) for p in nxt)
        return len(nxt)

    pre = reveal(r0) if r0 else 0
    cycles = 0
    while True:
        res = m.decode_attempt(ch_type, ch_bit, syn, base, ZC, ITER_MAX, m.LQ_DEFAULT, *PP, ET)
        ch_type = res["ch_type"]
        conv = bool(res["conv"][0])
        it = int(res["iters"][0])
        cycles += it * CYC_PER_IT[ctrl.schedule][name] + CYC_ATTEMPT * int(res["decodes"][0])
        trace.append({"conv": conv, "pp": int(res["decodes"][0] - 1), "usc": int(res["n_usc"][0]),
                      "iters": it, "nrev": 0})
        if conv or r >= D:
            break
        trace[-1]["nrev"] = reveal(ctrl.next_reveal(int(res["n_usc"][0]), D - r))

    hard = res["hard"][0]
    resid = int((hard[key_pos] != blk["alice"]).sum())
    success = conv and resid == 0
    errcnt = int((hard[key_pos] != blk["bob"]).sum()) if conv else 0
    q_blk = float((blk["alice"] != blk["bob"]).mean())
    leak = m.CODE_MB[name] * ZC - D + r
    hq = m.h2(q_blk)
    out = {"code": name, "r0": r0, "pre": pre, "success": success, "undetected": conv and resid > 0,
           "resid": resid, "attempts": len(trace), "revealed": r, "leak": leak, "rate": 1 - leak / NKEY,
           "f": leak / (NKEY * hq) if (success and hq > 0) else float("nan"), "iters": sum(t["iters"] for t in trace),
           "cycles": cycles, "errcnt": errcnt, "q_block": q_blk, "trace": trace}
    if collect_vectors:
        out.update({"revs": revs, "sym": sym0, "syn": syn[0], "hard": hard, "pre_revs": pre})
    return out


PE_SAMPLE = 256          # bits compared in parameter estimation (modelled as a sample of the block)


def simulate(sequence, mode, seed0=1000, collect_vectors=False, gs=True, cn=None, **ctrl_kw):
    """sequence: list of (alice, bob) arrays of NKEY bits, in time order. Returns list of per-block results.
    gs: punctured positions from puncture.order (grouping & sorting) instead of random.
    cn: check-node correction for this run (ir_model.CN_MODE: "oms" / "nms75" ...), None = current setting."""
    if cn is not None:
        saved, m.CN_MODE = m.CN_MODE, cn
        try:
            return simulate(sequence, mode, seed0, collect_vectors, gs, None, **ctrl_kw)
        finally:
            m.CN_MODE = saved
    codes = m.load_codes(ZC)
    ctrl = Controller(mode=mode, **ctrl_kw)
    return [one_block(b, item[0], item[1], ctrl, codes, gs, seed0, collect_vectors, item[2] if len(item) > 2 else None)
            for b, item in enumerate(sequence)]


def one_block(b, alice, bob, ctrl, codes, gs=True, seed0=1000, collect_vectors=False, pe=None):
    """PE, plan, reconcile and controller update of block number b.
    pe = (q_est, n_est): QBER estimate supplied by the caller, e.g. from the public test-basis (X) bits of the same
    time window (decoy BB84 sessions, eval_sessions.py); no key bit is disclosed then. None: PE_SAMPLE bits of the
    block itself are compared (synthetic sequences; strictly these bits would have to be removed from the key)."""
    if pe is None:
        rng = np.random.default_rng(seed0 + 7919 * b)
        pe_idx = rng.choice(len(alice), PE_SAMPLE, replace=False)
        q_pe = float((alice[pe_idx] != bob[pe_idx]).mean())
        n_pe = PE_SAMPLE
    else:
        q_pe, n_pe = float(pe[0]), int(max(pe[1], 1))
    name, r0 = ctrl.plan(q_pe, n_pe)
    q_blk = float((alice != bob).mean())
    if name is None:                                         # early discard: no decoder time, no leakage
        res = {"code": "-", "r0": 0, "pre": 0, "success": False, "undetected": False, "resid": 0, "attempts": 0,
               "revealed": 0, "leak": 0, "rate": float("nan"), "f": float("nan"), "iters": 0, "cycles": 0,
               "errcnt": 0, "q_block": q_blk, "trace": []}
    else:
        blk = prepare_block(alice, bob, seed0 + b, pu.order(name, codes[name], ZC, D) if gs else None)
        res = run_block(blk, codes, name, r0, ctrl, collect_vectors)
    res["q_pe"] = q_pe
    res["f_adj"] = ctrl.f_adj
    ctrl.update(res["success"], res["errcnt"], res["attempts"])
    return res


# ------------------------------------------------------------------------------------------------------------
# Two operating profiles + backlog-driven switching (2026-10-11, results/exp_mode.txt, exp_adaptive.txt)
#
#   efficiency : basic blind (all of D punctured, reveal d/4), GS positions, NMS, early discard above q_abort
#                (11 %, on the PE point estimate). Highest secret bits per sifted
#                bit (eta 0.481 vs 0.464 basic / 0.429 dynamic of 10-10) and still 11.5 Mbit/s IR capacity at
#                RTT 100 us. Best whenever the IR keeps up with the raw key (alpha = 1 in Kprac).
#   throughput : dynamic controller, GS, NMS, rescue-room code choice f_safe 1.7, PE bound z 1.5, f* 1.3.
#                ~1.06 attempts / block: 21.6 Mbit/s IR capacity, 8.4 Mbit/s secret at saturation.
#   switching  : by the number of sifted blocks waiting when a block starts (hysteresis):
#                backlog >= BACKLOG_HI -> throughput, backlog <= BACKLOG_LO -> efficiency.
# ------------------------------------------------------------------------------------------------------------
PROFILES = {
    "efficiency": ("basic", dict(gs=True, cn="nms75", abort_basic=True)),
    "throughput": ("dynamic", dict(gs=True, cn="nms75", f_safe=1.7, pe_z=1.5, f_target=1.3)),
}
BACKLOG_HI = 4
BACKLOG_LO = 1


def simulate_queue(sequence, raw_mbps, policy="adaptive", rtt_us=100.0, clk_mhz=100.0, hi=BACKLOG_HI,
                   lo=BACKLOG_LO, seed0=1000, profiles=None):
    """Blocks of NKEY sifted bits arrive every NKEY / raw_mbps us; the IR core processes them in order.
    policy: "adaptive" (backlog switching) or a profile name (fixed). Each profile keeps its own controller state.
    Returns dict(secret Mbit/s over the whole run, eta, share of blocks in throughput mode, results)."""
    profiles = profiles or PROFILES
    codes = m.load_codes(ZC)
    ctrls, kws = {}, {}
    for p, (mode, kw) in profiles.items():
        kw = dict(kw)
        kws[p] = (kw.pop("gs", True), kw.pop("cn", None))
        ctrls[p] = Controller(mode=mode, **kw)
    t_blk = NKEY / raw_mbps
    arr = [b * t_blk for b in range(len(sequence))]
    t, prof, out, in_tp = 0.0, ("efficiency" if policy == "adaptive" else policy), [], 0
    saved = m.CN_MODE
    try:
        for b, (alice, bob) in enumerate(sequence):
            start = max(t, arr[b])
            backlog = sum(1 for a in arr[b + 1:] if a <= start)
            if policy == "adaptive":
                if backlog >= hi:
                    prof = "throughput"
                elif backlog <= lo:
                    prof = "efficiency"
            gs, cn = kws[prof]
            if cn is not None:
                m.CN_MODE = cn
            res = one_block(b, alice, bob, ctrls[prof], codes, gs, seed0)
            res["profile"] = prof
            in_tp += prof == "throughput"
            t = start + res["cycles"] / clk_mhz + rtt_us * res["attempts"]
            out.append(res)
    finally:
        m.CN_MODE = saved
    total = max(t, arr[-1] + t_blk)
    secret = sum(NKEY * secret_fraction(r["q_block"], r["f"]) for r in out if r["success"])
    return {"skr": secret / total, "eta": secret / (NKEY * len(out)), "tp_share": in_tp / len(out),
            "ok": sum(r["success"] for r in out), "results": out}


def secret_fraction(q, f, n_pa=1_000_000):
    """Finite-size secret fraction of a PA block of n_pa reconciled bits at QBER q with reconciliation
    efficiency f (PE sample n_pa / 10), pa_model.secure_length. Used for the secret-key-rate figure of merit."""
    q = max(q, 1e-4)
    ell, _ = pa.secure_length(n_pa, q, int(f * m.h2(q) * n_pa), n_pa // 10)
    return ell / n_pa


def summarize(results, rtt_us=(0.0, 100.0, 1000.0), clk_mhz=100.0):
    """Reconciled-key throughput (Mbit/s, thr_*) and secret-key throughput (skr_*: Kprac of Yang et al. 2020 for
    DV-QKD = reconciled bits x finite-size secret fraction of each block / processing time)."""
    ok = [r for r in results if r["success"]]
    s = {"blocks": len(results), "success": len(ok),
         "f": float(np.mean([r["f"] for r in ok])) if ok else float("nan"),
         "attempts": float(np.mean([r["attempts"] for r in results])),
         "iters": float(np.mean([r["iters"] for r in results])),
         "net_bits": sum(NKEY - r["leak"] for r in ok),
         "secret_bits": sum(NKEY * secret_fraction(r["q_block"], r["f"]) for r in ok)}
    # eta: secret bits per sifted key bit offered to IR (failed and discarded blocks count as 0) - the figure
    # of merit when the post-processor is NOT the bottleneck (raw key rate < IR capacity, alpha = 1 in Kprac)
    s["eta"] = s["secret_bits"] / (NKEY * len(results)) if results else float("nan")
    dec_us = sum(r["cycles"] for r in results) / clk_mhz
    for rtt in rtt_us:
        t = dec_us + rtt * sum(r["attempts"] for r in results)       # one round trip per attempt (syndrome / reveals)
        s[f"thr_{int(rtt)}us"] = sum(NKEY for _ in ok) / t if t else float("nan")   # Mbit/s of reconciled key
        s[f"skr_{int(rtt)}us"] = s["secret_bits"] / t if t else float("nan")        # Mbit/s of secret key
    return s
