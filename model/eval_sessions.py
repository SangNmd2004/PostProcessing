"""
Full post-processing evaluation on physically simulated decoy-BB84 sessions (gen_qkd_session.py), with a
finite-key secret length (Lim et al. 2014) instead of the per-block asymptotic fraction.

Per session (one PA block = all reconciled key-basis bits of the session, >= 1.2e6 bits):
  1. validation: gain per intensity vs. the analytic expectation over the stored irradiance trace (no dead time),
     QBER of key (Z) and test (X) basis, block-to-block QBER spread.
  2. IR: key-basis bits in time order, blocks of NKEY bits. QBER estimate of a block = test-basis (X) errors of
     the same time window (public test data, no key bit disclosed). Every controller configuration of the
     2026-10 work is run.
  3. finite key: leak_EC = sum over kept blocks of (m - d + revealed) + 64-bit verification tag per kept block.
     Decoy statistics: key-basis counts of the kept bits per intensity, test-basis counts / errors of the whole
     session. ell = pa_model.secure_length_decoy (eps_sec 1e-9, eps_cor 1e-15).
  4. time: IR time = decoder cycles at 100 MHz + RTT 100 us per attempt; secret rate = ell / max(link time, IR
     time) (the IR either keeps up with the link or becomes the bottleneck).
Usage: python eval_sessions.py [--sessions ../data/sessions] [--report ../results/sessions_eval]
"""
import argparse
import glob
import json
import math
import os
from multiprocessing import Pool

import numpy as np

import dyn_ir as dy
import ir_model as m
import pa_model as pa

CONFIGS = {
    "basic_old": ("basic", dict(gs=False, cn="oms", schedule="serial")),
    "dyn_old": ("dynamic", dict(gs=False, cn="oms", schedule="serial")),
    **dy.PROFILES,
}
RTT_US = 100.0
CLK_MHZ = 100.0
TAG_BITS = 64


def load(path):
    d = dict(np.load(path + ".npz"))
    with open(path + ".json", encoding="utf8") as fh:
        meta = json.load(fh)
    return d, meta


