"""
QBER sweep on a BSC: reconciliation efficiency, FER, throughput and secret-key figures of the controller profiles.

Figures of merit (Yang et al., JLT 2020, eq. 2, written for DV-QKD; dyn_ir.summarize):
  eta    = secret bits per sifted bit (finite-size PA block 1 Mbit) - what counts while the IR keeps up with the
           raw key (alpha = 1)
  skr_*  = secret Mbit/s when the IR is the bottleneck: decoder cycles at 100 MHz + one classical round trip per
           attempt (RTT 0 / 100 us)
Configurations:
  basic_old   : fixed QBER table, random D, offset min-sum, reveal d/4   (state of 2026-10-10)
  dyn_old     : dynamic controller, random D, offset min-sum             (state of 2026-10-10)
  efficiency  : dyn_ir.PROFILES["efficiency"] (basic blind + GS D + NMS + early discard)
  throughput  : dyn_ir.PROFILES["throughput"] (dynamic + GS D + NMS + f_safe 1.7, z 1.5, f* 1.3)
Usage: python exp_compare.py [--blocks 24] [--configs ...] [--out ../results/exp_compare.txt]
"""
import argparse
import os
from multiprocessing import Pool

import numpy as np

import dyn_ir as dy

QBERS = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08]
CONFIGS = {
    "basic_old": dict(mode="basic", gs=False, cn="oms", schedule="serial"),
    "dyn_old": dict(mode="dynamic", gs=False, cn="oms", schedule="serial"),
    **{k: dict(mode=v[0], **v[1]) for k, v in dy.PROFILES.items()},
}


def channel(q, blocks, seed):
    rng = np.random.default_rng(seed)
    seq = []
    for _ in range(blocks):
        a = rng.integers(0, 2, dy.NKEY, dtype=np.uint8)
        e = (rng.random(dy.NKEY) < q).astype(np.uint8)
        seq.append((a, a ^ e))
    return seq


def run(job):
    qp, name, blocks = job
    q = qp / 100
    kw = dict(CONFIGS[name])
    mode = kw.pop("mode")
    res = dy.simulate(channel(q, blocks, int(q * 1e4)), mode, **kw)
    s = dy.summarize(res)
    und = sum(r["undetected"] for r in res)
    return (f"{qp:4.1f}% {name:12} {s['success']:>3}/{s['blocks']:<2} {und:5d} {s['f']:5.2f} {s['attempts']:5.2f} "
            f"{s['iters']:6.1f} {s['eta']:6.3f} {s['thr_0us']:6.1f} {s['thr_100us']:6.1f} {s['skr_0us']:6.2f} "
            f"{s['skr_100us']:6.2f}")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", type=int, default=24)
    ap.add_argument("--configs", nargs="+", default=list(CONFIGS))
    ap.add_argument("--qber", nargs="+", type=float, default=[100 * q for q in QBERS])
    ap.add_argument("--out", default=os.path.join(here, "..", "results", "exp_compare.txt"))
    args = ap.parse_args()

    lines = [f"n={dy.N} d={dy.D} key={dy.NKEY} iter_max={dy.ITER_MAX} ET={dy.ET} PP={dy.PP} blocks/QBER={args.blocks}"
             f" | eta = secret bits/sifted bit, thr = reconciled Mbit/s, skr = secret Mbit/s (PA block 1 Mbit), 100 MHz",
             f"{'QBER':>5} {'config':12} {'ok':>6} {'undet':>5} {'f':>5} {'att':>5} {'it':>6} {'eta':>6} "
             f"{'thr0':>6} {'thr100':>6} {'skr0':>6} {'skr100':>6}"]
    with Pool(os.cpu_count() or 4) as pool:
        lines += pool.map(run, [(qp, name, args.blocks) for qp in args.qber for name in args.configs])
    print("\n".join(lines), flush=True)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
