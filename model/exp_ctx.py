"""
Throughput of the IR core with K block contexts sharing one decoder (option C, 2026-10-23), evaluated BEFORE the
RTL change.

Discrete-event model. Each block needs `attempts` rounds; a round = classical round trip RTT (Alice's syndrome or
reveals) followed by one decoder run (iterations of that attempt x cycles per iteration of the code + per-attempt
overhead, dyn_ir timing model, overlapped layer schedule). With K contexts, up to K blocks are in flight: while one
block waits for Alice, the decoder runs attempts of the others (FIFO). After a success the key is streamed out
(KEY_OUT_CYC, decoder blocked) and the context loads the next block (LOAD_CYC, overlaps the decoder).
K = 1 is the current core.
Blocks: the decoded traces (attempts / iterations / code) of the EFFICIENCY profile on the simulated sessions.
Usage: python exp_ctx.py [--blocks 120] [--out ../results/exp_ctx.md]
"""
import argparse
import heapq
import os

import numpy as np

import dyn_ir as dy
import eval_sessions as es

CLK_MHZ = 100.0
KEY_OUT_CYC = 120          # 48 key words + row fetches, decoder held
LOAD_CYC = 260             # 192 channel beats + syndrome beats at one beat per cycle
KS = [1, 2, 3, 4, 6, 8]


def traces(level, nblk):
    d, _ = es.load(os.path.join(es.os.path.dirname(os.path.abspath(__file__)), "..", "data", "sessions",
                                f"session_{level}"))
    blk = es.blocks_of(d)[:nblk]
    mode, kw = dy.PROFILES["efficiency"]
    res = dy.simulate([(a, b, pe) for a, b, pe, _ in blk], mode, **kw)
    out = []
    for r in res:
        if r["code"] == "-":
            continue
        cyc = [t["iters"] * dy.CYC_PER_IT["overlap"][r["code"]] + dy.CYC_ATTEMPT * (t["pp"] + 1) for t in r["trace"]]
        out.append(cyc)
    return out


def simulate(blocks, k, rtt_us):
    """Returns blocks per second."""
    rtt = rtt_us * CLK_MHZ                     # in cycles
    events = []                                # (time, seq, kind, ctx)
    seq = 0
    nxt = 0                                    # next block index to load
    state = {}                                 # ctx -> [block idx, round]
    ready = []                                 # FIFO of ctx waiting for the decoder
    t_dec_free = 0.0
    done = 0
    t_end = 0.0
    for c in range(min(k, len(blocks))):
        state[c] = [nxt, 0]
        nxt += 1
        heapq.heappush(events, (LOAD_CYC + rtt, seq, "ready", c)); seq += 1
    while events:
        t, _, kind, c = heapq.heappop(events)
        if kind == "ready":
            ready.append(c)
        elif kind == "dec_done":
            bi, rnd = state[c]
            if rnd + 1 < len(blocks[bi]):        # failed attempt: ask Alice, come back after RTT
                state[c] = [bi, rnd + 1]
                heapq.heappush(events, (t + rtt, seq, "ready", c)); seq += 1
            else:                                # success: key out (decoder held), load the next block
                t_dec_free = t + KEY_OUT_CYC
                heapq.heappush(events, (t_dec_free, seq, "free", -1)); seq += 1
                done += 1
                t_end = t + KEY_OUT_CYC
                if nxt < len(blocks):
                    state[c] = [nxt, 0]
                    nxt += 1
                    heapq.heappush(events, (t + KEY_OUT_CYC + LOAD_CYC + rtt, seq, "ready", c)); seq += 1
        # dispatch one attempt when the decoder is free (it is busy until t_dec_free)
        if ready and t_dec_free <= t:
            c2 = ready.pop(0)
            bi, rnd = state[c2]
            t_dec_free = t + blocks[bi][rnd]
            heapq.heappush(events, (t_dec_free, seq, "dec_done", c2)); seq += 1
    return done / (t_end / (CLK_MHZ * 1e6))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", type=int, default=120)
    ap.add_argument("--out", default=os.path.join(here, "..", "results", "exp_ctx.md"))
    args = ap.parse_args()
    L = ["# Block contexts sharing one decoder (option C): reconciled-key throughput before the RTL change", "",
         f"Discrete-event model, 100 MHz, EFFICIENCY profile traces of the first {args.blocks} blocks of each "
         "simulated session; Mbit/s of reconciled key (2765 bits per block).", "",
         "| Session | RTT | " + " | ".join(f"K = {k}" for k in KS) + " | decoder-only limit |",
         "|---|---|" + "---|" * len(KS) + "---|"]
    for lv in ("weak", "moderate", "severe"):
        bl = traces(lv, args.blocks)
        dec_only = len(bl) * dy.NKEY / (sum(sum(b) + KEY_OUT_CYC for b in bl) / (CLK_MHZ * 1e6)) / 1e6
        for rtt in (100.0, 1000.0):
            cells = [f"{simulate(bl, k, rtt) * dy.NKEY / 1e6:.1f}" for k in KS]
            L.append(f"| {lv} | {rtt:.0f} us | " + " | ".join(cells) + f" | {dec_only:.0f} |")
            print(L[-1], flush=True)
    with open(args.out, "w", encoding="utf8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
