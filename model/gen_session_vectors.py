"""
RTL replay vectors from the physically simulated decoy-BB84 sessions (data/sessions, gen_qkd_session.py).

Per session, BLOCKS_PER_SESSION key-basis blocks spread over the session are reconciled exactly as the firmware
would (dyn_ir.one_block, GS positions, normalized min-sum, QBER estimate from the test-basis bits of the same time
window): the first EFF_BLOCKS with the EFFICIENCY profile (basic blind, r0 = 0), the others with THROUGHPUT
(dynamic, r0 pre-reveals in HOLD mode). Blocks discarded before decoding (estimate > 11 %) are skipped.
The golden results are written in the tb/tb_qkd_ir.v format (same as gen_vectors.py) plus one PA job.

Usage: python gen_session_vectors.py [--out ../data/sessions_tb] [--per-session 6]
Then:  vsim -c -do sim/run_sim.do  with DATA_DIR = data/sessions_tb/
"""
import argparse
import os

import numpy as np

import dyn_ir as dy
import eval_sessions as es
import ir_model as m
import pa_model

ORDER = ["weak", "mild", "moderate", "strong", "severe"]


def write_block(out_dir, b, res):
    n = dy.N
    sym, sbits = res["sym"], np.asarray(res["syn"]).reshape(-1)

    def wr(name, vals, width):
        with open(os.path.join(out_dir, f"{name}_{b}.hex"), "w") as fh:
            fh.writelines(f"{v:0{width}x}\n" for v in vals)

    wr("ch", [sum(int(sym[t * 16 + k]) << (2 * k) for k in range(16)) for t in range(n // 16)], 8)
    wr("syn", [sum(int(sbits[t * 32 + k]) << k for k in range(32)) for t in range(len(sbits) // 32)], 8)
    ci = m.CODE_ORDER.index(res["code"])
    cfg = ci | (m.LQ_DEFAULT << 2) | (dy.ITER_MAX << 8) | (dy.PP[0] << 16) | (dy.PP[1] << 18) | (dy.PP[2] << 20)
    npre = int(res["pre"])
    cfg2 = dy.ET | (16 if npre else 0) | 32                                  # ET, HOLD, NMS
    lines = [cfg, cfg2, npre, len(res["trace"])]
    for t in res["trace"]:
        lines += [(int(t["conv"]) << 31) | (t["pp"] << 28) | (t["usc"] << 16) | t["iters"], t["nrev"]]
    lines.append(res["errcnt"])
    assert len(lines) <= 32, "tb blk_mem holds at most 13 attempts"
    wr("blk", lines, 8)
    wr("rev", res["revs"] or [0], 8)
    hard = res["hard"] if res["success"] or res["undetected"] else np.zeros(n, dtype=np.int64)
    wr("key", [sum(int(hard[w * 64 + i]) << i for i in range(64)) for w in range(n // 64)], 16)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", default=os.path.join(here, "..", "data", "sessions"))
    ap.add_argument("--out", default=os.path.join(here, "..", "data", "sessions_tb"))
    ap.add_argument("--per-session", type=int, default=6)
    ap.add_argument("--eff-blocks", type=int, default=4)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    codes = m.load_codes(dy.ZC)
    m.CN_MODE = "nms75"
    b = 0
    rows = []
    for lv in ORDER:
        d, meta = es.load(os.path.join(args.sessions, f"session_{lv}"))
        blk = es.blocks_of(d)
        pick = np.linspace(0, len(blk) - 1, args.per_session).astype(int)
        ctrls = {}
        for p, (mode, kw) in dy.PROFILES.items():
            kw = {k: v for k, v in kw.items() if k not in ("gs", "cn")}
            ctrls[p] = dy.Controller(mode=mode, **kw)
        for j, i in enumerate(pick):
            prof = "efficiency" if j < args.eff_blocks else "throughput"
            a, bob, pe, _ = blk[i]
            res = dy.one_block(int(i), a, bob, ctrls[prof], codes, gs=True, collect_vectors=True, pe=pe)
            if res["code"] == "-":
                rows.append((None, lv, int(i), prof, pe[0], res))
                continue
            write_block(args.out, b, res)
            rows.append((b, lv, int(i), prof, pe[0], res))
            b += 1
    m.CN_MODE = "oms"
    with open(os.path.join(args.out, "nblk.hex"), "w") as fh:
        fh.write(f"{b:x}\n")
    pa_model.write_vectors(args.out)
    with open(os.path.join(args.out, "blocks.txt"), "w", encoding="utf8") as fh:
        fh.write("tb_block level session_block profile q_est q_block code pre attempts iters result model_cycles\n")
        for tb, lv, i, prof, qe, r in rows:
            res = "early-discard" if tb is None else ("SUCCESS" if r["success"] else
                                                     ("UNDETECTED" if r["undetected"] else "DISCARD"))
            fh.write(f"{'-' if tb is None else tb} {lv} {i} {prof} {qe:.4f} {r['q_block']:.4f} {r['code']} "
                     f"{r.get('pre', 0)} {r['attempts']} {r['iters']} {res} {r['cycles']}\n")
    print(open(os.path.join(args.out, "blocks.txt"), encoding="utf8").read())


if __name__ == "__main__":
    main()
