# Tiến độ toàn bộ dự án ZC702

Cập nhật: 2026-10-27T17:36:34+07:00.

Danh sách hiện có **35 mục được định danh**, không có mục thứ 36. Không tự tạo thêm mục để khớp một tổng số đã nêu trong trao đổi.

Đạt tiêu chí chức năng hiện có: **13/35 (37.1% theo số đầu mục)**. Không dùng tỷ lệ này làm tỷ lệ công sức, mức an toàn hay mức sẵn sàng sản phẩm.

| Nhóm | Tổng | Đạt trong phạm vi thử | Một phần/đang làm | Chưa làm |
|---|---:|---:|---:|---:|
| Chức năng trên board | 12 | 12 | 0 | 0 |
| Hoàn thiện hệ thống | 8 | 1 | 7 | 0 |
| Mô hình, thí nghiệm, bài báo | 8 | 0 | 7 | 1 |
| Hướng phát triển | 7 | 0 | 6 | 1 |

Alice, thống kê decoy và dữ liệu BSC là mô phỏng. PL hiện chạy 50 MHz; PASS chức năng không đồng nghĩa chứng nhận bảo mật QKD.

## Kết quả mới có bằng chứng

- [Ablation board bốn cấu hình](zc702_board_ablation_20261027T024201Z/REPORT.md): 1.000 cặp đầu vào ×4; không chạy tag/PA trong phép đo. Có một đầu vào hội tụ sai 11 bit ở ba cấu hình GS; kết quả kiểm thử tag riêng phải được đọc độc lập, không đổi nhãn tag của cohort ablation.
- [Kiểm thử tag Alice trên wrong codeword tự nhiên](zc702_wrong_codeword_20261027T044256Z/REPORT.md): đã có raw proof; đọc giới hạn và kết luận riêng trong báo cáo.
- [Đối chiếu mô hình lập lịch trên timing held-out](zc702_schedule_validation_20261027T044317Z/REPORT.md): đã có raw proof; đọc giới hạn và kết luận riêng trong báo cáo.
- [FER catalog](FER_CATALOG.md): 8 cohort hoàn tất có proof; 2 cohort đủ cỡ mẫu ≥10.000. Không gộp các QBER/code/seed khác nhau.
- [Đo pha PS/PL/UART và PA lớn](zc702_profiling_20261027/REPORT.md): 36 ca per-block và một phiên PA 103 pass; chưa phải thông lượng khóa bí mật của sản phẩm.

## Trạng thái job lúc tạo báo cáo

- `RUNNING_JOBS.json`: `VERIFIED_COMPLETE`. Đây là snapshot; đọc file live trước khi dùng COM3.
- `FOLLOWUP_JOBS.json`: `VERIFIED_COMPLETE`. Đây là snapshot; đọc file live trước khi dùng COM3.

## Phần còn lại theo từng mục

| ID | Trạng thái | Công việc cần tiếp tục |
|---|---|---|
| P02 | PARTIAL | Integrate PE accounting into actual PA path; execute C and board negative cases |
| P03 | PARTIAL | Physical source integration, raw board capture and entropy assessment |
| P04 | PARTIAL | Specify production trust/storage, remove plaintext provisioning/debug KEY, authenticate control/errors and extend gate to accumulator EMIT/split; retain lab fixture scope until fault/reset regression |
| P05 | PARTIAL | Inspect actual reset-to-APP critical paths in the original DCP; retain 50MHz baseline and isolate any new PnR experiment |
| P06 | PARTIAL | Use measured phases to refine scheduling; measure controlled arrival/backlog crossover and multi-context end-to-end phases |
| P07 | PARTIAL | Queue-hole regression fixed in C; test concurrency, GIC/DMA/WFI and hardware timeout behavior before integration |
| P08 | PARTIAL | Complete staged qualification cohorts, then expand remaining QBER/code strata and tag/PA end-to-end fault statistics |
| R01 | PARTIAL | Implement real APP/CN/VN/syndrome/output and RTL golden tests |
| R02 | PARTIAL | Validate both graphs/rank/FER, then implement the rate ABI and ROM on an isolated build |
| R03 | TODO_RESEARCH | Skip Andes AE350; maintain 100% focus on Xilinx Zynq-7000 |
| R04 | PARTIAL | Implement real NTT/burst engine with valid transform lengths |
| R05 | PARTIAL | Use deployed codes.json matrix, correct pipeline and RTL testbench |
| R06 | PARTIAL | Label synthetic source and validate against independent published or real data |
| R07 | PARTIAL | Validate constraints on real hierarchy and run isolated PnR |
| PUB01 | PARTIAL | Extend to paced arrival and production phases without refitting this held-out cohort |
| PUB02 | PARTIAL | Crossover empirically confirmed; integrate into publication manuscript draft (PUB08) |
| PUB03 | PARTIAL | Freeze finite-key/first-EMIT predictions before new independent sessions, including split and ABORT regimes |
| PUB04 | PARTIAL | Design trusted monotonic durable storage and atomic authenticated commits; test reset/power-loss/old-snapshot restore before closing session accounting |
| PUB05 | PARTIAL | Preserve old profiler; fix new header/API and validate missing PL/IRQ phases |
| PUB06 | PARTIAL | Four-stage board ablation verified; extend paired dynamic profile, hysteresis switching and K1/K4 under paced traffic |
| PUB07 | PARTIAL | Complete staged qualification cohorts, then expand remaining QBER/code strata and tag/PA end-to-end fault statistics |
| PUB08 | TODO | Deferred per user instruction until hardware engineering is complete |

Ưu tiên: hoàn tất cohort đang chạy → kiểm thử tag với wrong codeword tự nhiên → đối chiếu mô hình đã đóng băng với dữ liệu board mới → fault recovery và security accounting → traffic/backlog/crossover thực → mở rộng thống kê và bản thảo. Các mục R là hướng phát triển riêng.

Nguồn: [work items](zc702_work_items.csv), [claim/evidence](zc702_claim_evidence.csv), [kế hoạch thực thi](ONGOING_RESEARCH_STAGES.md).
