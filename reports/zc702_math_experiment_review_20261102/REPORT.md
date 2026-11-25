# Duyệt mô hình toán học và kế hoạch thực nghiệm

Ngày 02/11/2026. Kết luận: **khả thi để triển khai nghiên cứu trên baseline ZC702 50 MHz, nhưng chưa duyệt chạy nguyên trạng tài liệu tổng quan và các generator**. Có thể giữ bốn mô hình và ba đóng góp, thu gọn phép thử theo dependency; cần sửa các điểm dưới trước khi lấy số làm kết luận.

Lượt này chỉ review và chạy probe Python host. Không sửa mô hình, tài liệu gốc, work items, con trỏ hoặc checkpoint lịch sử. Không mở COM3/JTAG. [Receipt tái hiện](REVIEW_RECEIPT.json), [script](run_review_probes.py), [fixture split](split_probe_records.json).

## Đánh giá từng mô hình

| Mục | Đánh giá | Điều kiện triển khai |
|---|---|---|
| PUB01: lập lịch K/RTT | Khả thi nhất; đã có mô hình hai tài nguyên và bằng chứng timing giới hạn | Dùng `zc702_resource_model.py`, không dùng riêng công thức min(K,1+RTT/Tdec) để dự đoán pipeline đầy đủ |
| PUB02: f/attempts/crossover | Công thức leakage và crossover có điều kiện dùng được; phần dự đoán outcome và đo arrival chưa đầy đủ | Training cùng input cho EFF/THR; không gán gain K4/yield cố định; viết runner pacing thực trên ARM |
| PUB03: finite-key/first-EMIT | Khả thi dưới dạng mô phỏng nguồn + functional board; còn lỗi model split và thiết kế validation | Sửa giữ tail, replay theo event, freeze trước cohort mới; giới hạn phát biểu về bảo mật và thời gian |
| PUB04: verification budget | Phép tính union bound có điều kiện đơn giản, khả thi | Định nghĩa hash family/seed/transcript và epsilon; phân biệt số lần verify, input buffer và output PA; bỏ PASS persistence tự sinh |

Code self-check của resource model và crossover đều PASS trong lượt review. Chúng là self-check toán/mô phỏng, không bổ sung phép đo board. Hash raw-result của ba proof scheduling/ablation/secure-accumulator đã được đối chiếu lại; không chạy lại raw UART verifier trong lượt này.

## Phát hiện cần xử lý

### M01 — High: tài liệu tổng quan và CSV còn diễn đạt kết quả vượt bằng chứng

`MO_HINH_TOAN_HOC_VA_KE_HOACH_THUC_NGHIEM.md`, mục 2–3, viết x3,48/không thêm BRAM/8,67 Mbit/s/470 kbit khóa an toàn như kết quả đóng góp thực nghiệm chung. Những con số lịch sử phải có nhãn nền tảng, model/RTL/board và workload; không dùng làm target buộc ZC702 tái hiện.

`reports/zc702_work_items.csv`, PUB02, vẫn viết crossover đã được empirically verified và có thể chuyển sang manuscript, trong khi `run_paced_arrival_benchmark.py` là host simulator có hệ số K4=3,5 và yield gán trước. Giữ PUB02 PARTIAL; chưa nghiệm thu crossover board. Ngược lại, `publication_plan_20261026/EXPERIMENT_PLAN.md` còn ghi chưa có board ablation ba chiều, dù proof bốn cấu hình đã có. Cần đồng bộ tài liệu trước khi lập ma trận còn thiếu để tránh chạy lặp.

### M02 — High: kế hoạch tải 1–40 Mbit/s không thể cấp trực tiếp qua UART hiện có

Runner dùng 115200 baud. Với 8N1, trần lý tưởng binary chỉ 92.160 payload bit/s; đường hex QAS2 chỉ tương đương tối đa 46.080 bit dữ liệu binary/s, chưa trừ header, MAC, phản hồi và debug. Đây là suy ra từ framing, không phải throughput đo trên board.

Phương án khả thi ngay: nạp pool input vào DDR trước, ARM phát job theo hardware timer ở tốc độ đã chốt, đo lịch phát **thực tế**, backlog, drop/backpressure, số output và wall time. Gọi đúng là DDR-paced system/component benchmark. UART làm điều khiển và xuất log sau đo. Không preload sẵn lịch hoàn thành; job vẫn phải chạy IR/verify/PA thật trong cửa sổ đo. Nếu cần kết luận end-to-end của đường truyền Alice–Bob thực thì phải tích hợp transport đủ nhanh và đo riêng; không bắt buộc làm việc đó cho gate DDR nghiên cứu đầu tiên.

### M03 — High: mô hình finite-key làm mất tail sau split

