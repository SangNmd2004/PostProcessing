"""
Generate self-checking test vectors for tb/tb_qkd_ir.v from the golden model (decode_attempt).

Usage: python gen_vectors.py [out_dir]      (default ../data/tb)

Per block b:
  ch_<b>.hex   24*ZC/16 lines, 32-bit channel beats (16 symbols of 2 bit: 0/1 key bit, 2 punctured)
  syn_<b>.hex  mb*ZC/32 lines, 32-bit syndrome beats
  blk_<b>.hex  line 0: CFG register value, line 1: CFG2 register value (et, HOLD, NMS), line 2: pre-reveals,
               line 3: number of attempts A,
               then per attempt: expected {conv[31], pp_used[29:28], n_usc[27:16], iters[11:0]}, reveals after it,
               last line: expected ERRCNT (corrected channel errors, 0 if discarded)
  rev_<b>.hex  reveal register values {val[16], pos[15:0]} of all rounds, in order
  key_<b>.hex  24*ZC/64 lines, 64-bit words of the final hard decision (zeros if the block is discarded)
  nblk.hex     number of blocks
"""
import os
import sys

import numpy as np

import ir_model as m
import pa_model
import puncture as pu

ZC = 128
HERE = os.path.dirname(os.path.abspath(__file__))

# (code index, QBER, iter_max, pp_rounds, pp_min_usc, pp_max_usc, seed, et_patience, pre-reveals in HOLD mode,
#  check node: 1 normalized min-sum x0.75 (CFG2[5]) / 0 offset min-sum). D = puncture.order (GS) of the code.
BLOCKS = [
    (2, 0.010, 30, 1, 2, 16, 11, 12, 0, 1),       # r34, easy: first attempt
    (2, 0.025, 30, 1, 2, 16, 12, 12, 0, 1),       # r34, needs reveals
    (1, 0.040, 20, 2, 2, 4095, 13, 0, 0, 1),      # r23, post-processing forced on every failure (datapath test), no ET
    (3, 0.030, 15, 1, 2, 16, 14, 12, 0, 1),       # r56, too noisy: discarded after the last attempt
    (0, 0.050, 30, 1, 2, 16, 15, 12, 0, 0),       # r12, offset min-sum
    (1, 0.045, 20, 1, 3, 4095, 16, 12, 0, 1),     # r23, post-processing with min_usc = 3
    (2, 0.030, 50, 1, 2, 16, 17, 4, 0, 1),        # r34 far above its window: early termination cuts every attempt
    (0, 0.080, 50, 1, 2, 16, 18, 8, 0, 1),        # r12 near its limit with ET = 8
    (2, 0.022, 50, 1, 2, 16, 19, 12, 200, 0),     # dynamic mode: HOLD, 200 bits revealed with the syndrome, OMS
]
DELTA = 0.10
REVEAL_ROUNDS = 2                       # d is revealed in 2 steps -> at most 3 attempts


def cfg_word(code, lq, iter_max, ppr, ppmin, ppmax):
    return code | (lq << 2) | (iter_max << 8) | (ppr << 16) | (ppmin << 18) | (ppmax << 20)


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    codes = m.load_codes(ZC)
    names = m.CODE_ORDER
    n = m.NCOL * ZC
    for b, (ci, q, iter_max, ppr, ppmin, ppmax, seed, et, npre, nms) in enumerate(BLOCKS):
        base = codes[names[ci]]
        rng = np.random.default_rng(seed)
        m.CN_MODE = "nms75" if nms else "oms"
        d = int(round(DELTA * n))
        blk = m.make_blocks(ZC, base, q, 1, DELTA, rng, pu.order(names[ci], base, ZC, d))
        d, pos_d = blk["d"], blk["pos_d"]
        step = -(-d // REVEAL_ROUNDS)
        ch_type, ch_bit, syn = blk["ch_type"], blk["ch_bit"], blk["syn"]

        # channel / syndrome streams
        sym = np.where(ch_type[0] == m.T_PUNCT, 2, ch_bit[0])
        ch_beats = [sum(int(sym[t * 16 + k]) << (2 * k) for k in range(16)) for t in range(n // 16)]
        sbits = syn[0].reshape(-1)
        syn_beats = [sum(int(sbits[t * 32 + k]) << k for k in range(32)) for t in range(len(sbits) // 32)]

        exp, revs, nrev = [], [], []
        r = 0
        if npre:                                  # HOLD mode: first npre positions of D revealed before attempt 1
            nxt = pos_d[:npre]
            r = npre
            ch_type[0, nxt] = m.T_SHORT
            ch_bit[0, nxt] = blk["v"][0, nxt]
            revs.extend(int(p) | (int(blk["v"][0, p]) << 16) for p in nxt)
        hard = np.zeros(n, dtype=np.int64)
        while True:
            res = m.decode_attempt(ch_type, ch_bit, syn, base, ZC, iter_max, m.LQ_DEFAULT, ppr, ppmin, ppmax, et)
            ch_type = res["ch_type"]
            conv = bool(res["conv"][0])
            exp.append((int(conv) << 31) | (int(res["decodes"][0] - 1) << 28) | (int(res["n_usc"][0]) << 16)
                       | int(res["iters"][0]))
            if conv:
                hard = res["hard"][0]
                nrev.append(0)
                break
            if r >= d:
                nrev.append(0)
                break
            nxt = pos_d[r:r + step]
            r = min(d, r + step)
            ch_type[0, nxt] = m.T_SHORT
            ch_bit[0, nxt] = blk["v"][0, nxt]
            revs.extend(int(p) | (int(blk["v"][0, p]) << 16) for p in nxt)
            nrev.append(len(nxt))

        words = [sum(int(hard[w * 64 + i]) << i for i in range(64)) for w in range(n // 64)]
        key_mask = np.ones(n, dtype=bool)
        key_mask[pos_d] = False
        errcnt = int((hard[key_mask] != ch_bit[0][key_mask]).sum()) if conv else 0
        if conv:
            assert np.array_equal(hard[key_mask], blk["v"][0][key_mask]), "golden decode converged to a wrong key"

        def wr(name, vals, width):
            with open(os.path.join(out_dir, f"{name}_{b}.hex"), "w") as fh:
                fh.writelines(f"{v:0{width}x}\n" for v in vals)

        wr("ch", ch_beats, 8)
        wr("syn", syn_beats, 8)
        blk_lines = [cfg_word(ci, m.LQ_DEFAULT, iter_max, ppr, ppmin, ppmax), et | (16 if npre else 0) | (32 * nms),
                     npre, len(exp)]
        for e, k in zip(exp, nrev):
            blk_lines += [e, k]
        blk_lines.append(errcnt)
        wr("blk", blk_lines, 8)
        wr("rev", revs or [0], 8)
        wr("key", words, 16)
        att = ", ".join(f"[conv={e >> 31} pp={(e >> 28) & 3} usc={(e >> 16) & 0xFFF} it={e & 0xFFF}]" for e in exp)
        print(f"block {b}: code={names[ci]} Q={q:.3f} et={et} cn={m.CN_MODE} d={d} attempts={len(exp)} {att} -> "
              f"{'SUCCESS' if conv else 'DISCARD'}")
    m.CN_MODE = "oms"
    with open(os.path.join(out_dir, "nblk.hex"), "w") as fh:
        fh.write(f"{len(BLOCKS):x}\n")
    pa_model.write_vectors(out_dir)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "data", "tb"))
