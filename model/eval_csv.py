"""
Error-correction evaluation on a BB84 simulation CSV (key_alice / key_bob columns).

Sifted keys of the same turbulence level are concatenated in test order and cut into IR blocks of n - d key bits
(n = 24 * ZC, d = round(DELTA * n) padding positions). Each block runs the basic blind reconciliation of the
golden model (bit-exact with the RTL): mother code chosen from the level's QBER estimate, reveal step d / 4.
Every block is also decoded with each of the 4 mother codes ("oracle" table) to show which code would work.

Usage: python eval_csv.py <csv> [--out-vectors ../data/csv] [--report ../results/csv_eval]
Writes: <report>.md (summary), <report>_blocks.csv, and TB vectors (same format as gen_vectors.py) so that
tb/tb_qkd_ir.v can replay the same blocks on the RTL (DATA_DIR=data/csv/).
"""
import argparse
import collections
import csv
import math
import os

import numpy as np

import ir_model as m
import layer_sched
import pa_model

ZC = 128
N = m.NCOL * ZC
DELTA = 0.10
D = int(round(DELTA * N))
NKEY = N - D
STEP = -(-D // 4)
ITER_MAX = 50
PP = (1, 2, 16)          # pp_rounds, pp_min_usc, pp_max_usc
ET = 12                  # early-termination patience (CFG2), 0 = off
CYC_PER_IT = {n: layer_sched.iteration_cycles(b) for n, b in m.load_codes(128).items()}   # overlapped layers
CLK_MHZ = 65.0           # post-route Fmax of the current build


def pick_code(qber):
    """Mother code from the QBER estimate (thresholds from the model sweeps)."""
    if qber <= 0.008:
        return "r56"
    if qber <= 0.022:
        return "r34"
    if qber <= 0.045:
        return "r23"
    return "r12"


def load_blocks(path):
    rows = list(csv.DictReader(open(path, newline="")))
    by_level = collections.OrderedDict()
    for r in sorted(rows, key=lambda r: (int(r["turb_level"]), int(r["test_id"]))):
        key = (int(r["turb_level"]), r["turb_name"])
        a, b = r["key_alice"].strip(), r["key_bob"].strip()
        assert len(a) == len(b), r["test_id"]
        lv = by_level.setdefault(key, {"a": [], "b": [], "tests": []})
        lv["a"].append(a)
        lv["b"].append(b)
        lv["tests"].append(int(r["test_id"]))
    blocks = []
    for (lvl, name), lv in by_level.items():
        a = np.frombuffer("".join(lv["a"]).encode(), dtype=np.uint8) - 48
        b = np.frombuffer("".join(lv["b"]).encode(), dtype=np.uint8) - 48
        q_level = float((a != b).mean())
        nblk = len(a) // NKEY
        for k in range(nblk):
            sl = slice(k * NKEY, (k + 1) * NKEY)
            blocks.append({"level": lvl, "name": name, "idx": k, "alice": a[sl].astype(np.int64),
                           "bob": b[sl].astype(np.int64), "q_level": q_level,
                           "q_block": float((a[sl] != b[sl]).mean()), "bits_level": len(a),
                           "unused": len(a) - nblk * NKEY})
    return blocks


def run_block(blk, base, seed, pos_d=None):
    """Basic blind reconciliation of one block. Returns per-attempt trace and summary."""
    rng = np.random.default_rng(seed)
    pos_d = rng.choice(N, D, replace=False) if pos_d is None else np.asarray(pos_d,dtype=np.int64)
    if len(pos_d)!=D or len(np.unique(pos_d))!=D or np.any(pos_d<0) or np.any(pos_d>=N):
        raise ValueError('invalid puncture positions')
    key_pos = np.setdiff1d(np.arange(N), pos_d)          # key bits fill the other positions in order
    v = np.zeros((1, N), dtype=np.int64)
    v[0, key_pos] = blk["alice"]
    v[0, pos_d] = rng.integers(0, 2, D)
    ch_bit = np.zeros((1, N), dtype=np.int64)
    ch_bit[0, key_pos] = blk["bob"]
    ch_type = np.zeros((1, N), dtype=np.int64)
    ch_type[0, pos_d] = m.T_PUNCT
    syn = m.syndrome(base, v.reshape(1, m.NCOL, ZC), ZC)
    sym0 = np.where(ch_type[0] == m.T_PUNCT, 2, ch_bit[0])

    trace, revs = [], []
    r = 0
    res = None
    while True:
        res = m.decode_attempt(ch_type, ch_bit, syn, base, ZC, ITER_MAX, m.LQ_DEFAULT, *PP, ET)
        ch_type = res["ch_type"]
        conv = bool(res["conv"][0])
        trace.append({"conv": conv, "pp": int(res["decodes"][0] - 1), "usc": int(res["n_usc"][0]),
                      "iters": int(res["iters"][0]), "nrev": 0})
        if conv or r >= D:
            break
        nxt = pos_d[r:r + STEP]
        r = min(D, r + STEP)
        ch_type[0, nxt] = m.T_SHORT
        ch_bit[0, nxt] = v[0, nxt]
        revs.extend(int(p) | (int(v[0, p]) << 16) for p in nxt)
        trace[-1]["nrev"] = len(nxt)

    hard = res["hard"][0]
    resid = int((hard[key_pos] != blk["alice"]).sum())
    conv = trace[-1]["conv"]
    errcnt = int((hard[key_pos] != blk["bob"]).sum()) if conv else 0     # what the RTL reports in ERRCNT
    mb = len(base)
    leak = mb * ZC - D + r
    hq = m.h2(blk["q_block"])
    return {
        "trace": trace, "revs": revs, "sym": sym0, "syn": syn[0], "hard": hard,
        "success": conv and resid == 0, "undetected": conv and resid > 0, "resid": resid,
        "attempts": len(trace), "revealed": r, "leak": leak,
        "rate": 1 - leak / NKEY, "f": leak / (NKEY * hq) if hq > 0 else float("inf"),
        "iters": sum(t["iters"] for t in trace), "errcnt": errcnt,
    }


def write_vectors(out_dir, b, blk, res, code_idx):
    os.makedirs(out_dir, exist_ok=True)
    sym, sbits = res["sym"], res["syn"].reshape(-1)

    def wr(name, vals, width):
        with open(os.path.join(out_dir, f"{name}_{b}.hex"), "w") as fh:
            fh.writelines(f"{v:0{width}x}\n" for v in vals)

    wr("ch", [sum(int(sym[t * 16 + k]) << (2 * k) for k in range(16)) for t in range(N // 16)], 8)
    wr("syn", [sum(int(sbits[t * 32 + k]) << k for k in range(32)) for t in range(len(sbits) // 32)], 8)
    cfg = code_idx | (m.LQ_DEFAULT << 2) | (ITER_MAX << 8) | (PP[0] << 16) | (PP[1] << 18) | (PP[2] << 20)
    lines = [cfg, ET, 0, len(res["trace"])]
    for t in res["trace"]:
        lines += [(int(t["conv"]) << 31) | (t["pp"] << 28) | (t["usc"] << 16) | t["iters"], t["nrev"]]
    lines.append(res["errcnt"])
    wr("blk", lines, 8)
    wr("rev", res["revs"] or [0], 8)
    hard = res["hard"]
    wr("key", [sum(int(hard[w * 64 + i]) << i for i in range(64)) for w in range(N // 64)], 16)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--out-vectors", default=os.path.join(here, "..", "data", "csv"))
    ap.add_argument("--report", default=os.path.join(here, "..", "results", "csv_eval"))
    args = ap.parse_args()

    codes = m.load_codes(ZC)
    blocks = load_blocks(args.csv)
    print(f"n={N}, d={D}, key bits/block={NKEY}, reveal step={STEP}, iter_max={ITER_MAX}, blocks={len(blocks)}")

    rows, oracle = [], []
    for b, blk in enumerate(blocks):
        name = pick_code(blk["q_level"])
        res = run_block(blk, codes[name], 1000 + b)
        write_vectors(args.out_vectors, b, blk, res, m.CODE_ORDER.index(name))
        t_us = sum(t["iters"] * CYC_PER_IT[name] + 300 for t in res["trace"]) / CLK_MHZ
        row = {"block": b, "level": blk["level"], "turb": blk["name"], "q_level_pct": round(100 * blk["q_level"], 2),
               "q_block_pct": round(100 * blk["q_block"], 2), "errors_in": int(round(blk["q_block"] * NKEY)),
               "code": name, "result": "SUCCESS" if res["success"] else ("UNDETECTED" if res["undetected"] else "DISCARD"),
               "attempts": res["attempts"], "revealed": res["revealed"], "iters": res["iters"],
               "pp_used": sum(t["pp"] for t in res["trace"]), "leak": res["leak"],
               "rate": round(res["rate"], 3), "f": round(res["f"], 2) if res["success"] else "",
               "resid_errors": res["resid"], "decoder_us_65MHz": round(t_us, 1),
               "trace": " ".join(f"[{'ok' if t['conv'] else 'fail'} it={t['iters']} usc={t['usc']} pp={t['pp']}]"
                                 for t in res["trace"])}
        rows.append(row)
        print(f"blk {b:2d} {blk['name']:8s} Q={100 * blk['q_block']:5.2f}% {name} -> {row['result']:9s} "
              f"att={res['attempts']} rev={res['revealed']:3d} f={row['f']} it={res['iters']} "
              f"resid={res['resid']} {row['trace']}", flush=True)
        # oracle: every mother code on the same block
        orow = {"block": b, "turb": blk["name"], "q_block_pct": round(100 * blk["q_block"], 2)}
        for cn in m.CODE_ORDER:
            o = res if cn == name else run_block(blk, codes[cn], 1000 + b)
            orow[cn] = (f"{o['attempts']} lần, f={o['f']:.2f}" if o["success"] else
                        ("SAI KHÔNG PHÁT HIỆN" if o["undetected"] else "hỏng"))
        oracle.append(orow)

    with open(os.path.join(args.out_vectors, "nblk.hex"), "w") as fh:
        fh.write(f"{len(blocks):x}\n")
    pa_model.write_vectors(args.out_vectors)
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report + "_blocks.csv", "w", newline="", encoding="utf8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # per-level summary
    lv = collections.OrderedDict()
    for row in rows:
        lv.setdefault((row["level"], row["turb"]), []).append(row)
    lines = [f"# Đánh giá sửa lỗi trên `{os.path.basename(args.csv)}`", "",
             f"n = {N}, d = {D}, {NKEY} bit key / khối, bước công bố {STEP} bit, iter_max {ITER_MAX}, "
             f"PP (rounds, min_usc, max_usc) = {PP}.", "",
             "| Mức | QBER mức | Khối | Code | Thành công | Lần thử TB | f TB | Lỗi còn lại |",
             "|---|---|---|---|---|---|---|---|"]
    for (lvl, name), rs in lv.items():
        ok = [r for r in rs if r["result"] == "SUCCESS"]
        att = sum(r["attempts"] for r in ok) / len(ok) if ok else float("nan")
        f = sum(r["f"] for r in ok) / len(ok) if ok else float("nan")
        lines.append(f"| {lvl} {name} | {rs[0]['q_level_pct']}% | {len(rs)} | {rs[0]['code']} | {len(ok)}/{len(rs)} | "
                     f"{att:.2f} | {f:.2f} | {sum(r['resid_errors'] for r in ok)} |")
    lines += ["", "## Từng khối", "", "| Khối | Mức | QBER khối | Code | Kết quả | Lần thử | Bit công bố | f | Vết |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['block']} | {r['turb']} | {r['q_block_pct']}% | {r['code']} | {r['result']} | {r['attempts']} | "
                     f"{r['revealed']} | {r['f']} | {r['trace']} |")
    lines += ["", "## Oracle: mọi mother code trên cùng khối", "", "| Khối | Mức | QBER | r12 | r23 | r34 | r56 |",
              "|---|---|---|---|---|---|---|"]
    for o in oracle:
        lines.append(f"| {o['block']} | {o['turb']} | {o['q_block_pct']}% | {o['r12']} | {o['r23']} | {o['r34']} | {o['r56']} |")
    with open(args.report + ".md", "w", encoding="utf8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines[:12]))
    print(f"report: {os.path.normpath(args.report)}.md, vectors: {os.path.normpath(args.out_vectors)}")


if __name__ == "__main__":
    main()
