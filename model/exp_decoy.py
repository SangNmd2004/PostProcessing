"""
Source / protocol parameters vs finite-key secret length on a fixed link (same channel, same link time).

For each configuration a session of LINK_S seconds is simulated (gen_qkd_session.Session) and the finite-key length
(pa_model.secure_length_decoy, Lim 2014) is computed for several reconciliation efficiencies f, with
leak_EC = f h(Q) n + 64 bits per IR block. Varied: decoy intensity mu2, intensity probabilities, signal mu1,
basis bias PZ (Z = key basis).
Usage: python exp_decoy.py [--level STRONG] [--link-s 939] [--out ../results/exp_decoy.txt]
"""
import argparse
import os
from multiprocessing import Pool

import numpy as np

import dyn_ir as dy
import gen_qkd_session as g
import ir_model as m
import pa_model as pa

CONFIGS = {
    "current mu .6/.2/0 p 6:1:1 PZ .5": dict(MU=(0.6, 0.2, 0.0), P_K=(0.75, 0.125, 0.125), PZ=0.5),
    "mu .6/.1/0  p 6:1:1  PZ .5": dict(MU=(0.6, 0.1, 0.0), P_K=(0.75, 0.125, 0.125), PZ=0.5),
    "mu .5/.1/0  p .6/.25/.15 PZ .5": dict(MU=(0.5, 0.1, 0.0), P_K=(0.6, 0.25, 0.15), PZ=0.5),
    "mu .5/.1/0  p .6/.25/.15 PZ .8": dict(MU=(0.5, 0.1, 0.0), P_K=(0.6, 0.25, 0.15), PZ=0.8),
    "mu .5/.1/0  p .6/.25/.15 PZ .9": dict(MU=(0.5, 0.1, 0.0), P_K=(0.6, 0.25, 0.15), PZ=0.9),
    "mu .4/.08/0 p .6/.25/.15 PZ .8": dict(MU=(0.4, 0.08, 0.0), P_K=(0.6, 0.25, 0.15), PZ=0.8),
    "mu .5/.05/0 p .6/.25/.15 PZ .8": dict(MU=(0.5, 0.05, 0.0), P_K=(0.6, 0.25, 0.15), PZ=0.8),
}
F_LIST = (1.1, 1.25, 1.4)


def run(job):
    name, level, link_s, scale, y0 = job
    kw = CONFIGS[name]
    s = g.Session(level, seed=7, Y0=y0, **kw)
    parts = [s.chunk(1.0) for _ in range(int(link_s))]
    d = {k: np.concatenate([p[k] for p in parts]) for k in ("k", "basis", "a", "b")}
    z, x = d["basis"] == 0, d["basis"] == 1
    e = d["a"] != d["b"]
    nk = [int((z & (d["k"] == k)).sum()) * scale for k in range(3)]
    nt = [int((x & (d["k"] == k)).sum()) * scale for k in range(3)]
    mt = [int((x & e & (d["k"] == k)).sum()) * scale for k in range(3)]
    q = float(e[z].mean())
    n = sum(nk)
    row = [name, n, q]
    for f in F_LIST:
        r = pa.secure_length_decoy(nk, nt, mt, kw["MU"], kw["P_K"], int(f * m.h2(q) * n) + 64 * (n // dy.NKEY))
        row.append((r["ell"], r["s1"] / n, r["phi"]))
    return row


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="STRONG")
    ap.add_argument("--link-s", type=float, default=939)
    ap.add_argument("--scale", type=int, default=1, help="multiply counts (longer link time, same statistics)")
    ap.add_argument("--y0", type=float, default=g.DEFAULTS["Y0"], help="dark + background per detector")
    ap.add_argument("--configs", nargs="+", default=list(CONFIGS))
    ap.add_argument("--out", default=os.path.join(here, "..", "results", "exp_decoy.txt"))
    args = ap.parse_args()
    with Pool(len(args.configs)) as pool:
        rows = pool.map(run, [(n, args.level, args.link_s, args.scale, args.y0) for n in args.configs])
    L = [f"level {args.level}, Y0 {args.y0:.0e}, link time {args.link_s * args.scale:.0f} s (simulated {args.link_s:.0f} s x {args.scale}), "
         f"Lim 2014 eps_sec 1e-9; cells: secret bits (s1/n, phase error)",
         f"{'config':34} {'n_key':>9} {'QBER':>6} " + " ".join(f"{'f=' + str(f):>26}" for f in F_LIST)]
    for name, n, q, *cells in rows:
        L.append(f"{name:34} {n:9d} {100 * q:5.2f}% " +
                 " ".join(f"{c[0]:9d} ({c[1]:.2f}, {100 * c[2]:4.1f}%)".rjust(26) for c in cells))
    print("\n".join(L))
    with open(args.out, "a", encoding="utf8") as fh:
        fh.write("\n".join(L) + "\n\n")


if __name__ == "__main__":
    main()
