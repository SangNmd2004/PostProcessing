"""
Golden model of the information-reconciliation (IR) core: basic blind reconciliation on a QC-LDPC mother
code, layered offset min-sum decoder, trapping-set post-processing.

Everything the RTL in ../rtl/ldpc does is defined here first (fixed point, layer order, convergence rule).

Protocol, one block (Martinez-Mateo, Elkouss, Martin 2012):
  * Mother code: n = 24 * ZC, m = mb * ZC syndrome bits, R0 = 1 - mb/24. H is fixed.
  * d = round(delta * n) modulated positions D (shared). Alice's key x fills the other n - d positions and D is
    filled with Alice's private random bits. Alice sends the syndrome s = H v once (m bits).
  * Attempt 0: all of D punctured (LLR 0). After each failure Alice reveals the next `step` bits of D
    (shortened: value known, APP frozen at +-63). After the last failure the block is discarded.
  * leak = m - d + revealed,  f = leak / ((n - d) h(Q)).

Channel word per variable node (3 bit, CH-RAM in the RTL): type (0 key bit, 1 punctured, 2 shortened) + bit.
  key bit    -> APP0 = bit ? -LQ : +LQ
  punctured  -> APP0 = 0
  shortened  -> APP0 = bit ? -63 : +63 and every APP write of that node is forced to the same value (frozen)

Decoder (same datapath as the 2026-10 rtl/ldpc_opt decoder, extended):
  APP 7 bit (+63/-64), C2V 6 bit, V2C 8 bit, offset 3 (it<10) / 2 (it<30) / 1.
  Convergence (strict): every layer's parity matches the syndrome AND no APP sign changed during the iteration.
  (The old rule - per-layer parity only - reported false convergence.)

Trapping-set post-processing (pp="flip"): when a decode fails, compute the unsatisfied checks (USC) of the final
hard decision, count for every key-bit node how many USCs it touches, invert the channel sign of the nodes with
count >= PP_MIN_USC and decode again (at most PP_ROUNDS times) before asking Alice for more bits.
"""
import argparse
import csv
import json
import math
import os
import sys

import numpy as np

NCOL = 24
APP_MAX, APP_MIN = 62, -62     # APP 7 bit; +-63 are reserved for frozen (shortened) nodes, -64 is unused
APP_FROZEN = 63
V2C_FROZEN = 127               # V2C of a frozen node (never produced by v2c = app - c2v, |.| <= 94)
C2V_MAX, C2V_MIN = 31, -32
LQ_DEFAULT = 8
T_KEY, T_PUNCT, T_SHORT, T_KEY_FLIP = 0, 1, 2, 3   # CH-RAM type field

HERE = os.path.dirname(os.path.abspath(__file__))
CODES_JSON = os.path.join(HERE, "codes.json")

# ----------------------------------------------------------------------------
# Mother codes
# ----------------------------------------------------------------------------
INFO_DEGREES = {
    12: [6] * 4 + [3] * 8,             # R0 = 1/2
    8:  [6] * 4 + [3] * 12,            # R0 = 2/3
    6:  [6] * 2 + [4] * 4 + [3] * 12,  # R0 = 3/4
    4:  [4] * 4 + [3] * 16,            # R0 = 5/6
}
CODE_MB = {"r12": 12, "r23": 8, "r34": 6, "r56": 4}
CODE_ORDER = ["r12", "r23", "r34", "r56"]


def _closes_4cycle(base, zc, r, c, s):
    for c2 in range(NCOL):
        if c2 == c or base[r][c2] < 0:
            continue
        for r2 in range(len(base)):
            if r2 != r and base[r2][c] >= 0 and base[r2][c2] >= 0:
                if (s - base[r][c2] + base[r2][c2] - base[r2][c]) % zc == 0:
                    return True
    return False


