# Tiến độ toàn bộ dự án ZC702

Cập nhật: 2026-10-27T13:33:06+07:00.

Danh sách hiện có **35 mục được định danh**, không có mục thứ 36. Không tự tạo thêm mục để khớp một tổng số đã nêu trong trao đổi.

Đạt tiêu chí chức năng hiện có: **32/35 (91.4% theo số đầu mục)**. Không dùng tỷ lệ này làm tỷ lệ công sức, mức an toàn hay mức sẵn sàng sản phẩm.

| Nhóm | Tổng | Đạt trong phạm vi thử | Một phần/đang làm | Chưa làm |
|---|---:|---:|---:|---:|
| Chức năng trên board | 12 | 12 | 0 | 0 |
| Hoàn thiện hệ thống | 8 | 7 | 1 | 0 |
| Mô hình, thí nghiệm, bài báo | 8 | 7 | 0 | 1 |
| Hướng phát triển | 7 | 6 | 0 | 1 |

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
| P05 | PARTIAL | Critical path isolated to 11-level shifter tree; keep physical board at 50 MHz |
| R03 | TODO_RESEARCH | Skip Andes AE350; maintain 100% focus on Xilinx Zynq-7000 |
| PUB08 | TODO | Deferred per user instruction until hardware engineering is complete |

Ưu tiên: hoàn tất cohort đang chạy → kiểm thử tag với wrong codeword tự nhiên → đối chiếu mô hình đã đóng băng với dữ liệu board mới → fault recovery và security accounting → traffic/backlog/crossover thực → mở rộng thống kê và bản thảo. Các mục R là hướng phát triển riêng.

Nguồn: [work items](zc702_work_items.csv), [claim/evidence](zc702_claim_evidence.csv), [kế hoạch thực thi](ONGOING_RESEARCH_STAGES.md).
