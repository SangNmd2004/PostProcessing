"""
Physical simulation of decoy-state BB84 over a turbulent free-space link -> sifted detection records for the
post-processing chain (replaces the Test/*.csv generator for evaluation; that one had no channel loss and set the
QBER directly from the turbulence level).

Model, per pulse (event driven: only pulses that produce a click are materialised):
  source    weak coherent pulses, intensity class k with prob P_K: mu = MU[k] (signal / decoy / vacuum),
            Poisson photon number. Alice basis Z (key) with prob PZ, bit uniform.
  channel   eta(t) = ETA_DET * 10^(-LOSS_DB/10) * I(t). I(t): Gamma-Gamma irradiance (alpha, beta from the
            turbulence level), unit mean, temporally correlated: two AR(1) Gaussian processes with coherence time
            TAU_C, mapped to exact Gamma(alpha), Gamma(beta) marginals by rank (Gaussian copula), I = X * Y. Constant
            inside a slot of SLOT_S seconds.
  detection active basis choice at Bob (Z with prob PZ), two detectors (bit 0 / 1):
            signal click prob 1 - exp(-eta mu); detector = Alice bit XOR misalignment error (prob e_d(t)) when
            the bases match, random otherwise. e_d(t) = slow Ornstein-Uhlenbeck drift around ED0.
            dark + background clicks: prob Y0 per detector and pulse, random detector.
            two detectors in one pulse -> double click -> random bit (squashing).
            dead time DEAD_S per detector, afterpulse prob P_AP in a window AP_WIN_S after the dead time
            (same detector, so a random bit w.r.t. Alice).
  output    only basis-matched (sifted) detections are stored: pulse index, basis (0 Z key / 1 X test),
            intensity class, Alice bit, Bob bit; plus pulses sent per class and the slot irradiance / e_d traces.

Default parameters: decoy BB84 of Zhu et al. JLT 2022 (mu 0.6 / 0.2 / 0, 6:1:1, detector efficiency 10 %,
dark count 1e-6, dead time 2 us, afterpulse < 0.5 %), 100 MHz, free-space link budget LOSS_DB, turbulence
levels (sigma_R^2, alpha, beta) taken from the team's Test/bb84_key_test_Sim_*.csv.

Turbulence alone hardly raises the QBER (fades must reach ~1/1000 of the mean before dark counts matter); the
QBER is set by the link budget. Each level therefore comes with a link loss (stronger turbulence <-> longer
path): 15 / 22 / 27 / 30 / 32 dB with Y0 = 2e-6, giving a mean QBER of about 1.4 .. 7 %.

Usage: python gen_qkd_session.py [--levels WEAK MILD ...] [--target-z 1200000] [--out ../data/sessions]
"""
import argparse
import json
import math
import os

import numpy as np

# turbulence levels of the team's CSV generator (sigma_R^2, alpha, beta) and the link loss used with each (dB)
LEVELS = {
    "WEAK": (0.2, 11.65, 10.12),
    "MILD": (0.5, 5.98, 4.40),
    "MODERATE": (1.2, 4.20, 2.27),
    "STRONG": (3.0, 4.12, 1.44),
    "SEVERE": (8.0, 5.27, 1.13),
}
LINK_LOSS_DB = {"WEAK": 15.0, "MILD": 22.0, "MODERATE": 27.0, "STRONG": 30.0, "SEVERE": 32.0}

DEFAULTS = dict(
    F_REP=100e6,            # pulse rate (Hz)
    MU=(0.6, 0.2, 0.0),     # signal, decoy, vacuum
    P_K=(0.75, 0.125, 0.125),
    PZ=0.5,                 # basis Z (key) probability, Alice and Bob
    ETA_DET=0.10,
    LOSS_DB=None,           # link + optics loss; None: LINK_LOSS_DB[level]
    Y0=2e-6,                # dark (1e-6) + background click prob per detector and pulse
    ED0=0.010,              # misalignment error, mean
    ED_SIG=0.004,           # OU stationary std of the drift
    ED_TAU_S=20.0,          # OU time constant (polarisation drift / feedback)
    TAU_C_S=5e-3,           # turbulence coherence time
    SLOT_S=2e-4,            # irradiance constant within a slot
    DEAD_S=2e-6,
    P_AP=0.005,
    AP_WIN_S=1e-6,
)


