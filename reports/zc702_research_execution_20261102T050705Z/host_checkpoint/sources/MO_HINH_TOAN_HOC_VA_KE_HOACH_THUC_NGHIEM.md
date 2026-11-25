# M? h?nh to?n v? k? ho?ch th?c nghi?m ZC702

C?p nh?t 02/11/2026 sau [b?n duy?t](reports/zc702_math_experiment_review_20261102/REPORT.md). B?n tr??c ???c gi? trong `reports/zc702_research_execution_20261102T050705Z/before/`. ID chu?n v?n l? 35 ??u vi?c trong [CSV](reports/zc702_work_items.csv); t?i li?u n?y kh?ng ??i ID ho?c t? n?ng PASS.

M?c ti?u nghi?n c?u: h? h?u x? l? DV-QKD tr?n ZC702 chi ph? th?p, che tr? h?i???p b?ng ?a context, ?i?u khi?n EFFICIENCY/THROUGHPUT v? gom verified key cho finite-key PA. Baseline th?c thi l? PL50MHz v?i LDPC3072 v? Hankel streaming. Ngu?n Alice/decoy/seed m? ph?ng ph?i ???c ghi nh?n; output ch?c n?ng kh?ng t? th?nh kh?a b? m?t ???c ch?ng nh?n.

## 1. Ph?m vi v? nguy?n t?c

- Ba ??ng g?p c?n ki?m ch?ng: l?p l?ch ?a context, ch?nh s?ch hai profile, v? buffer finite-key WAIT/EMIT/ABORT/split.
- T?i s? d?ng s? ?o v? raw proof hi?n c?. Ch? ?o b? sung ?i?u ki?n c?n thi?u; m?t fixture l?p ?? ?o timing kh?ng t?ng c? m?u FER.
- C?c s? l?ch s? ?3,48, 5,81/8,67Mbit/s v?470kbit l? d? li?u theo b?i c?nh model/RTL c?, kh?ng ph?i target board ph?i ??t. Nh?n c? k?t qu? kh?ng c? crossover ho?c model kh?ng ??t ng??ng.
- D?ng input hash/seed ??c l?p cho training v? validation. ??ng b?ng tham s?, d? ?o?n, ti?u ch? v? hash tr??c ph?p ?o m?i; kh?ng fit l?i tr?n validation.
- T?ch ngu?n th?i gian: source optical m? ph?ng, replay virtual, wall time board. PS PMU, global timer v? counter PL c? ??n v? ri?ng.
- NTT, code d?i/rate m?i, TRNG v?t l?, timing70MHz v? production trust/storage l? h??ng ri?ng, kh?ng l? dependency c?a m?i ph?p ?o d??i ??y.

## 2. M? h?nh l?p l?ch ? PUB01/P06/PUB05

C?ng th?c S(K)?min(K,1+RTT/Tservice) ch? gi?i th?ch tr?c gi?c cho workload ??n gi?n. Predictor ch?nh d?ng m? h?nh hai t?i nguy?n `model/zc702_resource_model.py`: m?t decoder d?ng chung; PS/DMA load/reveal tu?n t?, c? th? overlap v?i decoder context kh?c. K kh?ng nh?n t?c ?? v?t l? c?a decoder.

Input: trace attempt/iteration/reveal, K, injected reveal delay, chi ph? load/control v? reveal. Output: elapsed time, decoder busy cycles v? speedup so K1 tr?n c?ng workload. Trace-known kh?ng ph?i d? ?o?n FER t? QBER.

?? c?12 calibration v?54 held-out timing, K1/2/4 ? RTT0/100/500/1000/5000/10000us, mean absolute relative-to-prediction error0,293559%, max1,116519%; ph?m vi ET=PP=0, DDR IR, fixture l?p. Gi? frozen model c? v? b?ng ch?ng ??. Ng??ng10%/20% l? tolerance k? thu?t, kh?ng ph?i CI. Workload m?i ho?c ET/PP c?n model/validation t??ng ?ng.

Kh?ng c?ng profiler parent/child ho?c span overlap. T?ch latency UART ?i?u khi?n kh?i timed DDR loop. Mu?n claim kh?ng t?ng BRAM c?n so hai ki?n tr?c/build th?c K1/K4; thay active K tr?n c?ng bitstream kh?ng ??.

