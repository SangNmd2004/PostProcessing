# Kiểm chứng mô hình hai tài nguyên trên workload held-out

Một decoder dùng chung, PS/DMA load/reveal tuần tự có thể chồng lên decode, context queue round robin. Cohort ET=PP=0, r0=0, chọn trước các job thành công strict trước iteration limit để công thức cycle không nhập nhằng đường USC. Model nhận trace attempts/iterations từ golden, chưa tự dự đoán trace hoặc FER từ QBER.

Training load intercept=21.603333 µs/job, retry cost=0.385628 µs/reveal bit. Chỉ fit các timing K1 training; tham số và model SHA đóng băng trước held-out. Tập trial/input hash training và held-out không giao nhau. Các vector từng được dùng trong ablation; timing validation K/RTT mới không được dùng để fit.

Chu kỳ decoder khớp đúng trên toàn bộ 66 batch calibration/validation. Latency mean absolute error=0.294%, max=1.117%. Tiêu chí kỹ thuật chốt trước: mean≤10%, max≤20%; kết quả ACCEPTED. PASS raw replay không tự đồng nghĩa đạt tiêu chí model.

| K | RTT µs | Median board µs | Prediction µs | Error % | Speedup vs K1 |
|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 8259 | 8289.227 | -0.365 | 1.000 |
| 2 | 0 | 6984 | 6906.883 | 1.117 | 1.183 |
| 4 | 0 | 7013 | 6936.577 | 1.102 | 1.178 |
| 1 | 100 | 10660 | 10689.227 | -0.273 | 1.000 |
| 2 | 100 | 7518 | 7511.850 | 0.082 | 1.418 |
| 4 | 100 | 7113 | 7036.577 | 1.086 | 1.499 |
| 1 | 500 | 20266 | 20289.227 | -0.114 | 1.000 |
| 2 | 500 | 11045 | 11034.520 | 0.095 | 1.835 |
| 4 | 500 | 7643 | 7581.837 | 0.807 | 2.652 |
| 1 | 1000 | 32262 | 32289.227 | -0.084 | 1.000 |
| 2 | 1000 | 17498 | 17500.260 | -0.013 | 1.844 |
| 4 | 1000 | 9928 | 9921.117 | 0.069 | 3.250 |
| 1 | 5000 | 128261 | 128289.227 | -0.022 | 1.000 |
| 2 | 5000 | 69499 | 69500.260 | -0.002 | 1.846 |
| 4 | 5000 | 37928 | 37921.117 | 0.018 | 3.382 |
| 1 | 10000 | 248262 | 248289.227 | -0.011 | 1.000 |
| 2 | 10000 | 134497 | 134500.260 | -0.002 | 1.846 |
| 4 | 10000 | 72927 | 72921.117 | 0.008 | 3.404 |

Chưa mô hình hóa riêng IRQ, KEY-output contention, phân bố arrival hoặc kênh UART sản phẩm. Per-job load intercept gộp overhead output/control trung bình, không phải đo load thuần. RTT được chèn sau khi PS phát hiện FAIL. Bốn vector lặp lại không phải FER samples độc lập và không phải secret-key throughput. Thứ tự config random, ba lần lặp; min/max không phải CI. Không hiệu chỉnh lại tham số bằng các điểm held-out trong báo cáo này.
