# Đánh giá sửa lỗi trên `bb84_key_test_Sim_20260618_002028.csv`

n = 3072, d = 307, 2765 bit key / khối, bước công bố 77 bit, iter_max 50, PP (rounds, min_usc, max_usc) = (1, 2, 16).

| Mức | QBER mức | Khối | Code | Thành công | Lần thử TB | f TB | Lỗi còn lại |
|---|---|---|---|---|---|---|---|
| 1 WEAK | 0.31% | 3 | r56 | 3/3 | 1.67 | 2.94 | 0 |
| 2 MILD | 3.65% | 4 | r23 | 4/4 | 3.00 | 1.40 | 0 |
| 3 MODERATE | 8.37% | 3 | r12 | 3/3 | 2.67 | 1.19 | 0 |
| 4 STRONG | 11.64% | 3 | r12 | 0/3 | nan | nan | 0 |
| 5 SEVERE | 13.43% | 3 | r12 | 0/3 | nan | nan | 0 |

## Từng khối

| Khối | Mức | QBER khối | Code | Kết quả | Lần thử | Bit công bố | f | Vết |
|---|---|---|---|---|---|---|---|---|
| 0 | WEAK | 0.33% | r56 | SUCCESS | 2 | 77 | 3.23 | [fail it=50 usc=25 pp=0] [ok it=19 usc=0 pp=0] |
| 1 | WEAK | 0.33% | r56 | SUCCESS | 1 | 0 | 2.35 | [ok it=48 usc=0 pp=0] |
| 2 | WEAK | 0.33% | r56 | SUCCESS | 2 | 77 | 3.23 | [fail it=50 usc=44 pp=0] [ok it=20 usc=0 pp=0] |
| 3 | MILD | 3.94% | r23 | SUCCESS | 4 | 231 | 1.43 | [fail it=50 usc=165 pp=0] [fail it=50 usc=121 pp=0] [fail it=50 usc=106 pp=0] [ok it=14 usc=0 pp=0] |
| 4 | MILD | 3.36% | r23 | SUCCESS | 2 | 77 | 1.35 | [fail it=50 usc=171 pp=0] [ok it=50 usc=0 pp=0] |
| 5 | MILD | 3.33% | r23 | SUCCESS | 3 | 154 | 1.5 | [fail it=50 usc=103 pp=0] [fail it=50 usc=38 pp=0] [ok it=17 usc=0 pp=0] |
| 6 | MILD | 3.91% | r23 | SUCCESS | 3 | 154 | 1.32 | [fail it=50 usc=180 pp=0] [fail it=50 usc=180 pp=0] [ok it=35 usc=0 pp=0] |
| 7 | MODERATE | 8.93% | r12 | SUCCESS | 3 | 154 | 1.15 | [fail it=50 usc=318 pp=0] [fail it=50 usc=248 pp=0] [ok it=34 usc=0 pp=0] |
| 8 | MODERATE | 7.59% | r12 | SUCCESS | 2 | 77 | 1.22 | [fail it=50 usc=193 pp=0] [ok it=48 usc=0 pp=0] |
| 9 | MODERATE | 8.35% | r12 | SUCCESS | 3 | 154 | 1.21 | [fail it=50 usc=243 pp=0] [fail it=50 usc=240 pp=0] [ok it=25 usc=0 pp=0] |
| 10 | STRONG | 12.33% | r12 | DISCARD | 5 | 307 |  | [fail it=50 usc=348 pp=0] [fail it=50 usc=304 pp=0] [fail it=50 usc=307 pp=0] [fail it=50 usc=308 pp=0] [fail it=50 usc=334 pp=0] |
| 11 | STRONG | 11.75% | r12 | DISCARD | 5 | 307 |  | [fail it=50 usc=338 pp=0] [fail it=50 usc=350 pp=0] [fail it=50 usc=324 pp=0] [fail it=50 usc=286 pp=0] [fail it=50 usc=223 pp=0] |
| 12 | STRONG | 11.07% | r12 | DISCARD | 5 | 307 |  | [fail it=50 usc=307 pp=0] [fail it=50 usc=348 pp=0] [fail it=50 usc=326 pp=0] [fail it=50 usc=297 pp=0] [fail it=50 usc=195 pp=0] |
| 13 | SEVERE | 12.59% | r12 | DISCARD | 5 | 307 |  | [fail it=50 usc=326 pp=0] [fail it=50 usc=329 pp=0] [fail it=50 usc=345 pp=0] [fail it=50 usc=281 pp=0] [fail it=50 usc=293 pp=0] |
| 14 | SEVERE | 14.29% | r12 | DISCARD | 5 | 307 |  | [fail it=50 usc=382 pp=0] [fail it=50 usc=342 pp=0] [fail it=50 usc=364 pp=0] [fail it=50 usc=353 pp=0] [fail it=50 usc=354 pp=0] |
| 15 | SEVERE | 13.16% | r12 | DISCARD | 5 | 307 |  | [fail it=50 usc=389 pp=0] [fail it=50 usc=327 pp=0] [fail it=50 usc=324 pp=0] [fail it=50 usc=300 pp=0] [fail it=50 usc=304 pp=0] |

## Oracle: mọi mother code trên cùng khối

| Khối | Mức | QBER | r12 | r23 | r34 | r56 |
|---|---|---|---|---|---|---|
| 0 | WEAK | 0.33% | 1 lần, f=14.07 | 1 lần, f=8.21 | 1 lần, f=5.28 | 2 lần, f=3.23 |
| 1 | WEAK | 0.33% | 1 lần, f=14.07 | 1 lần, f=8.21 | 1 lần, f=5.28 | 1 lần, f=2.35 |
| 2 | WEAK | 0.33% | 1 lần, f=14.07 | 1 lần, f=8.21 | 1 lần, f=5.28 | 2 lần, f=3.23 |
| 3 | MILD | 3.94% | 1 lần, f=1.85 | 4 lần, f=1.43 | hỏng | hỏng |
| 4 | MILD | 3.36% | 1 lần, f=2.09 | 2 lần, f=1.35 | hỏng | hỏng |
| 5 | MILD | 3.33% | 1 lần, f=2.11 | 3 lần, f=1.50 | 5 lần, f=1.32 | hỏng |
| 6 | MILD | 3.91% | 1 lần, f=1.87 | 3 lần, f=1.32 | hỏng | hỏng |
| 7 | MODERATE | 8.93% | 3 lần, f=1.15 | hỏng | hỏng | hỏng |
| 8 | MODERATE | 7.59% | 2 lần, f=1.22 | hỏng | hỏng | hỏng |
| 9 | MODERATE | 8.35% | 3 lần, f=1.21 | hỏng | hỏng | hỏng |
| 10 | STRONG | 12.33% | hỏng | hỏng | hỏng | hỏng |
| 11 | STRONG | 11.75% | hỏng | hỏng | hỏng | hỏng |
| 12 | STRONG | 11.07% | hỏng | hỏng | hỏng | hỏng |
| 13 | SEVERE | 12.59% | hỏng | hỏng | hỏng | hỏng |
| 14 | SEVERE | 14.29% | hỏng | hỏng | hỏng | hỏng |
| 15 | SEVERE | 13.16% | hỏng | hỏng | hỏng | hỏng |