def blocks_of(d):
    """Key-basis bits in blocks of NKEY + the X-basis QBER estimate of each block's time window."""
    z = d["basis"] == 0
    tz, az, bz, kz = d["t"][z], d["a"][z], d["b"][z], d["k"][z]
    tx = d["t"][~z]
    ex = (d["a"][~z] != d["b"][~z]).astype(np.int64)
    cex = np.concatenate([[0], np.cumsum(ex)])
    out = []
    for i in range(len(tz) // dy.NKEY):
        sl = slice(i * dy.NKEY, (i + 1) * dy.NKEY)
        lo, hi = np.searchsorted(tx, tz[sl.start]), np.searchsorted(tx, tz[sl.stop - 1], side="right")
        n_est = int(hi - lo)
        q_est = (cex[hi] - cex[lo]) / n_est if n_est else 0.0
        out.append((az[sl], bz[sl], (q_est, n_est), kz[sl]))
    return out


def validation(d, meta):
    p = meta
    eta = p["ETA_DET"] * 10 ** (-p["LOSS_DB"] / 10) * d["irr"].astype(np.float64)
    gain_th = [float(np.mean(1 - (1 - p["Y0"]) ** 2 * np.exp(-eta * mu))) for mu in p["MU"]]
    gain = (d["clicks"] / d["pulses"]).tolist()
    z = d["basis"] == 0
    qz = float((d["a"][z] != d["b"][z]).mean())
    qx = float((d["a"][~z] != d["b"][~z]).mean())
    blk = blocks_of(d)
    qb = np.array([float((a != b).mean()) for a, b, _, _ in blk])
    return {"gain": gain, "gain_th": gain_th, "qz": qz, "qx": qx, "q_blk_min": float(qb.min()),
            "q_blk_max": float(qb.max()), "q_blk_std": float(qb.std()), "nblk": len(blk)}


def run(job):
    path, cfg = job
    d, meta = load(path)
    blk = blocks_of(d)
    mode, kw = CONFIGS[cfg]
    res = dy.simulate([(a, b, pe) for a, b, pe, _ in blk], mode, **kw)
    kept = [i for i, r in enumerate(res) if r["success"]]
    leak = sum(res[i]["leak"] for i in kept) + TAG_BITS * len(kept)
    nk = np.zeros(3, np.int64)
    for i in kept:
        nk += np.bincount(blk[i][3], minlength=3)
    x = d["basis"] == 1
    err = d["a"] != d["b"]
    nt = [int((x & (d["k"] == k)).sum()) for k in range(3)]
    mt = [int((x & err & (d["k"] == k)).sum()) for k in range(3)]
    fk = pa.secure_length_decoy(nk.tolist(), nt, mt, meta["MU"], meta["P_K"], leak)
    ir_s = (sum(r["cycles"] for r in res) / CLK_MHZ + RTT_US * sum(r["attempts"] for r in res)) * 1e-6
    n_kept = int(nk.sum())
    fs = [r["f"] for r in res if r["success"]]
    return {"session": os.path.basename(path), "cfg": cfg, "ok": len(kept), "blocks": len(res),
            "f": float(np.mean(fs)) if fs else float("nan"), "leak": leak, "n_kept": n_kept,
            "s1": fk["s1"], "phi": fk["phi"], "ell": fk["ell"], "ir_s": ir_s, "link_s": meta["seconds"]}


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default=os.path.join(here, "..", "data", "sessions"))
    ap.add_argument("--report", default=os.path.join(here, "..", "results", "sessions_eval"))
    args = ap.parse_args()
    paths = sorted(p[:-4] for p in glob.glob(os.path.join(args.sessions, "*.npz")))
    order = ["weak", "mild", "moderate", "strong", "severe"]
    paths.sort(key=lambda p: next((i for i, o in enumerate(order) if o in p), 99))
    with Pool(os.cpu_count() or 4) as pool:
        val = pool.map(_val, paths)
        res = pool.map(run, [(p, c) for p in paths for c in CONFIGS])

    L = ["# Post-processing on simulated decoy-BB84 sessions (finite key)", "",
         "Sessions: `model/gen_qkd_session.py` (decoy BB84 0.6/0.2/0, 6:1:1, 100 MHz, detector 10 %, Y0 2e-6, "
         "dead time 2 us, afterpulse 0.5 %, Gamma-Gamma turbulence with 5 ms coherence time, link loss per level). "
         "Finite key: Lim et al. 2014, eps_sec 1e-9, eps_cor 1e-15, one PA block per session, leak_EC includes a "
         f"{TAG_BITS}-bit verification tag per block. IR time at 100 MHz + RTT {RTT_US:.0f} us per attempt.", "",
         "## 1. Session statistics (validation)", "",
         "| Session | Loss | Link time | Gain signal / decoy / vacuum (sim) | Gain (analytic, no dead time) | "
         "QBER Z / X | Block QBER min..max (std) |", "|---|---|---|---|---|---|---|"]
    for p, v in zip(paths, val):
        meta = load(p)[1]
        g = " / ".join(f"{x:.2e}" for x in v["gain"])
        gt = " / ".join(f"{x:.2e}" for x in v["gain_th"])
        L.append(f"| {meta['level']} | {meta['LOSS_DB']:.0f} dB | {meta['seconds']:.0f} s | {g} | {gt} | "
                 f"{100 * v['qz']:.2f}% / {100 * v['qx']:.2f}% | {100 * v['q_blk_min']:.1f}..{100 * v['q_blk_max']:.1f}% "
                 f"({100 * v['q_blk_std']:.2f}) |")
    L += ["", "## 2. Finite-key result per controller configuration", "",
          "| Session | Config | Blocks ok | f | Kept key bits | leak_EC | s1 | phase err. | Secret bits ell | "
          "ell / kept | IR time / link time | Secret bit/s |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res:
        rate = r["ell"] / max(r["link_s"], r["ir_s"])
        L.append(f"| {r['session'].replace('session_', '')} | {r['cfg']} | {r['ok']}/{r['blocks']} | {r['f']:.2f} | "
                 f"{r['n_kept']} | {r['leak']} | {r['s1']:.0f} | {100 * r['phi']:.1f}% | {r['ell']} | "
                 f"{r['ell'] / max(r['n_kept'], 1):.3f} | {r['ir_s'] / r['link_s']:.3f} | {rate:.0f} |")
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report + ".md", "w", encoding="utf8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L))


def _val(path):
    d, meta = load(path)
    return validation(d, meta)


if __name__ == "__main__":
    main()
