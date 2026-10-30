"""
Secret-key rate vs raw (sifted) key rate: fixed profiles vs backlog-driven switching (dyn_ir.simulate_queue).

Same drifting QBER sequence as exp_tune.py, RTT 100 us, 100 MHz, PA block 1 Mbit for the secret fraction.
Usage: python exp_adaptive.py [--per-level 6] [--out ../results/exp_adaptive.txt]
"""
import argparse
import os
from multiprocessing import Pool

import dyn_ir as dy
import exp_tune as et

RATES = [2, 5, 8, 11, 14, 18, 25, 40]                 # sifted key Mbit/s offered to IR
ALL = {**dy.PROFILES,
       "basic_old": ("basic", dict(gs=False, cn="oms", schedule="serial")),
       "dyn_old": ("dynamic", dict(gs=False, cn="oms", schedule="serial"))}
POLICIES = ["basic_old", "dyn_old", "efficiency", "throughput", "adaptive"]


def run(args):
    policy, rate, per_level = args
    r = dy.simulate_queue(et.sequence(per_level), rate, policy=policy, profiles=ALL)
    return policy, rate, r["skr"], r["tp_share"], r["ok"]


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-level", type=int, default=6)
    ap.add_argument("--out", default=os.path.join(here, "..", "results", "exp_adaptive.txt"))
    args = ap.parse_args()
    jobs = [(p, r, args.per_level) for r in RATES for p in POLICIES]
    with Pool(os.cpu_count() or 4) as pool:
        res = pool.map(run, jobs)
    tab = {(p, r): (s, tp, ok) for p, r, s, tp, ok in res}
    lines = [f"secret key Mbit/s vs sifted key rate (QBER drift {et.LEVELS} x {args.per_level}, RTT 100 us, "
             f"100 MHz); adaptive: BACKLOG_HI={dy.BACKLOG_HI} LO={dy.BACKLOG_LO}, [share of blocks in throughput mode]",
             f"{'raw Mbit/s':>10} " + " ".join(f"{p:>12}" for p in POLICIES)]
    for r in RATES:
        cells = []
        for p in POLICIES:
            s, tp, ok = tab[(p, r)]
            cells.append(f"{s:6.2f} [{tp:3.0%}]" if p == "adaptive" else f"{s:12.2f}")
        lines.append(f"{r:>10} " + " ".join(cells))
    print("\n".join(lines))
    with open(args.out, "w", encoding="utf8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