Trong `model/finite_key_accumulation_model.py:54`, `simulate_accumulation_trajectory` gọi `acc.reset()` sau mọi EMIT. Với split phải dùng `acc.emitted()` để giữ tail và metadata. Probe dùng 90 block tốt + hai block metadata xấu: split ở index90; khi xử lý block tiếp, model hiện chỉ có **2.765 bit**, reference giữ tail có **5.530 bit**. Đây là lỗi Python model, không phải kết luận lỗi buffer board.

Ngoài ra, `validate_against_board_run` ánh xạ quyết định bằng tổng bit (`board_decisions_by_bits`) có thể gộp mất các quyết định cùng bit count ở những thời điểm khác nhau; không xử lý đầy đủ trạng thái sau EMIT/split/ABORT. Cần event ID/session ID, phân biệt APPEND/DECIDE/EMIT/ABORT và đối chiếu tail. Lấy counters đã đo rồi gọi lại cùng `PAAccumulator` chỉ là retrospective consistency; chưa dự đoán thời gian thu thập hoặc first-EMIT của nguồn chưa biết.

### M04 — High: generator budget tự công bố persistence PASS và nhầm loại dung lượng

`model/verification_budget_model.py:91` gán `overall='PASS'`; dòng103 và report template khẳng định chống rollback/OCM warm-reset, không có phép thử tương ứng trong module. Không chạy `main()` này để xuất báo cáo nghiệm thu hiện hành. Hàm `analyze_accumulation_session` gọi tham số `target_secret_bits` nhưng thực tế chia cho 2765 bit input đã reconciliation; đó không phải output PA secret length.

Buffer 16.000.000 bit chứa tối đa **5.786 block trọn = 15.998.290 bit**; block thứ5.787 làm tổng thành **16.001.055 bit**, vượt buffer. `ceil(target/2765)` phù hợp câu hỏi “cần bao nhiêu block để vượt ngưỡng input”, không phù hợp “bao nhiêu block trọn vừa buffer”. Công thức `ceil(naccepted/(1-preject))` chỉ là ước tính theo tỷ lệ, không bảo đảm số lượt đủ trong một hard cap cho mọi realization ngẫu nhiên.