TRACE_DECIM = 5            # stored irradiance / e_d traces: mean over 5 slots (1 ms)


def gamma_by_rank(z, shape, rng):
    """Gamma(shape, scale 1/shape) values (unit mean) carrying the temporal correlation of the Gaussian series z:
    exact Gamma samples are sorted and assigned in the rank order of z (Gaussian copula, no scipy needed)."""
    g = np.sort(rng.gamma(shape, 1.0 / shape, z.size))
    out = np.empty(z.size)
    out[np.argsort(z, kind="stable")] = g
    return out


class Session:
    def __init__(self, level, seed=1, **kw):
        self.p = dict(DEFAULTS, **kw)
        if self.p["LOSS_DB"] is None:
            self.p["LOSS_DB"] = LINK_LOSS_DB[level]
        self.level = level
        self.sig2, self.alpha, self.beta = LEVELS[level]
        self.rng = np.random.default_rng(seed)
        self.zx = self.rng.standard_normal()
        self.zy = self.rng.standard_normal()
        self.ed_ou = 0.0
        self.t_pulse = 0
        self.slots_i, self.slots_ed = [], []

    def _slots(self, n):
        """Irradiance and misalignment of the next n slots (AR(1) state carried across chunks)."""
        p, rng = self.p, self.rng
        rho = math.exp(-p["SLOT_S"] / p["TAU_C_S"])
        s = math.sqrt(1 - rho * rho)
        ex, ey = rng.standard_normal(n), rng.standard_normal(n)
        zx, zy = np.empty(n), np.empty(n)
        x, y = self.zx, self.zy
        for i in range(n):                      # n ~ 5000 per second of link time
            x = rho * x + s * ex[i]
            y = rho * y + s * ey[i]
            zx[i], zy[i] = x, y
        self.zx, self.zy = x, y
        irr = gamma_by_rank(zx, self.alpha, rng) * gamma_by_rank(zy, self.beta, rng)
        r_ed = math.exp(-p["SLOT_S"] / p["ED_TAU_S"])
        e_ed = rng.standard_normal(n) * p["ED_SIG"] * math.sqrt(1 - r_ed * r_ed)
        ed = np.empty(n)
        o = self.ed_ou
        for i in range(n):
            o = r_ed * o + e_ed[i]
            ed[i] = o
        self.ed_ou = o
        ed = np.clip(p["ED0"] + ed, 0.002, 0.08)
        return irr, ed

    def chunk(self, seconds):
        """Simulate `seconds` of link time. Returns dict of sifted detections and per-class pulse counts."""
        p, rng = self.p, self.rng
        n_slot = int(round(p["SLOT_S"] * p["F_REP"]))
        ns = int(round(seconds / p["SLOT_S"]))
        irr, ed = self._slots(ns)
        self.slots_i.append(irr.astype(np.float32))
        self.slots_ed.append(ed.astype(np.float32))
        eta = p["ETA_DET"] * 10 ** (-p["LOSS_DB"] / 10) * irr
        base = self.t_pulse
        mu, pk = np.array(p["MU"]), np.array(p["P_K"])
        # pulses per class and slot
        nk = np.zeros((3, ns), dtype=np.int64)
        left = np.full(ns, n_slot, dtype=np.int64)
        rem = 1.0
        for k in range(3):
            nk[k] = left if k == 2 else rng.binomial(left, pk[k] / rem)
            left -= nk[k]
            rem -= pk[k]
        ev_t, ev_k, ev_kind, ev_det = [], [], [], []
        for k in range(3):
            # signal clicks (some photon detected)
            if mu[k] > 0:
                c = rng.binomial(nk[k], 1 - np.exp(-eta * mu[k]))
                sl = np.repeat(np.arange(ns), c)
                ev_t.append(base + sl * n_slot + rng.integers(0, n_slot, sl.size))
                ev_k.append(np.full(sl.size, k, np.uint8))
                ev_kind.append(np.zeros(sl.size, np.uint8))           # 0 signal
                ev_det.append(np.full(sl.size, 255, np.uint8))        # decided below
            # dark / background clicks, either detector
            c = rng.binomial(nk[k], 2 * p["Y0"])
            sl = np.repeat(np.arange(ns), c)
            ev_t.append(base + sl * n_slot + rng.integers(0, n_slot, sl.size))
            ev_k.append(np.full(sl.size, k, np.uint8))
            ev_kind.append(np.ones(sl.size, np.uint8))                # 1 dark
            ev_det.append(rng.integers(0, 2, sl.size).astype(np.uint8))
        t = np.concatenate(ev_t)
        k = np.concatenate(ev_k)
        kind = np.concatenate(ev_kind)
        det = np.concatenate(ev_det)
        order = np.argsort(t, kind="stable")
        t, k, kind, det = t[order], k[order], kind[order], det[order]
        n = t.size
        # Alice / Bob choices at the pulse of each event
        a_bas = (rng.random(n) >= p["PZ"]).astype(np.uint8)          # 0 Z, 1 X
        b_bas = (rng.random(n) >= p["PZ"]).astype(np.uint8)
        a_bit = rng.integers(0, 2, n).astype(np.uint8)
        slot = (t - base) // n_slot
        err = rng.random(n) < ed[slot]
        sig = kind == 0
        match = a_bas == b_bas
        det = np.where(sig & match, a_bit ^ err.astype(np.uint8), det)
        det = np.where(sig & ~match, rng.integers(0, 2, n).astype(np.uint8), det)
        # dead time, double clicks and afterpulses (sequential over events)
        dead = int(round(p["DEAD_S"] * p["F_REP"]))
        apw = int(round(p["AP_WIN_S"] * p["F_REP"]))
        b_bit, keep = self._detect(t, det, dead, apw, a_bit, a_bas, b_bas, k)
        t, k, a_bas, b_bas, a_bit, b_bit = (x[keep] for x in (t, k, a_bas, b_bas, a_bit, b_bit))
        self.t_pulse = base + ns * n_slot
        sift = a_bas == b_bas
        return {"t": t[sift], "k": k[sift], "basis": a_bas[sift], "a": a_bit[sift], "b": b_bit[sift],
                "pulses": nk.sum(axis=1), "clicks": np.bincount(k, minlength=3)}

    def _detect(self, t, det, dead, apw, a_bit, a_bas, b_bas, k):
        """Dead time per detector, double clicks (random bit), afterpulses. Afterpulses are appended in place of
        the next event they land on (approximation: an afterpulse adds a click only if it lands on an event-free
        pulse; it is then modelled as a fresh event with random Alice data)."""
        rng = self.rng
        n = t.size
        b_bit = det.copy()
        keep = np.zeros(n, dtype=bool)
        last = [-10 ** 18, -10 ** 18]
        ap_t, ap_d = [], []
        i = 0
        u_ap = rng.random(n)
        u_off = rng.integers(0, max(apw, 1), n)
        while i < n:
            ti = t[i]
            j = i
            dets = set()
            while j < n and t[j] == ti:                  # events in the same pulse
                dets.add(int(det[j]))
                j += 1
            live = [d for d in dets if ti - last[d] >= dead]
            if live:
                keep[i] = True
                b_bit[i] = live[0] if len(live) == 1 else rng.integers(0, 2)
                for d in live:
                    last[d] = ti
                    if u_ap[i] < self.p["P_AP"]:
                        ap_t.append(ti + dead + int(u_off[i]))
                        ap_d.append(d)
            i = j
        # afterpulses: extra clicks, random Alice data, Bob bit = detector
        if ap_t:
            m = len(ap_t)
            self._extra = {
                "t": np.array(ap_t, np.int64), "det": np.array(ap_d, np.uint8),
                "a_bas": (rng.random(m) >= self.p["PZ"]).astype(np.uint8),
                "b_bas": (rng.random(m) >= self.p["PZ"]).astype(np.uint8),
                "a_bit": rng.integers(0, 2, m).astype(np.uint8),
                "k": rng.choice(3, m, p=self.p["P_K"]).astype(np.uint8)}
        else:
            self._extra = None
        return b_bit, keep


