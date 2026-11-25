# Mô hình toán và kế hoạch thực nghiệm ZC702

Cập nhật 02/11/2026 theo [bản duyệt](reports/zc702_math_experiment_review_20261102/REPORT.md). Bản trước được giữ trong reports/zc702_research_execution_20261102T050705Z/before/. Giữ nguyên [35 ID chuẩn](reports/zc702_work_items.csv), tên và trạng thái.

## Mục tiêu và phạm vi

Kiểm chứng ba đóng góp: che RTT bằng đa context, điều khiển EFFICIENCY/THROUGHPUT theo backlog, tích lũy verified key cho finite-key PA. Baseline PL 50 MHz, LDPC 3072, Hankel streaming giữ nguyên. Nguồn synthetic/công khai không chứng minh khóa bí mật.

Các số lịch sử ×3,48, 5,81/8,67 Mbit/s và 470 kbit thuộc bối cảnh model/RTL cũ, không là target board bắt buộc. Tái dùng bằng chứng verified; lặp fixture để đo timing không tăng cỡ mẫu FER. Chấp nhận không có crossover hoặc model không đạt tolerance.

## 1. Lập lịch — PUB01/P06/PUB05

S(K) ≈ min(K,1+RTT/Tservice) chỉ giải thích trực giác. Predictor model/zc702_resource_model.py dùng decoder chung và PS/DMA load/reveal tuần tự, có thể overlap với context khác. K không nhân tốc độ vật lý decoder.

Input: trace attempt/iteration/reveal, K, injected delay, chi phí load/control. Output: elapsed time, busy cycles, speedup so K=1 trên cùng workload. Trace-known không dự đoán FER từ QBER. Không cộng profiler parent/child hoặc span overlap.

Bằng chứng cũ: 12 calibration, 54 held-out timing, K=1/2/4, RTT 0/100/500/1000/5000/10000 µs; mean absolute relative-to-prediction error 0,293559%, max 1,116519%; phạm vi ET=PP=0, DDR IR, fixture lặp. Tolerance 10%/20% là ngưỡng kỹ thuật, không là CI.

Scheduler thử mới với một RX buffer drain wave trước load/REVEAL blocking, rồi queue các context đã chuẩn bị. Predictor cũ không tự áp dụng cho scheduler mới. Claim không tăng BRAM cần so hai build/kiến trúc K=1/K=4 thực.

## 2. Leakage và crossover — PUB02/PUB06

    leak_IR = m - D + r0 + sum(reveal_i)
    f_IR = leak_IR / (n_key * h2(QBER))
    E[A] = sum_a P(A >= a)

Ghi tag/PE/control disclosure riêng theo transcript; chốt QBER ground truth hay estimate và mẫu số/cohort. So paired common-success, đồng thời báo success/wrong/discard; không chỉ chọn success riêng từng policy.

Mô hình fluid có điều kiện: Rp(lambda)=Yp*min(lambda,mup). Yp là retained modeled output/input block dưới policy/window cố định; mup là capacity đo ở training. Nếu YE>YT>0, muT>muE và YT*muT>YE*muE thì lambda*=YE*muE/YT nằm giữa hai capacity; không thỏa thì báo không có crossover.

Yield phụ thuộc age/window/channel/arrival cần event model. Hysteresis/burst/queue hữu hạn cần đo riêng. Pilot chưa chạy tag/PE/PA chỉ dùng n_key−leak_IR làm IR proxy, không là secret-key throughput hoặc Yp toàn pipeline.

## 3. Thực nghiệm pacing

UART 115200 baud không cấp trực tiếp tải Mbit/s. DDR preload và ARM hardware timer-paced jobs; UART ngoài timed loop. Ghi scheduled/actual arrival, admission, dispatch, completion, backlog, drop, outcome, attempts/leak và timer. Tách PMU/global timer/PL cycles, virtual time và wall time.

Đo EFF/THR trên cùng Alice/Bob/PE/channel/arrival. Freeze tham số, prediction, tiêu chí và hash trước capture mới; không fit lại validation. Validation đầy đủ cần input/seed độc lập. Pilot lặp hai input chỉ kiểm tra lịch arrival mới; repeat range không là CI.

