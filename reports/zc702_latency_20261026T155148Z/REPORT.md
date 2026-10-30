# IR latency benchmark trên ZC702

DDR replay, PL 50 MHz, timer Cortex-A9. Không có UART hoặc tính Python trong vòng được đo. Bốn vector chuẩn lặp lại, không phải mẫu FER độc lập; không phải thông lượng khóa bí mật hay hệ quang. Vòng đo có gồm kiểm tra correctness bằng golden trên PS. RTT là độ trễ thêm sau khi PS phát hiện FAIL trước REVEAL; không gồm lần trao đổi syndrome ban đầu hay RTT mạng thật.

| K | Reveal RTT µs | Median µs | Tăng tốc đo so K1 | IR Mbit/s | Sai số model % |
|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 13377 | 1.000 | 6.6143 | 0.00 |
| 2 | 0 | 10913 | 1.226 | 8.1078 | -18.42 |
| 4 | 0 | 10913 | 1.226 | 8.1078 | -18.42 |
| 1 | 100 | 19798 | 1.000 | 4.4691 | 0.11 |
| 2 | 100 | 11702 | 1.692 | 7.5611 | -12.52 |
| 4 | 100 | 11012 | 1.798 | 8.0349 | -17.68 |
| 1 | 1000 | 77389 | 1.000 | 1.1433 | 0.02 |
| 2 | 1000 | 39082 | 1.980 | 2.2640 | -2.15 |
| 4 | 1000 | 21565 | 3.589 | 4.1029 | -1.43 |
| 1 | 10000 | 653402 | 1.000 | 0.1354 | 0.00 |
| 2 | 10000 | 327087 | 1.998 | 0.2705 | -0.26 |
| 4 | 10000 | 174538 | 3.744 | 0.5069 | -0.11 |

Model được đóng băng sau K1/RTT0 trước điều kiện kiểm chứng. Là mô hình service trung bình đơn giản; khác biệt giữa vector, DMA/load/reveal và polling có thể gây sai số. Không hiệu chỉnh lại tham số từ dữ liệu held-out trong báo cáo này.

[Raw receipt](../../build/zc702/latency_runs/20261026T155148Z/result.json) · [UART](../../build/zc702/latency_runs/20261026T155148Z/uart.log)