def run_session(level, target_z, seed=1, chunk_s=1.0, **kw):
    s = Session(level, seed, **kw)
    parts = []
    pulses = np.zeros(3, np.int64)
    clicks = np.zeros(3, np.int64)
    nz = 0
    while nz < target_z:
        c = s.chunk(chunk_s)
        ex = s._extra
        if ex is not None:                                            # afterpulse clicks (sifted ones kept)
            sift = ex["a_bas"] == ex["b_bas"]
            c["t"] = np.concatenate([c["t"], ex["t"][sift]])
            c["k"] = np.concatenate([c["k"], ex["k"][sift]])
            c["basis"] = np.concatenate([c["basis"], ex["a_bas"][sift]])
            c["a"] = np.concatenate([c["a"], ex["a_bit"][sift]])
            c["b"] = np.concatenate([c["b"], ex["det"][sift]])
            o = np.argsort(c["t"], kind="stable")
            for key in ("t", "k", "basis", "a", "b"):
                c[key] = c[key][o]
            clicks += np.bincount(ex["k"], minlength=3)
        parts.append(c)
        pulses += c["pulses"]
        clicks += c["clicks"]
        nz += int((c["basis"] == 0).sum())
    out = {key: np.concatenate([c[key] for c in parts]) for key in ("t", "k", "basis", "a", "b")}
    out["pulses"] = pulses
    out["clicks"] = clicks
    irr, ed = np.concatenate(s.slots_i), np.concatenate(s.slots_ed)
    nd = len(irr) // TRACE_DECIM * TRACE_DECIM
    out["irr"] = irr[:nd].reshape(-1, TRACE_DECIM).mean(axis=1).astype(np.float32)   # diagnostics trace, 1 ms
    out["ed"] = ed[:nd].reshape(-1, TRACE_DECIM).mean(axis=1).astype(np.float32)
    meta = dict(s.p, level=level, sigma_r2=s.sig2, alpha=s.alpha, beta=s.beta, seed=seed,
                seconds=float(len(irr) * s.p["SLOT_S"]), trace_s=TRACE_DECIM * s.p["SLOT_S"])
    return out, meta


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--levels", nargs="+", default=list(LEVELS))
    ap.add_argument("--target-z", type=int, default=1_200_000, help="sifted key-basis (Z) detections per session")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=os.path.join(here, "..", "data", "sessions"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    from multiprocessing import Pool
    jobs = [(lv, args.target_z, args.seed + 101 * i, args.out) for i, lv in enumerate(args.levels)]
    with Pool(len(jobs)) as pool:
        for line in pool.map(_job, jobs):
            print(line, flush=True)


def _job(job):
    lv, target_z, seed, out = job
    d, meta = run_session(lv, target_z, seed=seed)
    path = os.path.join(out, f"session_{lv.lower()}")
    np.savez_compressed(path + ".npz", **d)
    with open(path + ".json", "w", encoding="utf8") as fh:
        json.dump(meta, fh, indent=1)
    z = d["basis"] == 0
    return (f"{lv:9} {meta['LOSS_DB']:4.0f} dB {meta['seconds']:7.1f} s  sifted Z {int(z.sum()):8d}  "
            f"X {int((~z).sum()):8d}  QBER Z {100 * (d['a'][z] != d['b'][z]).mean():5.2f}%  "
            f"X {100 * (d['a'][~z] != d['b'][~z]).mean():5.2f}%")


if __name__ == "__main__":
    main()
