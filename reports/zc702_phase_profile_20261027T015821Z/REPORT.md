# Phân rã thời gian PS/PL/UART trên ZC702

Đã đối chiếu raw TX/RX cho 36 block lặp lại, 288 snapshot lệnh và 1908 dòng phase. Toàn bộ KEY và PA1024 khớp golden/toán tham chiếu. Đây là workload chức năng K=1 với fixture công khai, không phải mẫu FER độc lập. Mỗi code dùng một fixture chọn trước khác nhau; chênh lệch giữa code không phải ablation rate trên cùng input.

PL 50 MHz. Global timer 333.333.343 Hz, CPU/PMU 666.666.687 Hz; divider PMU đã tắt và tỷ lệ hai counter được kiểm tra. Chu kỳ PMU là chu kỳ PS CPU; `PL_decode_cycles` lấy riêng từ register PL và hiệu giữa các attempt. Span dài vượt khả năng xác định wrap CCNT 32 bit sẽ bị đánh dấu invalid; các span của run này đều valid.

| Code | Delay host µs | Attempts | Load PS µs | IR poll µs | Verify µs | PA1024 µs | Host transaction ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| r12 | 0 | 4 | 17.889 | 738.762 | 23.049 | 22.698 | 907.017 |
| r12 | 1000 | 4 | 17.931 | 738.801 | 23.409 | 22.728 | 922.911 |
| r12 | 10000 | 4 | 17.952 | 738.756 | 23.403 | 22.716 | 941.455 |
| r23 | 0 | 2 | 17.727 | 207.048 | 23.355 | 22.728 | 776.838 |
| r23 | 1000 | 2 | 17.766 | 207.027 | 23.415 | 22.710 | 775.676 |
| r23 | 10000 | 2 | 17.763 | 207.024 | 23.079 | 22.728 | 787.429 |
| r34 | 0 | 5 | 17.685 | 677.763 | 23.388 | 22.728 | 958.247 |
| r34 | 1000 | 5 | 17.700 | 677.742 | 23.415 | 22.389 | 975.244 |
| r34 | 10000 | 5 | 17.724 | 677.787 | 23.055 | 22.428 | 1000.549 |
| r56 | 0 | 1 | 17.946 | 36.555 | 23.406 | 22.731 | 702.802 |
| r56 | 1000 | 1 | 17.640 | 36.546 | 23.412 | 22.758 | 703.242 |
| r56 | 10000 | 1 | 17.625 | 36.564 | 23.040 | 22.710 | 703.433 |

Các file: `tung_pha.csv` (từng phase), `tung_lenh.csv` (RPC/board snapshot), `tung_block.csv`, `tong_hop.csv`. Min/max là độ trải của số lần lặp, không phải khoảng tin cậy FER.

**Đọc đúng overlap:** phase 2 bao trùm xử lý lệnh và printf; phase 13/14 bao trùm các phase DMA/cache con. Phase 11 bắt đầu khi PS thấy FAIL tới đầu lệnh REVEAL, bao gồm reply UART, chờ host và truyền ngược; nó chồng lên nhiều frame. Không cộng các parent với children hoặc cộng phase 11 vào tổng snapshot. `disjoint_compute_spans_us` chỉ cộng các span compute rời nhau đã instrument, không phải toàn bộ CPU overhead hay throughput end-to-end.

UART receive/ACK là wall span CPU, bao gồm ACK enqueue và host/USB waits. TX drain đo phần FIFO còn lại sau hàm lệnh; phần printf trong lệnh đã có truyền đồng thời. Host RPC đo bằng perf_counter_ns từ trước gửi header đến nhận đủ reply; không gồm ghi packet file trước lúc bắt đầu, nhưng host transaction gồm khoảng giữa các lệnh và sleep. Host sleep trước reveal không phải RTT mạng; dùng thời gian sleep thực tế đã lưu, không thay bằng giá trị yêu cầu. Cột delay là cấu hình mỗi lần reveal; ca một attempt (r56) không có reveal nên sleep thực tế bằng 0 ở cả ba cấu hình delay.

Workload có đọc lại toàn bộ KEY và gửi expected PA để kiểm chứng, nên lượng UART lớn hơn giao thức sản phẩm. Không gọi nghịch đảo wall time này là tốc độ khóa bí mật. Có overhead đọc counter chưa trừ; chi phí read-pair lưu tại từng block. Verification/PA call bao gồm reset DMA, cache và chờ phần cứng; chưa tách pure PL PA bằng counter RTL riêng.

Chưa đo policy arrival/backlog crossover, lịch đa context bằng profiler này hoặc IRQ DMA thuần. Chưa đo PA tích lũy lớn trong run này; chỉ per-block 2.784 bit padded → 1.024 bit PA và tag64.

[Raw run](../../build/zc702/phase_profile_runs/20261027T015821Z/result.json).


[Compute spans](compute_phase_breakdown.png) | [SVG](compute_phase_breakdown.svg) | [UART validation vs compute](UART_validation_vs_compute.png) | [SVG](UART_validation_vs_compute.svg).
