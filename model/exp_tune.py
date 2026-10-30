"""
Controller tuning by the secret-key throughput (dyn_ir.summarize skr_100us: RTT 100 us, 100 MHz, PA block 1 Mbit).

Channel: QBER drifting 1 -> 6 -> 1 % in steps (BLOCKS_PER_LEVEL blocks per level, level jumps included), the
regime the dynamic controller is meant for. Every configuration sees the same block sequence.
Usage: python exp_tune.py [--per-level 6] [--out ../results/exp_tune.txt]
"""
import argparse
import itertools
import os

import numpy as np

import dyn_ir as dy

LEVELS = [0.01, 0.02, 0.03, 0.045, 0.06, 0.045, 0.03, 0.02, 0.01]


def sequence(per_level, seed=7):
    rng = np.random.default_rng(seed)
    seq = []
    for q in LEVELS:
        for _ in range(per_level):
            a = rng.integers(0, 2, dy.NKEY, dtype=np.uint8)
            e = (rng.random(dy.NKEY) < q).astype(np.uint8)
            seq.append((a, a ^ e))
    return seq


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-level", type=int, default=6)
    ap.add_argument("--out", default=os.path.join(here, "..", "results", "exp_tune.txt"))
    args = ap.parse_args()
    seq = sequence(args.per_level)
    runs = [("basic_old", "basic", dict(gs=False))]
    runs.append(("dyn_old", "dynamic", dict(gs=False)))
    for cn, fuse, f_safe, pe_z in itertools.product(["oms", "nms75"], [False, True], [None, 1.5, 1.7], [1.0, 0.5]):
        name = f"dyn cn={cn} fuse={int(fuse)} f_safe={f_safe} z={pe_z}"
        runs.append((name, "dynamic", dict(gs=True, cn=cn, fuse=fuse, f_safe=f_safe, pe_z=pe_z)))
    lines = [f"QBER levels {LEVELS} x {args.per_level} blocks, GS = grouping & sorting D",
             f"{'config':44} {'ok':>6} {'f':>5} {'att':>5} {'it':>6} {'thr100':>6} {'skr0':>6} {'skr100':>6} {'skr1ms':>6}"]
    print("\n".join(lines), flush=True)
    for name, mode, kw in runs:
        res = dy.simulate(seq, mode, **kw)
        s = dy.summarize(res)
        lines.append(f"{name:44} {s['success']:>3}/{s['blocks']:<2} {s['f']:5.2f} {s['attempts']:5.2f} {s['iters']:6.1f} "
                     f"{s['thr_100us']:6.1f} {s['skr_0us']:6.2f} {s['skr_100us']:6.2f} {s['skr_1000us']:6.3f}")
        print(lines[-1], flush=True)
    with open(args.out, "w", encoding="utf8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
