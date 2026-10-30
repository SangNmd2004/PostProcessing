# Phân rã thời gian PS/PL/UART trên ZC702

Đã đối chiếu raw TX/RX cho 2 block lặp lại, 16 snapshot lệnh và 106 dòng phase. Toàn bộ KEY và PA1024 khớp golden/toán tham chiếu. Đây là workload chức năng K=1 với fixture công khai, không phải mẫu FER độc lập.

PL 50 MHz. Global timer 333.333.343 Hz, CPU/PMU 666.666.687 Hz; divider PMU đã tắt và tỷ lệ hai counter được kiểm tra. Chu kỳ PMU là chu kỳ PS CPU; `PL_decode_cycles` lấy riêng từ register PL và hiệu giữa các attempt. Span dài vượt khả năng xác định wrap CCNT 32 bit sẽ bị đánh dấu invalid; các span của run này đều valid.

| Code | Delay host µs | Attempts | Load PS µs | IR poll µs | Verify µs | PA1024 µs | Host transaction ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| r12 | 0 | 4 | 19.209 | 738.864 | 23.832 | 22.710 | 890.087 |
| r23 | 1000 | 2 | 17.946 | 207.054 | 23.463 | 22.746 | 771.064 |

Các file: `tung_pha.csv` (từng phase), `tung_lenh.csv` (RPC/board snapshot), `tung_block.csv`, `tong_hop.csv`. Min/max là độ trải của số lần lặp, không phải khoảng tin cậy FER.

**Đọc đúng overlap:** phase 2 bao trùm xử lý lệnh và printf; phase 13/14 bao trùm các phase DMA/cache con. Phase 11 bắt đầu khi PS thấy FAIL tới đầu lệnh REVEAL, bao gồm reply UART, chờ host và truyền ngược; nó chồng lên nhiều frame. Không cộng các parent với children hoặc cộng phase 11 vào tổng snapshot. `disjoint_compute_spans_us` chỉ cộng các span compute rời nhau đã instrument, không phải toàn bộ CPU overhead hay throughput end-to-end.

UART receive/ACK là wall span CPU, bao gồm ACK enqueue và host/USB waits. TX drain đo phần FIFO còn lại sau hàm lệnh; phần printf trong lệnh đã có truyền đồng thời. Host RPC đo bằng perf_counter_ns từ trước gửi header đến nhận đủ reply; không gồm ghi packet file trước lúc bắt đầu, nhưng host transaction gồm khoảng giữa các lệnh và sleep. Host sleep trước reveal không phải RTT mạng; dùng thời gian sleep thực tế đã lưu, không thay bằng giá trị yêu cầu.

Workload có đọc lại toàn bộ KEY và gửi expected PA để kiểm chứng, nên lượng UART lớn hơn giao thức sản phẩm. Không gọi nghịch đảo wall time này là tốc độ khóa bí mật. Có overhead đọc counter chưa trừ; chi phí read-pair lưu tại từng block. Verification/PA call bao gồm reset DMA, cache và chờ phần cứng; chưa tách pure PL PA bằng counter RTL riêng.

Chưa đo policy arrival/backlog crossover, lịch đa context bằng profiler này hoặc IRQ DMA thuần. Chưa đo PA tích lũy lớn trong run này; chỉ per-block 2.784 bit padded → 1.024 bit PA và tag64.

[Raw run](../../build/zc702/phase_profile_runs/20261027T015652Z/result.json).
