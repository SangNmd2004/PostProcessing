"""Basic vs dynamic blind reconciliation on (a) the BB84 CSV in time order, (b) a synthetic drifting-QBER run.
Throughput = reconciled key bits / (decoder time at 100 MHz + one classical round trip per attempt).
Usage: python exp_dyn.py <csv> [n_synth]"""
import sys

import numpy as np

import dyn_ir as dy
import eval_csv as ev


def synth_sequence(nblk, seed=7):
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 1, nblk)
    q = 0.01 + 0.05 * np.sin(np.pi * t) ** 2 + rng.normal(0, 0.003, nblk)   # 1% -> 6% -> 1%
    seq = []
    for qq in np.clip(q, 0.002, 0.2):
        a = rng.integers(0, 2, dy.NKEY)
        seq.append((a, a ^ (rng.random(dy.NKEY) < qq).astype(np.int64)))
    return seq


def line(tag, res):
    s = dy.summarize(res)
    return (f"{tag:38s} ok {s['success']:2d}/{s['blocks']}  f={s['f']:.2f}  att={s['attempts']:.2f}  "
            f"it={s['iters']:5.1f}  net={s['net_bits']:6d} bit  thr@100MHz: RTT0 {s['thr_0us']:5.1f} | "
            f"RTT100us {s['thr_100us']:5.1f} | RTT1ms {s['thr_1000us']:5.2f} Mbit/s")


def main():
    csv_path = sys.argv[1]
    nsyn = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    blocks = ev.load_blocks(csv_path)
    seq_csv = [(b["alice"], b["bob"]) for b in blocks]
    seq_syn = synth_sequence(nsyn)
    for name, seq in (("CSV (WEAK->SEVERE, 16 blk)", seq_csv), (f"synthetic drift 1-6-1% ({nsyn} blk)", seq_syn)):
        print(f"=== {name}")
        print(line("basic", dy.simulate(seq, "basic")), flush=True)
        for z in (0.0, 0.5, 1.0):
            for ft in (1.15, 1.3):
                for al in (0.5, 1.0):
                    print(line(f"dynamic pe_z={z} f*={ft} alpha={al}",
                               dy.simulate(seq, "dynamic", pe_z=z, f_target=ft, alpha=al)), flush=True)


if __name__ == "__main__":
    main()
