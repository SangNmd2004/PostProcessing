"""Experiment: early termination patience vs. FER, f and decoder iterations (ZC = 128, basic blind rec).
Usage: python exp_et.py [frames]"""
import sys

import ir_model as m

ZC = 128
frames = int(sys.argv[1]) if len(sys.argv) > 1 else 150
codes = m.load_codes(ZC)
POINTS = [("r34", 0.02), ("r23", 0.035), ("r12", 0.06), ("r12", 0.08)]
print(f"zc={ZC} frames={frames} iter_max=50 pp_rounds=1; 'it/blk' = iterations per successful block "
      f"(all attempts, failures included)")
for name, q in POINTS:
    out = []
    for et in (0, 4, 6, 8, 12):
        s = m.run_blind(codes[name], ZC, q, frames, iter_max=50, et_patience=et)
        out.append(f"et={et:2d}: FER={s['fer']:.3f} f={s['f']:.2f} att={s['avg_attempts']:.2f} it/blk={s['avg_iters']:.0f}")
    print(f"{name} Q={100 * q:.1f}% | " + " | ".join(out), flush=True)
