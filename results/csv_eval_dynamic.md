# Controller profiles on `bb84_key_test_Sim_20260618_002028.csv`

n = 3072, d = 307, 2765 key bits/block, iter_max 50, PP (1, 2, 16), ET 12, PE sample 256 bits, 100 MHz. eta = secret bits per sifted bit (PA block 1 Mbit).

| Profile | Success | f (successes) | Attempts / block | Iterations / block | eta | Mbit/s RTT 0 | RTT 100 us | secret Mbit/s RTT 0 | secret RTT 100 us |
|---|---|---|---|---|---|---|---|---|---|
| basic_old | 10/16 | 1.91 | 3.62 | 101.9 | 0.245 | 6.0 | 2.7 | 2.35 | 1.04 |
| dyn_old | 10/16 | 2.12 | 0.81 | 14.6 | 0.231 | 47.0 | 14.6 | 17.35 | 5.40 |
| efficiency | 10/16 | 1.55 | 1.06 | 25.3 | 0.265 | 31.0 | 10.7 | 13.14 | 4.52 |
| throughput | 10/16 | 2.48 | 0.62 | 4.2 | 0.202 | 161.8 | 23.6 | 52.33 | 7.64 |

## Per block (code / result / attempts / f)

| # | Level | QBER | PE est. | basic_old | dyn_old | efficiency | throughput |
|---|---|---|---|---|---|---|---|
| 0 | WEAK | 0.33% | 0.78% | r56 / ok / 2 / 3.23 | r56 / ok / 1 / 3.72 | r56 / ok / 1 / 2.35 | r34 / ok / 1 / 5.28 |
| 1 | WEAK | 0.33% | 0.00% | r56 / ok / 2 / 3.23 | r56 / ok / 2 / 3.64 | r56 / ok / 1 / 2.35 | r56 / ok / 1 / 2.35 |
| 2 | WEAK | 0.33% | 0.78% | r56 / ok / 2 / 3.23 | r56 / ok / 1 / 3.79 | r56 / ok / 1 / 2.35 | r34 / ok / 1 / 5.28 |
| 3 | MILD | 3.94% | 2.73% | r23 / ok / 4 / 1.43 | r23 / ok / 2 / 1.38 | r23 / ok / 2 / 1.20 | r12 / ok / 1 / 1.85 |
| 4 | MILD | 3.36% | 3.52% | r23 / ok / 3 / 1.48 | r23 / ok / 1 / 1.53 | r23 / ok / 1 / 1.22 | r12 / ok / 1 / 2.09 |
| 5 | MILD | 3.33% | 2.34% | r23 / ok / 3 / 1.50 | r34 / ok / 2 / 1.32 | r23 / ok / 1 / 1.23 | r12 / ok / 1 / 2.11 |
| 6 | MILD | 3.91% | 3.91% | r23 / ok / 3 / 1.32 | r12 / ok / 1 / 1.87 | r23 / ok / 2 / 1.21 | r12 / ok / 1 / 1.87 |
| 7 | MODERATE | 8.93% | 8.59% | r12 / ok / 3 / 1.15 | r12 / ok / 1 / 1.28 | r12 / ok / 4 / 1.22 | r12 / ok / 1 / 1.28 |
| 8 | MODERATE | 7.59% | 9.77% | r12 / ok / 3 / 1.29 | r12 / ok / 1 / 1.43 | r12 / ok / 2 / 1.22 | r12 / ok / 1 / 1.43 |
| 9 | MODERATE | 8.35% | 7.81% | r12 / ok / 3 / 1.21 | r12 / ok / 1 / 1.25 | r12 / ok / 2 / 1.14 | r12 / ok / 1 / 1.25 |
| 10 | STRONG | 12.33% | 13.28% | r12 / discard / 5 / - | - / early discard / 0 / - | - / early discard / 0 / - | - / early discard / 0 / - |
| 11 | STRONG | 11.75% | 11.72% | r12 / discard / 5 / - | - / early discard / 0 / - | - / early discard / 0 / - | - / early discard / 0 / - |
| 12 | STRONG | 11.07% | 11.72% | r12 / discard / 5 / - | - / early discard / 0 / - | - / early discard / 0 / - | - / early discard / 0 / - |
| 13 | SEVERE | 12.59% | 14.45% | r12 / discard / 5 / - | - / early discard / 0 / - | - / early discard / 0 / - | - / early discard / 0 / - |
| 14 | SEVERE | 14.29% | 13.67% | r12 / discard / 5 / - | - / early discard / 0 / - | - / early discard / 0 / - | - / early discard / 0 / - |
| 15 | SEVERE | 13.16% | 17.19% | r12 / discard / 5 / - | - / early discard / 0 / - | - / early discard / 0 / - | - / early discard / 0 / - |
