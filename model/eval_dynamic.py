"""
Controller profiles on a BB84 CSV (blocks in time order), report for results/.

Usage: python eval_dynamic.py <csv> [--report ../results/csv_eval_dynamic]
Profiles: basic_old / dyn_old = state of 2026-10-10 (random D, offset min-sum); efficiency / throughput =
dyn_ir.PROFILES (GS positions, normalized min-sum). Throughput = reconciled key bits / (decoder time at CLK_MHZ +
one classical round trip per attempt); secret = x finite-size secret fraction (PA block 1 Mbit); eta = secret bits
per sifted bit.
"""
import argparse
import os

import dyn_ir as dy
import eval_csv as ev

CLK_MHZ = 100.0
RUNS = {"basic_old": ("basic", dict(gs=False, cn="oms", schedule="serial")),
        "dyn_old": ("dynamic", dict(gs=False, cn="oms", schedule="serial")),
        **dy.PROFILES}


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--report", default=os.path.join(here, "..", "results", "csv_eval_dynamic"))
    args = ap.parse_args()

    blocks = ev.load_blocks(args.csv)
    seq = [(b["alice"], b["bob"]) for b in blocks]
    runs = {name: dy.simulate(seq, mode, **kw) for name, (mode, kw) in RUNS.items()}

    L = [f"# Controller profiles on `{os.path.basename(args.csv)}`", "",
         f"n = {dy.N}, d = {dy.D}, {dy.NKEY} key bits/block, iter_max {dy.ITER_MAX}, PP {dy.PP}, ET {dy.ET}, "
         f"PE sample {dy.PE_SAMPLE} bits, 100 MHz. eta = secret bits per sifted bit (PA block 1 Mbit).", "",
         "| Profile | Success | f (successes) | Attempts / block | Iterations / block | eta | "
         "Mbit/s RTT 0 | RTT 100 us | secret Mbit/s RTT 0 | secret RTT 100 us |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, res in runs.items():
        s = dy.summarize(res, clk_mhz=CLK_MHZ)
        L.append(f"| {name} | {s['success']}/{s['blocks']} | {s['f']:.2f} | {s['attempts']:.2f} | {s['iters']:.1f} | "
                 f"{s['eta']:.3f} | {s['thr_0us']:.1f} | {s['thr_100us']:.1f} | {s['skr_0us']:.2f} | {s['skr_100us']:.2f} |")
    names = list(runs)
    L += ["", "## Per block (code / result / attempts / f)", "",
          "| # | Level | QBER | PE est. | " + " | ".join(names) + " |", "|---|---|---|---|" + "---|" * len(names)]
    for i, b in enumerate(blocks):
        def cell(r):
            res = "ok" if r["success"] else ("early discard" if r["attempts"] == 0 else "discard")
            f = f"{r['f']:.2f}" if r["success"] else "-"
            return f"{r['code']} / {res} / {r['attempts']} / {f}"
        r0 = runs[names[0]][i]
        L.append(f"| {i} | {b['name']} | {100 * r0['q_block']:.2f}% | {100 * r0['q_pe']:.2f}% | "
                 + " | ".join(cell(runs[n][i]) for n in names) + " |")
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report + ".md", "w", encoding="utf8") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L[:10]))
    print(f"report: {os.path.normpath(args.report)}.md")


if __name__ == "__main__":
    main()
