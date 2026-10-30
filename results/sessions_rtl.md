# IR on the RTL with the simulated decoy-BB84 sessions

`model/gen_session_vectors.py` -> `data/sessions_tb/` (6 blocks spread over each session of `data/sessions`, 4 EFFICIENCY + 2 THROUGHPUT, QBER estimate from the test-basis bits of the same window), replayed by `tb/tb_qkd_ir.v` in ModelSim: **TB_RESULT: PASS (30 IR blocks + 1 PA pass bit-exact vs golden model)**.

| TB block | Level | Profile | QBER est. / true | Code | Pre-reveals | Attempts | Iterations | Result | RTL cycles | Model cycles |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | weak | efficiency | 1.24% / 1.52% | r34 | 0 | 1 | 9 | SUCCESS | 2094 | 2019 |
| 1 | weak | efficiency | 1.60% / 1.45% | r34 | 0 | 1 | 7 | SUCCESS | 1730 | 1637 |
| 2 | weak | efficiency | 1.61% / 2.10% | r34 | 0 | 2 | 40 | SUCCESS | 8572 | 8240 |
| 3 | weak | efficiency | 1.54% / 1.59% | r34 | 0 | 1 | 9 | SUCCESS | 2098 | 2019 |
| 4 | weak | throughput | 1.79% / 1.41% | r34 | 80 | 1 | 5 | SUCCESS | 1747 | 1255 |
| 5 | weak | throughput | 1.52% / 1.37% | r34 | 11 | 1 | 7 | SUCCESS | 1781 | 1637 |
| 6 | mild | efficiency | 2.18% / 2.13% | r34 | 0 | 2 | 38 | SUCCESS | 8184 | 7858 |
| 7 | mild | efficiency | 2.16% / 1.63% | r34 | 0 | 1 | 13 | SUCCESS | 2864 | 2783 |
| 8 | mild | efficiency | 1.93% / 1.88% | r34 | 0 | 2 | 28 | SUCCESS | 6291 | 5948 |
| 9 | mild | efficiency | 1.90% / 1.30% | r34 | 0 | 1 | 8 | SUCCESS | 1908 | 1828 |
| 10 | mild | throughput | 1.40% / 1.19% | r34 | 0 | 1 | 6 | SUCCESS | 1527 | 1446 |
| 11 | mild | throughput | 1.13% / 1.08% | r56 | 175 | 1 | 11 | SUCCESS | 3167 | 2203 |
| 12 | moderate | efficiency | 2.74% / 3.58% | r23 | 0 | 1 | 33 | SUCCESS | 7007 | 6933 |
| 13 | moderate | efficiency | 3.03% / 2.93% | r23 | 0 | 1 | 9 | SUCCESS | 2181 | 2109 |
| 14 | moderate | efficiency | 3.72% / 3.91% | r23 | 0 | 3 | 49 | SUCCESS | 11359 | 10749 |
| 15 | moderate | efficiency | 2.95% / 2.28% | r23 | 0 | 1 | 6 | SUCCESS | 1592 | 1506 |
| 16 | moderate | throughput | 3.53% / 4.52% | r12 | 0 | 1 | 6 | SUCCESS | 1659 | 1578 |
| 17 | moderate | throughput | 2.84% / 2.75% | r23 | 21 | 1 | 16 | SUCCESS | 3700 | 3516 |
| 18 | strong | efficiency | 5.07% / 4.30% | r12 | 0 | 1 | 6 | SUCCESS | 1652 | 1578 |
| 19 | strong | efficiency | 4.63% / 4.99% | r12 | 0 | 1 | 7 | SUCCESS | 1881 | 1791 |
| 20 | strong | efficiency | 6.10% / 5.53% | r12 | 0 | 1 | 8 | SUCCESS | 2091 | 2004 |
| 21 | strong | efficiency | 5.13% / 5.64% | r12 | 0 | 1 | 8 | SUCCESS | 2088 | 2004 |
| 22 | strong | throughput | 5.83% / 5.57% | r12 | 19 | 1 | 8 | SUCCESS | 2178 | 2004 |
| 23 | strong | throughput | 4.59% / 5.53% | r12 | 0 | 1 | 8 | SUCCESS | 2072 | 2004 |
| 24 | severe | efficiency | 6.70% / 6.73% | r12 | 0 | 1 | 12 | SUCCESS | 2943 | 2856 |
| 25 | severe | efficiency | 6.77% / 6.69% | r12 | 0 | 1 | 16 | SUCCESS | 3791 | 3708 |
| 26 | severe | efficiency | 7.05% / 7.12% | r12 | 0 | 1 | 15 | SUCCESS | 3583 | 3495 |
| 27 | severe | efficiency | 6.92% / 7.09% | r12 | 0 | 1 | 16 | SUCCESS | 3792 | 3708 |
| 28 | severe | throughput | 6.39% / 6.80% | r12 | 100 | 1 | 9 | SUCCESS | 2805 | 2217 |
| 29 | severe | throughput | 6.84% / 7.74% | r12 | 134 | 1 | 10 | SUCCESS | 3183 | 2430 |

## Throughput measured on the RTL (100 MHz, 2765 key bits per block)

| Level | Blocks | Mean cycles / block | Decoder only | With RTT 100 us per attempt | Sifted key rate of the link |
|---|---|---|---|---|---|
| weak | 6 | 3004 | 92 Mbit/s | 18.8 Mbit/s | 31.6 kbit/s |
| mild | 6 | 3990 | 69 Mbit/s | 16.0 Mbit/s | 7.3 kbit/s |
| moderate | 6 | 4583 | 60 Mbit/s | 15.4 Mbit/s | 2.4 kbit/s |
| strong | 6 | 1994 | 139 Mbit/s | 23.1 Mbit/s | 1.3 kbit/s |
| severe | 6 | 3350 | 83 Mbit/s | 20.7 Mbit/s | 0.8 kbit/s |

RTL cycles are 2-5 % above the timing model on normal blocks; blocks with r0 pre-reveals (HOLD) take ~5-6 cycles per revealed bit more (REVEAL register writes, B_RMW), which `dyn_ir` does not model.
