"""
Two figures of merit, two operating modes of the firmware controller (2026-10-11).

  eta    = secret bits per sifted key bit (finite-size PA block 1 Mbit). Maximised when the post-processor is
           NOT the bottleneck (raw key rate < IR capacity, alpha = 1 in Kprac of Yang et al. 2020): "efficiency".
  skr100 = secret Mbit/s at RTT 100 us, 100 MHz. Maximised when raw key piles up (alpha < 1): "throughput".

Every configuration runs on the same drifting sequence as exp_tune.py (QBER 1 -> 6 -> 1 %).
Usage: python exp_mode.py [--per-level 6] [--out ../results/exp_mode.txt]
"""
import argparse
import os
from multiprocessing import Pool

import dyn_ir as dy
import exp_tune as et

CONFIGS = {
    "basic_old (10-10)":            ("basic", dict(gs=False, cn="oms", schedule="serial")),
    "dyn_old (10-10)":              ("dynamic", dict(gs=False, cn="oms", schedule="serial")),
    "basic gs nms":                 ("basic", dict(gs=True, cn="nms75")),
    "basic gs nms step16":          ("basic", dict(gs=True, cn="nms75", basic_step=16)),
    "dyn gs nms fs1.7 z1.0 ft1.15": ("dynamic", dict(gs=True, cn="nms75", f_safe=1.7, pe_z=1.0, f_target=1.15)),
    "dyn gs nms fs1.7 z0.5 ft1.05": ("dynamic", dict(gs=True, cn="nms75", f_safe=1.7, pe_z=0.5, f_target=1.05,
                                                     f_min=1.0, alpha=0.5, delta_min=8)),
    "dyn gs nms fs1.7 z1.0 ft1.05": ("dynamic", dict(gs=True, cn="nms75", f_safe=1.7, pe_z=1.0, f_target=1.05,
                                                     f_min=1.0, alpha=0.5, delta_min=8)),
    "dyn gs nms fs1.7 z0 ft1.1":    ("dynamic", dict(gs=True, cn="nms75", f_safe=1.7, pe_z=0.0, f_target=1.1,
                                                     f_min=1.0, alpha=0.5, delta_min=8)),
    "dyn gs nms fs1.7 z1.5 ft1.3":  ("dynamic", dict(gs=True, cn="nms75", f_safe=1.7, pe_z=1.5, f_target=1.3)),
}


def run(args):
    name, per_level = args
    mode, kw = CONFIGS[name]
    s = dy.summarize(dy.simulate(et.sequence(per_level), mode, **kw))
    return (f"{name:30} {s['success']:>3}/{s['blocks']:<2} {s['f']:5.2f} {s['attempts']:5.2f} {s['iters']:6.1f} "
            f"{s['eta']:6.3f} {s['thr_100us']:6.1f} {s['skr_0us']:6.2f} {s['skr_100us']:6.2f} {s['skr_1000us']:6.3f}")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-level", type=int, default=6)
    ap.add_argument("--out", default=os.path.join(here, "..", "results", "exp_mode.txt"))
    args = ap.parse_args()
    lines = [f"QBER levels {et.LEVELS} x {args.per_level} blocks; eta = secret bits / sifted bit (PA block 1 Mbit)",
             f"{'config':30} {'ok':>6} {'f':>5} {'att':>5} {'it':>6} {'eta':>6} {'thr100':>6} {'skr0':>6} "
             f"{'skr100':>6} {'skr1ms':>6}"]
    with Pool(min(len(CONFIGS), os.cpu_count() or 4)) as pool:
        lines += pool.map(run, [(n, args.per_level) for n in CONFIGS])
    print("\n".join(lines))
    with open(args.out, "w", encoding="utf8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
