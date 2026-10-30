# Abort rule and PA accumulation (simulated link, IR surrogate from results/exp_compare.txt)

old: PA block = 1.2 Mbit of reconciled key, discarded when its finite-key length <= 0. new: pa_accum.PAAccumulator (emit when doubling the block would gain < 10 %, near the asymptotic fraction, at 16 Mbit, after 1 h, or at its best point when the channel degrades; abort only when the asymptotic fraction <= 0). Lim 2014 finite key, eps_sec 1e-9.

| Scenario | Rule | Secret bits | Secret bit/s | PA blocks | Avg block (Mbit) | Discarded key bits | Pending at end (its ell) | First key after |
|---|---|---|---|---|---|---|---|---|
| STRONG 3 h | old | 0 | 0.0 | 0 | 0.0 | 13030963 | 743100 (0) | never |
| STRONG 3 h | new | 0 | 0.0 | 0 | 0.0 | 13666662 | 107401 (0) | never |
| STRONG 3 h | new, no age limit | 0 | 0.0 | 0 | 0.0 | 13666662 | 107401 (0) | never |
| SEVERE 3 h | old | 0 | 0.0 | 0 | 0.0 | 9021263 | 94277 (0) | never |
| SEVERE 3 h | new | 0 | 0.0 | 0 | 0.0 | 9033744 | 81796 (0) | never |
| SEVERE 3 h | new, no age limit | 0 | 0.0 | 0 | 0.0 | 9033744 | 81796 (0) | never |
| MODERATE 1 h | old | 0 | 0.0 | 0 | 0.0 | 7698798 | 1055537 (0) | never |
| MODERATE 1 h | new | 0 | 0.0 | 0 | 0.0 | 494254 | 8260081 (469920) | never |
| MODERATE 1 h | new, no age limit | 0 | 0.0 | 0 | 0.0 | 494254 | 8260081 (469920) | never |
| MIXED 2 h 20 | old | 1483028 | 176.6 | 12 | 1.2 | 10972070 | 1143137 (20535) | 1 min |
| MIXED 2 h 20 | new | 1940404 | 231.0 | 3 | 5.2 | 5468773 | 5433364 (791605) | 3 min |
| MIXED 2 h 20 | new, no age limit | 1939991 | 231.0 | 2 | 4.7 | 5468773 | 11805000 (1074433) | 3 min |
