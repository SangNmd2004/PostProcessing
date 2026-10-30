"""
Abort rule + PA block accumulation: old (one PA block per ~1.2 Mbit session, discarded when ell <= 0) vs new
(pa_accum.PAAccumulator) on hours of simulated link (gen_qkd_session.Session, 1 s chunks).

IR surrogate (running the bit-exact IR on 1e7-1e8 bits would take hours): per 1 s chunk, the reconciliation
efficiency f(q) and block success rate of the EFFICIENCY profile are interpolated from the measured BSC sweep
(results/exp_compare.txt, rows "efficiency"); failed blocks lose their key bits; leak_EC = f h(q) n + 64 bits per
block of NKEY. Chunks whose test-basis QBER exceeds 11 % are dropped (key and test data of that span).

Scenarios: STRONG / SEVERE 3 h, MODERATE 1 h, and MIXED (the channel changes: WEAK 5 min, STRONG 1 h, MODERATE
30 min, SEVERE 30 min, MILD 15 min).
Usage: python exp_accum.py [--out ../results/exp_accum.md]
"""
import argparse
import math
import os
import re
from multiprocessing import Pool

import numpy as np

import dyn_ir as dy
import gen_qkd_session as g
import ir_model as m
import pa_accum as acc

HERE = os.path.dirname(os.path.abspath(__file__))
SCENARIOS = {
    "STRONG 3 h": [("STRONG", 10800)],
    "SEVERE 3 h": [("SEVERE", 10800)],
    "MODERATE 1 h": [("MODERATE", 3600)],
    "MIXED 2 h 20": [("WEAK", 300), ("STRONG", 3600), ("MODERATE", 1800), ("SEVERE", 1800), ("MILD", 900)],
}
OLD_BLOCK = 1_200_000
POLICIES = {"old": None, "new": {}, "new, no age limit": {"max_age_s": 1e18}}


def ir_table():
    """(QBER, f, success rate) of the EFFICIENCY profile from results/exp_compare.txt."""
    rows = []
    with open(os.path.join(HERE, "..", "results", "exp_compare.txt"), encoding="utf8") as fh:
        for line in fh:
            mm = re.match(r"\s*([\d.]+)% efficiency\s+(\d+)/(\d+)\s+\d+\s+([\d.]+)", line)
            if mm:
                rows.append((float(mm.group(1)) / 100, float(mm.group(4)), int(mm.group(2)) / int(mm.group(3))))
    return sorted(rows)


def chunks(scenario, seed=11):
    """Yield (t_end_s, level, per-chunk stats) for every 1 s of link time."""
    t = 0
    for i, (lv, secs) in enumerate(SCENARIOS[scenario]):
        s = g.Session(lv, seed=seed + 31 * i)
        for _ in range(secs):
            c = s.chunk(1.0)
            t += 1
            z, x = c["basis"] == 0, c["basis"] == 1
            e = c["a"] != c["b"]
            yield t, lv, {
                "nk": [int((z & (c["k"] == k)).sum()) for k in range(3)],
                "ek": int((z & e).sum()),
                "nt": [int((x & (c["k"] == k)).sum()) for k in range(3)],
                "mt": [int((x & e & (c["k"] == k)).sum()) for k in range(3)],
            }, s.p


def run(scenario):
    tab = ir_table()
    qs, fs, oks = (np.array([r[i] for r in tab]) for i in range(3))
    rng = np.random.default_rng(5)
    res = {}
    for policy, kw in POLICIES.items():
        rng = np.random.default_rng(5)
        a = None
        emitted, n_emit, discarded, first, blocks = 0, 0, 0, None, []
        for t, lv, st, p in chunks(scenario):
            if a is None:
                a = acc.PAAccumulator(p["MU"], p["P_K"], **(kw or {}))
            n = sum(st["nk"])
            ntt = sum(st["nt"])
            if n == 0 or ntt == 0:
                continue
            q_test = sum(st["mt"]) / ntt
            if q_test > acc.Q_BLOCK_MAX:
                discarded += n
                continue
            q = st["ek"] / n
            f = float(np.interp(q, qs, fs))
            ok = float(np.interp(q, qs, oks))
            keep = int(rng.binomial(n, ok))
            discarded += n - keep
            nk = [int(round(x * keep / n)) for x in st["nk"]]
            leak = int(f * m.h2(q) * keep) + 64 * math.ceil(keep / dy.NKEY)
            a.add(nk, st["nt"], st["mt"], leak, t)
            if policy == "old":
                if a.n >= OLD_BLOCK:
                    ell = a.lengths()[0]
                    if ell > 0:
                        emitted += ell
                        n_emit += 1
                        blocks.append(a.n)
                        first = first or t
                    else:
                        discarded += a.n
                    a.reset()
            else:
                act, ell, asym, why = a.decide(t)
                if act == "emit":
                    emitted += ell
                    n_emit += 1
                    blocks.append(a.emit_n)
                    first = first or t
                    a.emitted()
                elif act == "abort":
                    discarded += a.n
                    a.reset()
        res[policy] = {"secret": emitted, "emits": n_emit, "avg_block": float(np.mean(blocks)) if blocks else 0.0,
                       "discarded": discarded, "pending": a.n if a else 0,
                       "pending_ell": max(0, a.lengths()[0]) if a else 0, "first_s": first, "t_s": t}
    return scenario, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "..", "results", "exp_accum.md"))
    args = ap.parse_args()
    with Pool(len(SCENARIOS)) as pool:
        out = pool.map(run, list(SCENARIOS))
    L = ["# Abort rule and PA accumulation (simulated link, IR surrogate from results/exp_compare.txt)", "",
         "old: PA block = 1.2 Mbit of reconciled key, discarded when its finite-key length <= 0. "
         "new: pa_accum.PAAccumulator (emit when doubling the block would gain < 10 %, near the asymptotic fraction, "
         "at 16 Mbit, after 1 h, or at its best point when the channel degrades; abort only when the asymptotic fraction <= 0). Lim 2014 finite key, eps_sec 1e-9.", "",
         "| Scenario | Rule | Secret bits | Secret bit/s | PA blocks | Avg block (Mbit) | Discarded key bits | "
         "Pending at end (its ell) | First key after |", "|---|---|---|---|---|---|---|---|---|"]
    for sc, res in out:
        for pol in POLICIES:
            r = res[pol]
            first = f"{r['first_s'] / 60:.0f} min" if r["first_s"] else "never"
            L.append(f"| {sc} | {pol} | {r['secret']} | {r['secret'] / r['t_s']:.1f} | {r['emits']} | "
                     f"{r['avg_block'] / 1e6:.1f} | {r['discarded']} | {r['pending']} ({r['pending_ell']}) | {first} |")
    print("\n".join(L))
    with open(args.out, "w", encoding="utf8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
