"""
Experiment: choice / order of the punctured positions D (random vs grouping & sorting) on every mother code.

Blind reconciliation with a fine reveal step (16 bits, close to what the dynamic controller does), ET 12, PP on.
Variants:
  random        : rng.choice (old behaviour)
  gs_compact_rev: GS, compact (all 307 nodes 1-SR), reveal hardest first     <- puncture.order()
  gs_compact_fwd: GS, compact, reveal best-punctured first
  gs_reliable   : GS, most clean checks per node, reveal hardest first
Usage: python exp_punct.py [--frames 200] [--out ../results/exp_punct.txt]
"""
import argparse
import os

import numpy as np

import ir_model as m
import puncture as pu

POINTS = {"r56": [0.005, 0.01, 0.015], "r34": [0.015, 0.02, 0.025], "r23": [0.03, 0.04], "r12": [0.06, 0.07]}


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--out", default=os.path.join(here, "..", "results", "exp_punct.txt"))
    args = ap.parse_args()
    zc = 128
    d = int(round(0.10 * m.NCOL * zc))
    codes = m.load_codes(zc)
    lines = [f"zc={zc} d={d} frames={args.frames} step=16 ET=12 PP=(1,2,16)",
             f"{'code':4} {'QBER':>5} {'variant':15} {'FER':>6} {'f':>6} {'att':>5} {'iters':>6} {'undet':>5}"]
    print("\n".join(lines), flush=True)
    for name, qs in POINTS.items():
        base = codes[name]
        comp = pu.gs_select(base, zc, d, compact=True)
        rel = pu.gs_select(base, zc, d, compact=False)
        variants = {"random": None, "gs_compact_rev": comp[::-1], "gs_compact_fwd": comp, "gs_reliable": rel[::-1]}
        for q in qs:
            for vn, pos in variants.items():
                s = m.run_blind(base, zc, q, args.frames, step=16, et_patience=12, pos_d=pos)
                lines.append(f"{name:4} {100 * q:4.1f}% {vn:15} {s['fer']:6.3f} {s['f']:6.3f} {s['avg_attempts']:5.2f} "
                             f"{s['avg_iters']:6.1f} {s['undetected']:5d}")
                print(lines[-1], flush=True)
    with open(args.out, "w", encoding="utf8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