## 3. Leakage, attempts v? crossover ? PUB02/PUB06

V?i m?t block v? policy ?? ch?t:

    leak_IR = m - D + r0 + sum(reveal_i)
    f_IR = leak_IR / (n_key * h2(QBER))
    E[A] = sum_a P(A >= a)

Tag/PE/control disclosure ???c ghi ri?ng theo transcript. Ch?t QBER d?ng trong f l? ground truth hay estimate, v? m?u s? l? cohort n?o. B?o success/wrong/discard v? ?i?u ki?n c?ng so s?nh paired common-success; kh?ng ch? ch?n success c?a t?ng c?u h?nh r?i so mean f.

M? h?nh fluid c? ?i?u ki?n: Rp(lambda)=Yp*min(lambda,mup). Yp l? retained modeled output/input block d??i policy/window x?c ??nh; mup l? input capacity ?o tr?n training. N?u YE>YT>0, muT>muE v? YT*muT>YE*muE th? lambda*=YE*muE/YT n?m gi?a hai capacity. Kh?ng th?a ?i?u ki?n th? b?o kh?ng c? crossover. Ch?a ?? gi? ??nh b?o m?t th? g?i retained/model output, kh?ng g?i secret-key throughput.

Yield thay ??i theo age limit, block size, channel history ho?c arrival ph?i ???c m? h?nh h?a b?ng events, ho?c c? ??nh policy/window ?? d?ng approximation. Hysteresis/burst/queue h?u h?n c?n s? ?o ri?ng.

Transport hi?n t?i115200baud kh?ng c?p tr?c ti?p t?i1?40Mbit/s. D?ng DDR preload + ARM hardware timer-paced jobs. Ghi scheduled arrival, actual arrival/admission, dispatch, completion, backlog, drop/backpressure, outcome, leakage v? timer. UART ch? ?i?u khi?n v? xu?t log sau timed loop. G?i ??ng DDR-paced benchmark, kh?ng g?i Ethernet/optical end-to-end measurement.

?o EFF/THR tr?n c?ng Alice/Bob/PE/channel v? arrival schedule; ??ng b?ng d? ?o?n tr??c c?c ?i?m d??i/quanh/tr?n crossover. Kh?ng g?n K4=3,5 hay yield0,50/0,38 l?m k?t qu?. `run_paced_arrival_benchmark.py` c? l? simulator, kh?ng ph?i runner board.

## 4. Finite-key v? first-EMIT ? PUB03/P01/P02

D?ng c?ng th?c decoy trong `pa_model.py` d??i gi? ??nh ?? c?ng b? v? state machine `pa_accum.py`. Ph?n bi?t candidate ell v?i ell_out=0 khi WAIT; khi EMIT, firmware l?m tr?n xu?ng b?i64. Kh?ng y?u c?u t?i hi?n470kbit.

Replay b?ng event ID t?ng trong t?ng session: RESET, APPEND, DECIDE, EMIT, ABORT. Hai DECIDE c? c?ng bit count v?n l? hai events; ch? commit emitted() sau PA_EMIT th?nh c?ng, gi? tail khi split. Prediction t? source cohort m?i ph?i ???c freeze tr??c board capture. G?i replay d? li?u c? l? retrospective regression.

Ph?i gh?p ??ng key/counts/leak/time theo block. PE d?ng test basis t?ch bi?t, ho?c b?/t?nh ?? c?c bit PE b? c?ng b?. L?p ledger leak_IR, tag transcript, PE v? c?c correction term. Gi? c?ng th?c baseline cho t?i khi c? ph?n t?ch ch?ng minh thay ??i; ph?n tag ?? c?ng v? correction term b? sung hi?n ???c ghi l? conservative accounting c?n r? so?t, kh?ng ?m th?m gi?m leakage.

IR discard th?ch ?ng/split v? epsilon cho nhi?u PA emission c?n c?n review gi? ??nh; bit-exact kh?ng l? security proof. Th? nghi?m ngu?n synthetic ch? nghi?m thu model v? tri?n khai. First-EMIT ph?i n?u ?? l? th?i gian ngu?n m? ph?ng hay wall time x? l?.

