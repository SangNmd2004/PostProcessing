# Đo pha finite-key và PA nhiều pass trên buffer thật

Đã đối chiếu toàn bộ KEY/decoy/seed/output bằng report_key_stream trước khi kiểm tra counter. Nguồn Alice/decoy và seed vẫn mô phỏng công khai; clock điều khiển EMIT là replay ảo.

| Input bit | Output bit | Passes | PA calls ms | Mỗi pass µs | Chuẩn bị prefix µs | Finalize/wipe µs |
|---:|---:|---:|---:|---:|---:|---:|
| 1213835 | 104768 | 103 | 342.276 | 3323.072 | 162.495 | 42179.081 |

Counter là thời gian board thật, tách khỏi replay clock. Profiler bật sau ingest và đọc sau khi EMIT/output xong. Các phase PA reset/cache/DMA là con của PA call; không cộng trùng. Span nhận seed UART và output readback có trong profile_tung_lenh.csv. PA call chưa phải pure RTL latency; không quy đổi thành tốc độ khóa bí mật end-to-end. PC NTT reference tính giữa các command, ngoài board snapshot.

PMU spans invalid do wrap: 0. Các giá trị cycles chỉ cộng span valid; global timer 64 bit vẫn là nguồn wall time. Chưa có thí nghiệm nhiều mẫu/CI cho PA lớn; đây là một phiên functional có raw evidence đầy đủ.