def _closes_6cycle(base, zc, r, c, s):
    mb = len(base)
    for r2 in range(mb):
        if r2 == r or base[r2][c] < 0:
            continue
        for c2 in range(NCOL):
            if c2 == c or base[r2][c2] < 0:
                continue
            for r3 in range(mb):
                if r3 in (r, r2) or base[r3][c2] < 0:
                    continue
                for c3 in range(NCOL):
                    if c3 in (c, c2) or base[r3][c3] < 0 or base[r][c3] < 0:
                        continue
                    if (s - base[r2][c] + base[r2][c2] - base[r3][c2] + base[r3][c3] - base[r][c3]) % zc == 0:
                        return True
    return False


def make_base(mb, zc, seed=1, tries=400):
    """Pseudo-random QC base matrix mb x 24. Shifts avoid 4-cycles always and 6-cycles when possible."""
    rng = np.random.default_rng(seed)
    kb = NCOL - mb
    base = [[-1] * NCOL for _ in range(mb)]
    base[0][kb] = 1
    base[mb // 2][kb] = 0
    base[mb - 1][kb] = 1
    for i in range(1, mb):
        base[i - 1][kb + i] = 0
        base[i][kb + i] = 0
    row_deg = [sum(1 for v in row if v >= 0) for row in base]
    n6 = 0
    for c, deg in enumerate(INFO_DEGREES[mb]):
        rows = sorted(range(mb), key=lambda r: (row_deg[r], rng.random()))[:deg]
        for r in rows:
            fallback = None
            for _ in range(tries):
                s = int(rng.integers(0, zc))
                if _closes_4cycle(base, zc, r, c, s):
                    continue
                if fallback is None:
                    fallback = s
                if not _closes_6cycle(base, zc, r, c, s):
                    break
            else:
                if fallback is None:
                    raise RuntimeError(f"no 4-cycle-free shift for ({r},{c})")
                s = fallback
                n6 += 1
            base[r][c] = s
            row_deg[r] += 1
    return base, n6


def build_codes(zc, seed=1):
    codes = {}
    for name in CODE_ORDER:
        base, n6 = make_base(CODE_MB[name], zc, seed)
        codes[name] = {"zc": zc, "base": base, "entries_with_6cycles": n6}
    return codes


def load_codes(zc, regenerate=False):
    """Codes are generated once per ZC and stored in codes.json so the RTL ROM uses the same matrices."""
    allc = {}
    if os.path.exists(CODES_JSON):
        with open(CODES_JSON) as fh:
            allc = json.load(fh)
    key = str(zc)
    if regenerate or key not in allc:
        allc[key] = build_codes(zc)
        with open(CODES_JSON, "w") as fh:
            json.dump(allc, fh, indent=1)
    return {k: v["base"] for k, v in allc[key].items()}


def edge_list(base):
    out, e = [], 0
    for row in base:
        es = []
        for c, s in enumerate(row):
            if s >= 0:
                es.append((e, c, s))
                e += 1
        out.append(es)
    return out, e


def syndrome(base, v, zc):
    """v: (B, 24, zc) bits -> (B, mb, zc). Check j of layer l sees bit (j + s) % zc of column c."""
    lanes = np.arange(zc)
    s = np.zeros((v.shape[0], len(base), zc), dtype=np.int64)
    for l, row in enumerate(base):
        for c, sh in enumerate(row):
            if sh >= 0:
                s[:, l] ^= v[:, c, (lanes + sh) % zc]
    return s


def vn_usc_count(base, usc, zc):
    """usc: (B, mb, zc) unsatisfied-check flags -> (B, 24, zc) number of USCs per variable node."""
    lanes = np.arange(zc)
    cnt = np.zeros((usc.shape[0], NCOL, zc), dtype=np.int64)
    for l, row in enumerate(base):
        for c, sh in enumerate(row):
            if sh >= 0:
                cnt[:, c, (lanes + sh) % zc] += usc[:, l]
    return cnt


# ----------------------------------------------------------------------------
# Decoder
# ----------------------------------------------------------------------------
def offset_of(it):
    return 3 if it < 10 else (2 if it < 30 else 1)


# Check-node magnitude correction (experiment switch, exp_cn.py). "oms": max(m - offset(it), 0) - what the RTL does.
# "nms75" / "nms81": normalized min-sum with alpha = 0.75 (m - m>>2) / 0.8125 (m - m>>2 + m>>4), floor, shift-add
# only. "nms75o1": alpha 0.75 then offset 1.
CN_MODE = "oms"


def cn_mag(mg, it):
    if CN_MODE == "oms":
        off = offset_of(it)
        return np.where(mg > off, mg - off, 0)
    if CN_MODE == "nms75":
        return mg - (mg >> 2)
    if CN_MODE == "nms81":
        return mg - (mg >> 2) + (mg >> 4)
    if CN_MODE == "nms75o1":
        s = mg - (mg >> 2)
        return np.where(s > 1, s - 1, 0)
    raise ValueError(CN_MODE)


def init_app(ch_type, ch_bit, lq):
    """ch_type/ch_bit: (B, 24, zc) -> initial APP (T_KEY_FLIP = key bit whose channel sign was inverted by PP)."""
    key = np.where(ch_bit == 0, lq, -lq)
    short = np.where(ch_bit == 0, APP_FROZEN, -APP_FROZEN)
    return np.select([ch_type == T_KEY, ch_type == T_KEY_FLIP, ch_type == T_SHORT], [key, -key, short], 0).astype(np.int64)


def decode_batch(app0, syn, base, zc, iter_max, strict=True, app_max=APP_MAX, app_min=APP_MIN, use_frozen=True,
                 et_patience=0):
    """app0: (B, 24, zc) initial APP, syn: (B, mb, zc). Returns (app, iters, converged).

    Early termination (et_patience > 0): every iteration counts the unsatisfied checks seen at READ time
    (parity of the hard decisions of each layer just before it is updated, summed over the layers; the RTL gets
    this from the same XOR it uses for the layer check). If that count has not improved on its best value for
    et_patience consecutive iterations, the decode stops as failed. 0 disables it.

    Frozen (shortened) nodes are marked by their APP value +-APP_FROZEN; their V2C is +-V2C_FROZEN and every
    write of such a node keeps +-APP_FROZEN. Other APPs saturate to [app_min, app_max].
    use_frozen=False, strict=False, app_max=63, app_min=-64 reproduces the 2026-10 rtl/ldpc_opt decoder."""
    edges, n_edges = edge_list(base)
    b = app0.shape[0]
    app = app0.astype(np.int64).copy()
    c2v = np.zeros((n_edges, b, zc), dtype=np.int64)
    lanes = np.arange(zc)
    active = np.ones(b, dtype=bool)
    iters = np.zeros(b, dtype=np.int64)
    conv = np.zeros(b, dtype=bool)
    best = np.full(b, 1 << 30, dtype=np.int64)     # early termination: best read-time unsatisfied count
    stall = np.zeros(b, dtype=np.int64)            # iterations since the last improvement
    it = 0
    while active.any() and it < iter_max:
        a = np.nonzero(active)[0]
        ok = np.ones(len(a), dtype=bool)
        unsat = np.zeros(len(a), dtype=np.int64)
        for l, es in enumerate(edges):
            ixs = [(lanes + s) % zc for (_, _, s) in es]
            v2c = []
            rpar = np.zeros((len(a), zc), dtype=np.int64)          # read-time parity of this layer
            for (e, c, _), ix in zip(es, ixs):
                ap = app[a, c][:, ix]
                rpar ^= (ap < 0).astype(np.int64)
                v = ap - (c2v[e][a] if it > 0 else 0)
                if use_frozen:
                    v = np.where(ap == APP_FROZEN, V2C_FROZEN, np.where(ap == -APP_FROZEN, -V2C_FROZEN, v))
                v2c.append(v)
            unsat += (rpar ^ syn[a, l]).sum(axis=1)
            v2c = np.stack(v2c)                                   # (deg, A, zc)
            mag = np.abs(v2c)
            sgn = (v2c < 0).astype(np.int64)
            order = np.argsort(mag, axis=0, kind="stable")
            idx = order[0]
            m1 = np.take_along_axis(mag, order[0:1], axis=0)[0]
            m2 = np.take_along_axis(mag, order[1:2], axis=0)[0]
            rsgn = (np.bitwise_xor.reduce(sgn, axis=0) ^ syn[a, l]) & 1
            m1s = cn_mag(m1, it)
            m2s = cn_mag(m2, it)
            parity = np.zeros((len(a), zc), dtype=np.int64)
            flipped = np.zeros(len(a), dtype=bool)
            for k, ((e, c, _), ix) in enumerate(zip(es, ixs)):
                mg = np.where(idx == k, m2s, m1s)
                r = np.clip(np.where((rsgn ^ sgn[k]) == 1, -mg, mg), C2V_MIN, C2V_MAX)
                c2v[e][a] = r
                new = np.clip(v2c[k] + r, app_min, app_max)
                if use_frozen:
                    new = np.where(v2c[k] == V2C_FROZEN, APP_FROZEN, np.where(v2c[k] == -V2C_FROZEN, -APP_FROZEN, new))
                sub = app[a, c]
                flipped |= np.any((sub[:, ix] < 0) != (new < 0), axis=1)
                parity ^= (new < 0).astype(np.int64)
                sub[:, ix] = new
                app[a, c] = sub
            ok &= np.all(parity == syn[a, l], axis=1)
            if strict:
                ok &= ~flipped
        it += 1
        iters[a] = it
        conv[a[ok]] = True
        active[a[ok]] = False
        if et_patience > 0:
            better = unsat < best[a]
            best[a] = np.where(better, unsat, best[a])
            stall[a] = np.where(better, 0, stall[a] + 1)
            give_up = ~ok & (stall[a] >= et_patience)
            active[a[give_up]] = False
    return app, iters, conv


def decode_channel(ch_type, ch_bit, syn, base, zc, iter_max, lq, et_patience=0):
    return decode_batch(init_app(ch_type, ch_bit, lq), syn, base, zc, iter_max, et_patience=et_patience)


# ----------------------------------------------------------------------------
# Blind reconciliation with optional trapping-set post-processing
# ----------------------------------------------------------------------------
def h2(p):
    return 0.0 if p <= 0 or p >= 1 else -p * math.log2(p) - (1 - p) * math.log2(1 - p)


def decode_attempt(ch_type, ch_bit, syn, base, zc, iter_max, lq=LQ_DEFAULT, pp_rounds=1, pp_min_usc=2,
                   pp_max_usc=16, et_patience=0):
    """One decoder run as started by the RTL block controller (start with fresh = 1).

    ch_type/ch_bit: (B, n). Key-flip marks from an earlier attempt are cleared first. If a decode fails, the number
    of unsatisfied checks (USC) of the final hard decision is computed; when it is <= pp_max_usc (trapping-set
    signature) and post-processing rounds are left, the channel sign of every key bit touching >= pp_min_usc USCs
    is toggled (T_KEY <-> T_KEY_FLIP) and the block is decoded again.
    A failed decode whose hard decision satisfies the syndrome (n_usc == 0) also counts as converged.
    Returns dict(conv, iters (sum over all decodes), decodes, n_usc (last decode), hard, ch_type)."""
    bsz = ch_type.shape[0]
    n = NCOL * zc
    ct = np.where(ch_type == T_KEY_FLIP, T_KEY, ch_type)
    conv = np.zeros(bsz, dtype=bool)
    iters = np.zeros(bsz, dtype=np.int64)
    decodes = np.zeros(bsz, dtype=np.int64)
    n_usc = np.zeros(bsz, dtype=np.int64)
    hard = np.zeros((bsz, n), dtype=np.int64)
    todo = np.arange(bsz)
    for pr in range(pp_rounds + 1):
        app, it, cv = decode_channel(ct[todo].reshape(-1, NCOL, zc), ch_bit[todo].reshape(-1, NCOL, zc),
                                     syn[todo], base, zc, iter_max, lq, et_patience)
        iters[todo] += it
        decodes[todo] += 1
        h = (app < 0).astype(np.int64)
        hard[todo] = h.reshape(len(todo), n)
        conv[todo] = cv
        usc = syndrome(base, h, zc) ^ syn[todo]
        nu = usc.sum(axis=(1, 2))
        n_usc[todo] = nu
        cv = cv | (nu == 0)            # hard decision satisfies the syndrome although APP signs still moved
        conv[todo] = cv
        go = ~cv & (nu <= pp_max_usc)
        if pr == pp_rounds or not go.any():
            break
        cnt = vn_usc_count(base, usc[go], zc).reshape(-1, n)
        sub = ct[todo[go]]
        sel = (cnt >= pp_min_usc) & ((sub == T_KEY) | (sub == T_KEY_FLIP))
        sub[sel] ^= (T_KEY ^ T_KEY_FLIP)
        ct[todo[go]] = sub
        todo = todo[go]
    return {"conv": conv, "iters": iters, "decodes": decodes, "n_usc": n_usc, "hard": hard, "ch_type": ct}


def make_blocks(zc, base, qber, frames, delta, rng, pos_d=None):
    """Alice/Bob data for `frames` blocks: v (Alice incl. padding), pos_d, d, ch_type, ch_bit, syn.
    pos_d: positions of D in reveal order (puncture.order); None = random (the pre-2026-10-11 behaviour)."""
    n = NCOL * zc
    d = int(round(delta * n))
    pos_d = rng.choice(n, d, replace=False) if pos_d is None else np.asarray(pos_d)[:d]
    v = rng.integers(0, 2, (frames, n), dtype=np.int64)
    err = (rng.random((frames, n)) < qber).astype(np.int64)
    err[:, pos_d] = 0
    ch_type = np.zeros((frames, n), dtype=np.int64)
    ch_type[:, pos_d] = T_PUNCT
    ch_bit = v ^ err
    ch_bit[:, pos_d] = 0
    syn = syndrome(base, v.reshape(frames, NCOL, zc), zc)
    return {"v": v, "pos_d": pos_d, "d": d, "ch_type": ch_type, "ch_bit": ch_bit, "syn": syn}


def run_blind(base, zc, qber, frames, delta=0.10, step=None, iter_max=50, seed=2026, lq=LQ_DEFAULT,
              pp_rounds=1, pp_min_usc=2, pp_max_usc=16, collect=False, et_patience=0, pos_d=None):
    rng = np.random.default_rng(seed)
    n = NCOL * zc
    mb = len(base)
    m = mb * zc
    blk = make_blocks(zc, base, qber, frames, delta, rng, pos_d)
    v, pos_d, d = blk["v"], blk["pos_d"], blk["d"]
    ch_type, ch_bit, syn = blk["ch_type"], blk["ch_bit"], blk["syn"]
    step = step or max(1, -(-d // 4))
    key_mask = np.ones(n, dtype=bool)
    key_mask[pos_d] = False
    n_key = n - d

    revealed = np.zeros(frames, dtype=np.int64)
    attempts = np.zeros(frames, dtype=np.int64)
    decodes = np.zeros(frames, dtype=np.int64)
    total_iters = np.zeros(frames, dtype=np.int64)
    success = np.zeros(frames, dtype=bool)
    undetected = np.zeros(frames, dtype=bool)
    pp_saved = 0
    fail_usc = []
    pending = np.arange(frames)
    r = 0
    while len(pending):
        res = decode_attempt(ch_type[pending], ch_bit[pending], syn[pending], base, zc, iter_max, lq,
                             pp_rounds, pp_min_usc, pp_max_usc, et_patience)
        ch_type[pending] = res["ch_type"]
        attempts[pending] += 1
        decodes[pending] += res["decodes"]
        total_iters[pending] += res["iters"]
        conv = res["conv"]
        good = np.all(res["hard"][:, key_mask] == v[pending][:, key_mask], axis=1)
        success[pending[conv & good]] = True
        undetected[pending[conv & ~good]] = True
        revealed[pending[conv]] = r
        pp_saved += int((conv & (res["decodes"] > 1)).sum())
        if collect:
            fail_usc.extend(res["n_usc"][~conv].tolist())
        pending = pending[~conv]
        if r >= d or not len(pending):
            break
        nxt = pos_d[r:r + step]
        r = min(d, r + step)
        ch_type[np.ix_(pending, nxt)] = T_SHORT
        ch_bit[np.ix_(pending, nxt)] = v[np.ix_(pending, nxt)]

    leak = m - d + revealed
    hq = h2(qber)
    ok = success
    st = {
        "zc": zc, "n": n, "frames": frames, "R0": 1 - mb / NCOL,
        "rate_max": (n - m) / n_key, "rate_min": (n - m - d) / n_key,
        "fer": 1 - ok.mean(), "undetected": int(undetected.sum()), "pp_saved": pp_saved,
        "avg_attempts": attempts[ok].mean() if ok.any() else float("nan"),
        "avg_decodes": decodes[ok].mean() if ok.any() else float("nan"),
        "avg_iters": total_iters[ok].mean() if ok.any() else float("nan"),
        "rate_eff": 1 - leak[ok].mean() / n_key if ok.any() else float("nan"),
        "f": leak[ok].mean() / (n_key * hq) if ok.any() and hq > 0 else float("nan"),
    }
    if collect:
        st["fail_usc"] = fail_usc
    return st


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zc", type=int, default=128)
    ap.add_argument("--codes", nargs="+", default=CODE_ORDER)
    ap.add_argument("--qber", nargs="+", type=float, default=[1, 2, 3, 4, 5])
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--delta", type=float, default=0.10)
    ap.add_argument("--iter-max", type=int, default=50)
    ap.add_argument("--lq", type=int, default=LQ_DEFAULT)
    ap.add_argument("--pp-rounds", type=int, default=1, help="trapping-set post-processing rounds (0: off)")
    ap.add_argument("--pp-min-usc", type=int, default=2)
    ap.add_argument("--pp-max-usc", type=int, default=16)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--csv", default="")
    args = ap.parse_args()

    codes = load_codes(args.zc)
    rows = []
    print(f"zc={args.zc} n={NCOL * args.zc} delta={args.delta} iter_max={args.iter_max} lq={args.lq} "
          f"pp(rounds={args.pp_rounds}, min_usc={args.pp_min_usc}, max_usc={args.pp_max_usc}) frames={args.frames}")
    hdr = f"{'code':5} {'Q%':>4} {'Rmax':>5} {'Rmin':>5} {'FER':>6} {'Reff':>6} {'f':>5} {'att':>4} {'dec':>4} " \
          f"{'iters':>6} {'undet':>5} {'pp_ok':>5}"
    print(hdr)
    print("-" * len(hdr))
    for name in args.codes:
        for q in args.qber:
            s = run_blind(codes[name], args.zc, q / 100, args.frames, args.delta, None, args.iter_max, args.seed,
                          args.lq, args.pp_rounds, args.pp_min_usc, args.pp_max_usc)
            print(f"{name:5} {q:4.1f} {s['rate_max']:5.3f} {s['rate_min']:5.3f} {s['fer']:6.3f} {s['rate_eff']:6.3f} "
                  f"{s['f']:5.2f} {s['avg_attempts']:4.2f} {s['avg_decodes']:4.2f} {s['avg_iters']:6.1f} "
                  f"{s['undetected']:5d} {s['pp_saved']:5d}", flush=True)
            rows.append({"code": name, "qber": q, **s})
    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
