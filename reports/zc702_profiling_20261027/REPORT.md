# Đợt triển khai đo pha PS/PL/UART, 27/10/2026

Đã bổ sung và chạy profiler trên ZC702 thật ở PL 50 MHz, không đổi RTL/bitstream. Profiler mặc định tắt; bật bằng op74, đọc lịch sử bằng op75. Hai clock được đối chiếu: global timer 64 bit và PMU cycle counter của Cortex-A9, theo tần số BSP; PL decoder có counter riêng.

| Phép thử | Kết quả đo và kiểm chứng | Bằng chứng |
|---|---|---|
| 36 ca K=1, bốn code, host delay 0/1/10 ms, ba lần lặp | 288 snapshot, 1.908 dòng phase; toàn bộ KEY và PA1024 khớp; PMU/global timer nhất quán | [Báo cáo](../zc702_phase_profile_20261027T015821Z/REPORT.md), [từng block](../zc702_phase_profile_20261027T015821Z/tung_block.csv), [từng pha](../zc702_phase_profile_20261027T015821Z/tung_pha.csv) |
| Đường IR per-block | Span load khoảng 17,6–18,0 µs; decode poll khoảng 36,6–738,8 µs tùy fixture | [CSV tổng hợp](../zc702_phase_profile_20261027T015821Z/tong_hop.csv) |
| Verification và PA1024 | Khoảng 23 µs/tag và 22,7 µs/PA call; gồm reset/cache/DMA | [Các span và scope](../zc702_phase_profile_20261027T015821Z/REPORT.md) |
| Buffer tích lũy → PA nhiều pass | 439 block/1.213.835 bit → 104.768 bit, 103 pass; output NTT bit-exact; PA calls 342,276 ms, finalize/wipe 42,179 ms | [Counter/report](../zc702_key_stream_20261027T020445Z/PROFILE_REPORT.md), [PA CSV](../zc702_key_stream_20261027T020445Z/profile_PA_emit.csv), [functional replay](../zc702_key_stream_20261027T020445Z/REPORT.md) |
| Hồi quy cap xác minh | 42 kiểm tra trên firmware có profiler, raw replay PASS; profiler mặc định tắt | [Báo cáo](../zc702_verification_budget_20261027T021157Z/REPORT.md) |
| Hồi quy stream ngắn sau cùng | Tag sai không append; hai block đúng/5.530 bit; reset/wipe PASS | [Báo cáo](../zc702_key_stream_20261027T021456Z/REPORT.md) |

UART functional transaction đo khoảng 0,70–1,00 s/block trên tập fixture này. Workload gồm đọc toàn bộ KEY và gửi expected PA để kiểm chứng, nên không gọi đó là latency của giao thức sản phẩm hay throughput khóa bí mật. Mỗi code dùng một fixture khác nhau; đây không phải ablation code rate. Host delay là sleep được chèn trước REVEAL, không phải RTT mạng quang hay Ethernet.

Các CSV ghi rõ phase parent/child và span chồng lấp. IR load là span setup/cache/start và drain quan sát từ PS, có hai DMA chạy đồng thời; PA call bao trùm các phase DMA con. Khoảng FAIL→REVEAL bao gồm UART, host và truyền ngược; không cộng nó vào tổng snapshot. Counter overhead chưa trừ; có dữ liệu read-pair để đánh giá các phase rất ngắn.

Đo PA lớn chỉ bật profiler sau ingest để không mất lịch sử 64 snapshot. 30 snapshot và 138 dòng phase được kiểm tra với raw TX/RX; 103 lần PA đều có span PMU valid. Global timer vẫn là nguồn wall time cho span dài; chu kỳ PS không được gọi là chu kỳ PL.

P06 và PUB05 chuyển sang **PARTIAL có số đo board**, giữ các gate còn thiếu: pure RTL PA counter/IRQ completion, full pipeline với arrival/backlog thật, đo đa context theo từng pha và điểm giao profile. Benchmark K/RTT DDR trước đó vẫn có [bằng chứng riêng](../zc702_latency_20261026T155148Z/REPORT.md). Chưa có ablation nhiều tầng trên cùng input ở board trong đợt này.

Alice/decoy/seed tiếp tục là mô phỏng công khai. Những kết quả trên xác nhận chức năng và thời gian phần cứng trong scope đã nêu, chưa chứng nhận an toàn QKD. Cap xác minh mới vẫn theo vòng đời firmware, chưa bền vững qua reset CPU/mất nguồn.

Nguồn mới: `firmware/zc702_uart/hw_profiler.h`, `syn/zc702/run_phase_profile.py`, `report_phase_profile.py`, `profile_protocol.py`, `report_stream_profile.py`. Đồ thị PNG/SVG nằm trong thư mục báo cáo 36 ca. Không có job Python nào còn chiếm COM3 sau các phép thử.
