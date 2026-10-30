# Post-processing on simulated decoy-BB84 sessions (finite key)

Sessions: `model/gen_qkd_session.py` (decoy BB84 0.6/0.2/0, 6:1:1, 100 MHz, detector 10 %, Y0 2e-6, dead time 2 us, afterpulse 0.5 %, Gamma-Gamma turbulence with 5 ms coherence time, link loss per level). Finite key: Lim et al. 2014, eps_sec 1e-9, eps_cor 1e-15, one PA block per session, leak_EC includes a 64-bit verification tag per block. IR time at 100 MHz + RTT 100 us per attempt.

## 1. Session statistics (validation)

| Session | Loss | Link time | Gain signal / decoy / vacuum (sim) | Gain (analytic, no dead time) | QBER Z / X | Block QBER min..max (std) |
|---|---|---|---|---|---|---|
| WEAK | 15 dB | 38 s | 1.62e-03 / 5.47e-04 / 9.67e-06 | 1.90e-03 / 6.35e-04 / 4.00e-06 | 1.58% / 1.60% | 0.7..2.7% (0.33) |
| MILD | 22 dB | 165 s | 3.68e-04 / 1.26e-04 / 5.29e-06 | 3.82e-04 / 1.30e-04 / 4.00e-06 | 1.72% / 1.71% | 0.5..3.2% (0.52) |
| MODERATE | 27 dB | 492 s | 1.22e-04 / 4.39e-05 / 4.45e-06 | 1.24e-04 / 4.40e-05 / 4.00e-06 | 3.19% / 3.17% | 1.8..4.8% (0.54) |
| STRONG | 30 dB | 939 s | 6.36e-05 / 2.40e-05 / 4.25e-06 | 6.39e-05 / 2.40e-05 / 4.00e-06 | 5.15% / 5.16% | 3.9..6.6% (0.48) |
| SEVERE | 32 dB | 1416 s | 4.18e-05 / 1.67e-05 / 4.14e-06 | 4.19e-05 / 1.66e-05 / 4.00e-06 | 6.87% / 6.88% | 5.1..8.7% (0.58) |

## 2. Finite-key result per controller configuration

| Session | Config | Blocks ok | f | Kept key bits | leak_EC | s1 | phase err. | Secret bits ell | ell / kept | IR time / link time | Secret bit/s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| weak | basic_old | 441/441 | 1.71 | 1219365 | 269039 | 491893 | 5.1% | 79792 | 0.065 | 0.004 | 2100 |
| weak | dyn_old | 432/441 | 2.03 | 1194480 | 303162 | 480250 | 5.1% | 37358 | 0.031 | 0.002 | 983 |
| weak | efficiency | 440/441 | 1.53 | 1216600 | 242488 | 490673 | 5.1% | 105472 | 0.087 | 0.002 | 2776 |
| weak | throughput | 438/441 | 1.60 | 1211070 | 251428 | 488096 | 5.1% | 94693 | 0.078 | 0.002 | 2492 |
| mild | basic_old | 435/436 | 1.73 | 1202775 | 279834 | 471567 | 5.0% | 56860 | 0.047 | 0.001 | 345 |
| mild | dyn_old | 429/436 | 2.12 | 1186185 | 325787 | 464058 | 5.0% | 5510 | 0.005 | 0.001 | 33 |
| mild | efficiency | 436/436 | 1.60 | 1205540 | 261009 | 472824 | 5.0% | 76588 | 0.064 | 0.000 | 464 |
| mild | throughput | 436/436 | 1.64 | 1205540 | 270717 | 472824 | 5.0% | 66880 | 0.055 | 0.000 | 405 |
| moderate | basic_old | 432/434 | 1.45 | 1194480 | 377356 | 462824 | 7.1% | 0 | 0.000 | 0.000 | 0 |
| moderate | dyn_old | 428/434 | 1.60 | 1183420 | 408431 | 457994 | 7.1% | 0 | 0.000 | 0.000 | 0 |
| moderate | efficiency | 432/434 | 1.36 | 1194480 | 352825 | 463504 | 7.1% | 0 | 0.000 | 0.000 | 0 |
| moderate | throughput | 434/434 | 1.85 | 1200010 | 479151 | 465633 | 7.1% | 0 | 0.000 | 0.000 | 0 |
| strong | basic_old | 422/434 | 1.50 | 1166830 | 537361 | 431959 | 10.4% | 0 | 0.000 | 0.000 | 0 |
| strong | dyn_old | 390/434 | 1.49 | 1078350 | 492292 | 394737 | 10.4% | 0 | 0.000 | 0.000 | 0 |
| strong | efficiency | 423/434 | 1.49 | 1169595 | 535968 | 434113 | 10.4% | 0 | 0.000 | 0.000 | 0 |
| strong | throughput | 434/434 | 1.53 | 1200010 | 561162 | 447567 | 10.4% | 0 | 0.000 | 0.000 | 0 |
| severe | basic_old | 426/434 | 1.29 | 1177890 | 575760 | 438444 | 13.2% | 0 | 0.000 | 0.000 | 0 |
| severe | dyn_old | 416/434 | 1.36 | 1150240 | 589158 | 426601 | 13.2% | 0 | 0.000 | 0.000 | 0 |
| severe | efficiency | 433/434 | 1.25 | 1197245 | 566568 | 447277 | 13.2% | 0 | 0.000 | 0.000 | 0 |
| severe | throughput | 432/434 | 1.29 | 1194480 | 582485 | 446189 | 13.2% | 0 | 0.000 | 0.000 | 0 |