## 5. Verification budget ? PUB04/F07

D??i gi? ??nh m?i ph?p verify c? conditional collision bound eps_hash (???c ch?ng minh cho hash family v? seed policy), union bound cho N l?n l? min(1,N*eps_hash). V?i eps_hash=2^-64 v? ng?n s?ch1e-15, cap l? thuy?t l?18446 l??t. T?nh c? l?n tag sai v? hash ?? th? khi DMA l?i theo h?p ??ng firmware; reset buffer/session kh?ng ho?n budget trong boot.

Buffer16.000.000bit ch?a5786 block tr?n ?2765=15.998.290bit; block ti?p theo v??t buffer. ??y l? input ?? reconciliation, kh?ng ph?i output secret bits. ??c t?nh l??t th? t? rejection rate kh?ng l? b?o ??m hard cap cho m?i realization. MAC authentication, correctness, secrecy v? durable accounting l? c?c kh?i ni?m ri?ng.

Kh?ng g?i tag64 t?i ?u n?u ch?a c? b?i to?n tradeoff v? gi? ??nh ??y ??. Kh?ng g?i CRC/RAM/file th??ng l? ch?ng rollback. Storage qua reboot gi? PARTIAL v? n?m ngo?i gate nghi?n c?u hi?n t?i.

## 6. Th?c nghi?m t?i thi?u theo dependency

| Th? t? | ID chu?n | Vi?c th?c hi?n | Nghi?m thu |
|---|---|---|---|
| A | PUB03/PUB04/PUB02 | S?a split/event/budget v? stale claims | Host regressions, report c? scope, kh?ng auto-PASS |
| B | PUB01/P06/PUB05 | T?i d?ng K/RTT proof; th?m workload m?i n?u predictor ch?a bao ph? | Predictions hash tr??c capture; raw timer/cycles ??i chi?u |
| C | PUB02/PUB06 | Pilot DDR-paced paired EFF/THR, r?i frozen validation v? adaptive/K | Scheduled/actual timestamps, backlog/outcome/leak, capacity/yield ?o th?t |
| D | PUB03 | Cohort source m?i cho WAIT/EMIT/split/ABORT v? first-EMIT | Source/fixture/prediction hash tr??c board; PA/tail kh?p raw verifier |
| E | P08/PUB07 | Qualification c?c strata c?n thi?u trong FER catalog | >=10000 block ??c l?p/stratum ?? ch?n, CI v? failure accounting |

Pilot ch?n runtime/variance tr??c qualification. FER b?o discard, wrong-key theo ground truth, tag reject n?u th?t s? ch?y, l?i hardware/transport. Wilson hai ph?a95 kh?c exact m?t ph?a95; CI pointwise kh?ng t? l? CI ??ng th?i. Kh?ng d?ng s?m v? k?t qu? ??p khi ch?a c? k? ho?ch sequential.

Ablation decoder ?? c?1000 input paired ?4 c?u h?nh. Kh?ng ch?y l?i nh? th? ch?a c?; c?n dynamic/hysteresis/K d??i c?ng arrival/channel schedule. T?ch ET v? PP ch? khi mu?n claim l?i ?ch t?ng th?nh ph?n.

## 7. B?o c?o v? ph?m vi c?n l?i

M?i ch?ng l?u l?nh/tool versions/config/seeds/source/ELF/raw UART/hash manifest v? verifier receipt. RUNNING_JOBS ph?n bi?t running/pending verify/verified; runner PASS kh?ng ??. Baseline50MHz ph?i kh?p27hash v? ???c kh?i ph?c sau test ELF; COM3 ??ng sau run. M?t board job m?i l?n, model tu?n t?, kh?ng th?m worker m?c ??nh theo s? CPU.

B?n th?o PUB08 v?n deferred theo ch? ??o hi?n c?. Danh m?c venue, impact factor v? th?i gian review kh?ng l? ti?u ch? nghi?m thu k? thu?t; ch? tra l?i khi b?t ??u chu?n b? n?p b?i.