Union bound cần giả định collision bound của hash family và cách cấp seed; không tự suy từ nhãn 64bit. Cận correctness khác MAC authentication và secrecy. Theo [nghiên cứu blind IR + verification](https://arxiv.org/abs/1705.06664), verification dựa trên epsilon-universal hashing; module/file tồn tại không chứng minh các giả định đó. Không kết luận tag64 “tối ưu” chỉ từ một giá trị ngân sách.

### M05 — Medium: mô hình crossover hiện là mô hình có điều kiện, chưa là predictor f(QBER) hoàn chỉnh

Giữ công thức leakage IR `m-D+r0+sum(reveal)` và identity `E[A]=sum P(A>=a)`. Các xác suất attempt/correct/wrong/discard vẫn phải ước lượng trên training; chúng chưa tự suy từ code/QBER. Mean f cần nêu mẫu số và cohort retained correct, đồng thời báo unconditional success/wrong/discard và paired common-success để tránh selection bias.

Với yield cố định Yp trên mỗi input và capacity mup, mô hình fluid `Rp(lambda)=Yp*min(lambda,mup)` cho crossover có điều kiện. Nếu YT*muT không vượt YE*muE thì phải chấp nhận không có crossover. PA accumulation/age limit có thể làm Y phụ thuộc lambda, block size và channel history; khi đó phải cố định policy/window để dùng approximation này, hoặc dùng mô hình event đầy đủ. Multi-context che thời gian chờ; không làm decoder dùng chung nhanh lên 3,5 lần ở mọi RTT.

### M06 — Medium: finite-key formula cần hợp đồng leakage/selection rõ ràng

`pa_model.secure_length_decoy` ghi `leak_ec` bao gồm tag; stream cộng64bit/tag rồi công thức còn trừ `log2(2/eps_cor)`. [Lim et al., Eq.1 và supplementary Eq.11](https://arxiv.org/pdf/1311.7129) tách leakage error-correction với leakage error-verification. Cần giải thích phần trừ thêm đang là conservative accounting hay trùng khoản, nhất là khi có nhiều IR tag trên một PA block. Chưa có cơ sở tự xóa64bit hoặc thay công thức baseline trong lượt review này.

Quan trọng hơn, IR discard thích ứng và split chọn thời điểm theo thống kê cần kiểm tra giả định selection, bound và phân bổ epsilon nhiều lần phát. Bit-exact của Python/C/PA chỉ nghiệm thu thực thi mô hình; không chứng minh protocol secrecy. Báo ba trục thời gian riêng: nguồn quang mô phỏng, replay virtual và wall time board. Giữ kết quả nguồn synthetic ở đúng phạm vi.

### M07 — Medium: thiết kế FER/ablation cần chốt đại lượng và workload trước

10.000 mẫu không bảo đảm FER<=10^-3. Với0/10.000, Wilson hai phía95 có upper **0,0003840**, còn exact một phía95 upper **0,0002995**; hai con số có định nghĩa khác nhau. [NIST trình bày Wilson](https://itl.nist.gov/div898/handbook/prc/section2/prc241.htm). Báo các CI pointwise; không gọi chúng là coverage đồng thời toàn sweep.

Chọn strata QBER/code/profile trước; giữ số mẫu cố định hoặc dùng phương pháp sequential được xác định trước. Thêm lỗi transport/hardware vào accounting, không âm thầm bỏ trial. Nêu riêng decoder FER, wrong convergence theo ground truth và verification reject nếu thực sự chạy tag. Mỗi FER sample phải là block độc lập; bản phát lại cùng fixture đo timing không tăng mẫu FER.

Ablation GS/NMS/ET-PP và ablation dynamic/hysteresis/K dùng hai thiết kế phù hợp: fixed input paired cho decoder; cùng arrival schedule/channel/PE cho policy và K. Không ép hysteresis phát huy tác dụng trên nguồn không có biến thiên tải. Nếu muốn tách lợi ích ET với PP phải có cặp cấu hình riêng; bằng chứng bật cả hai chỉ hỗ trợ hiệu ứng chung.

## Kế hoạch thực thi gọn, theo thứ tự

| Chặng | Đầu việc chuẩn | Thực hiện | Gate nghiệm thu |
|---|---|---|---|
| 0. Sửa đặc tả/model host | PUB02/PUB03/PUB04 | Sửa split/event replay; bỏ auto-PASS persistence; thống nhất input/output bits và epsilon; sửa claim stale | Probe split giữ đúng tail, duplicate bit-count decisions không mất; report phân loại đúng nguồn bằng chứng |
| 1. Timing và lập lịch | P06/PUB05/PUB01 | Tái dùng profiler/counter và cohort K/RTT đã xác minh; chỉ thêm workload còn thiếu sau freeze | File dự đoán được hash trước chạy; timer/unit/overlap đúng; so prediction với số đo và chấp nhận kết quả âm |
| 2. Profile/crossover/ablation | PUB02/PUB06 | Training paired EFF/THR cùng nguồn; freeze yield/capacity và khoảng crossover; DDR timer-paced dưới/quanh/trên vùng dự đoán | Raw schedule thực, queue/outcome/leak/output/time; so EFF/THR/adaptive; không giả định gain K4 hay crossover phải tồn tại |
| 3. Finite-key và FER bổ sung | PUB03/P08/PUB07 | Một source cohort mới đã freeze, có WAIT/EMIT/split/ABORT; mở các FER strata còn thiếu theo catalog | Finite-key functional output/tail khớp; first-EMIT nêu đúng thời gian; FER độc lập + CI và đầy đủ failure accounting |

Đây là các chặng thí nghiệm, không tạo ID mục tiêu mới. Không cần NTT mới, rebuild70MHz, LDPC dài hoặc storage chống rollback để bắt đầu. Production/security hardening giữ backlog riêng; không nâng trạng thái của chúng từ phép đo nghiên cứu.

Không cần quét mọi tổ hợp ngay. Tái sử dụng bằng chứng K=1/2/4 ×6 RTT ×3 repeat và bốn cấu hình ablation đã có, trong phạm vi workload của chúng. Pilot mới xác định variance và runtime rồi chốt cỡ mẫu/repeat trước qualification. Không ấn định một mức throughput hoặc số bit bí mật phải xuất hiện.

Nguồn phối hợp cần có cho chặng2/3: định nghĩa input/PE/channel và seed độc lập; lựa chọn fixed-window/age/epsilon; danh sách strata còn thiếu; log raw counter và fixture hash. Nếu chưa có nguồn quang thật, dùng generator synthetic đã pin và ghi đúng nhãn. Không yêu cầu mua phần cứng/trust anchor để duyệt gate nghiên cứu này.

## Quyết định duyệt

**Duyệt khung nghiên cứu có điều kiện**, ưu tiên sửa model/đặc tả và bổ sung phép đo trên baseline. **Chưa duyệt các claim định lượng hoặc bảo mật trong tài liệu tổng quan như kết quả đã đạt.** Không chạy các generator cũ để tự cập nhật PASS. Review không đổi35ID, REV, work items hay RECONCILIATION_CURRENT; baseline và trạng thái COM3 giữ nguyên.