Runner board: syn/zc702/run_paced_board.py. run_paced_arrival_benchmark.py cũ là simulator. Không gán sẵn speedup/yield làm kết quả.

## 4. Finite-key — PUB03/P01/P02

Dùng pa_model.py với giả định công bố và pa_accum.py. Phân biệt candidate ell với ell_out=0 khi WAIT; EMIT làm tròn xuống bội 64. Không ép tái hiện 470 kbit.

Event ID tăng theo session: RESET/APPEND/DECIDE/EMIT/ABORT. Hai DECIDE cùng bit count vẫn là hai event. Chỉ commit emitted() sau PA_EMIT thành công, giữ split tail. Freeze source/prediction trước board capture; replay dữ liệu cũ là retrospective regression.

Ghép đúng key/counts/leak/time theo block. PE dùng test basis riêng hoặc bỏ/tính đủ bit công bố. Lập ledger IR/tag/PE/correction. Giữ công thức baseline tới khi có phân tích chứng minh thay đổi; phần tag cộng và correction bổ sung là conservative accounting cần rà soát, không âm thầm giảm leakage.

Selection/discard thích ứng, split và epsilon qua nhiều emission còn cần review. Bit-exact không là security proof. Nguồn đã generate, biết trước và virtual age chỉ chứng minh prospective functional replay; không chứng minh phân bố first-EMIT nguồn quang hay wall time.

## 5. Verification budget — PUB04/F07

Nếu mỗi verify có conditional collision bound eps_hash được chứng minh cho hash family/seed policy, union bound là min(1,N*eps_hash). Với eps_hash=2^-64, ngân sách 1e-15, cap lý thuyết 18446 lượt. Tính tag sai/hash đã thử khi DMA lỗi theo hợp đồng; reset session/buffer không hoàn budget trong boot.

Buffer 16.000.000 bit chứa 5786 block trọn ×2765 = 15.998.290 bit; block tiếp vượt buffer. Đây là input reconciled, khác output PA. Ước tính attempts từ rejection rate không bảo đảm hard cap cho mọi realization. Tách MAC/correctness/secrecy/durable accounting. Không gọi tag 64 tối ưu nếu chưa có tradeoff. CRC/RAM/file thường không là anti-rollback; reboot persistence vẫn PARTIAL.

## 6. Dependency và nghiệm thu

| Chặng | ID | Việc làm | Bằng chứng |
|---|---|---|---|
| A | PUB02/PUB03/PUB04 | Sửa split/event/budget/stale claims | Host regression, giới hạn rõ |
| B | PUB01/P06/PUB05 | Reuse K/RTT, thêm workload thiếu | Frozen prediction, raw timing |
| C | PUB02/PUB06 | Paired pacing/profile/adaptive/K | Arrival/backlog/outcome/leak, raw verifier |
| D | PUB03 | Source mới, WAIT/EMIT/split/ABORT | Hash trước capture, PA/tail khớp |
| E | P08/PUB07 | Qualification strata thiếu | Ít nhất 10000 input độc lập/stratum chọn, CI |

FER fixed n, seed disjoint, không dừng sớm theo CI đẹp. Tách discard/wrong-key/tag reject thực chạy/hardware/transport. Wilson hai phía 95% khác exact một phía 95%; CI pointwise không là CI đồng thời. Ablation decoder đã có 1000 paired input ×4 cấu hình; ưu tiên dynamic/hysteresis/K dưới cùng arrival/channel schedule.

## 7. Bằng chứng và phần mở rộng

Lưu lệnh/tool versions/seeds/config/source/ELF/raw UART/manifest và verifier độc lập. RUNNING_JOBS tách running/pending verify/verified. Kiểm tra 27 baseline hash, restore sau test ELF, đóng COM3; một board owner, không overwrite checkpoint lịch sử. Model chạy tuần tự, không thêm worker theo số CPU.

NTT/code dài/TRNG vật lý/timing 70 MHz/production trust-storage là hướng riêng, không chặn mọi gate nghiên cứu. PUB08 vẫn deferred; venue/review time chỉ tra khi chuẩn bị nộp bài.
