"""Experiment: block length (ZC) and gated trapping-set post-processing.
Usage: python exp_pp.py ZC [frames]"""
import sys

import numpy as np

import ir_model as m

zc = int(sys.argv[1])
frames = int(sys.argv[2]) if len(sys.argv) > 2 else 150
codes = m.load_codes(zc)
for name, qs in [("r34", [1.0, 2.0]), ("r23", [3.0, 4.0]), ("r12", [6.0, 7.0])]:
    for q in qs:
        out = []
        for ppr in (0, 2):
            s = m.run_blind(codes[name], zc, q / 100, frames, pp_rounds=ppr, collect=(ppr == 0))
            extra = ""
            if ppr == 0 and s["fail_usc"]:
                u = np.array(s["fail_usc"])
                extra = f" fails={len(u)} usc<=16:{int((u <= 16).sum())} med_usc={int(np.median(u))}"
            out.append(f"pp={ppr}: FER={s['fer']:.3f} f={s['f']:.2f} att={s['avg_attempts']:.2f} "
                       f"dec={s['avg_decodes']:.2f} it={s['avg_iters']:.0f} und={s['undetected']} "
                       f"pp_ok={s['pp_saved']}{extra}")
        print(f"zc={zc} {name} Q={q}% | " + " | ".join(out), flush=True)
