"""
Experiment: check-node magnitude correction, offset min-sum (RTL today) vs normalized min-sum (shift-add alphas).

Same blind setup as exp_punct.py (step 16, ET 12, PP on), punctured positions from puncture.order (GS).
Usage: python exp_cn.py [--frames 200] [--out ../results/exp_cn.txt]
"""
import argparse
import os

import ir_model as m
import puncture as pu

POINTS = {"r56": [0.01], "r34": [0.02], "r23": [0.035], "r12": [0.065]}
MODES = ["oms", "nms75", "nms81", "nms75o1"]


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--out", default=os.path.join(here, "..", "results", "exp_cn.txt"))
    args = ap.parse_args()
    zc = 128
    d = int(round(0.10 * m.NCOL * zc))
    codes = m.load_codes(zc)
    lines = [f"zc={zc} d={d} frames={args.frames} step=16 ET=12 PP=(1,2,16), D = puncture.order (GS)",
             f"{'code':4} {'QBER':>5} {'mode':8} {'FER':>6} {'f':>6} {'att':>5} {'iters':>6} {'undet':>5}"]
    print("\n".join(lines), flush=True)
    for name, qs in POINTS.items():
        pos = pu.order(name, codes[name], zc, d)
        for q in qs:
            for mode in MODES:
                m.CN_MODE = mode
                s = m.run_blind(codes[name], zc, q, args.frames, step=16, et_patience=12, pos_d=pos)
                lines.append(f"{name:4} {100 * q:4.1f}% {mode:8} {s['fer']:6.3f} {s['f']:6.3f} {s['avg_attempts']:5.2f} "
                             f"{s['avg_iters']:6.1f} {s['undetected']:5d}")
                print(lines[-1], flush=True)
    m.CN_MODE = "oms"
    with open(args.out, "w", encoding="utf8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
