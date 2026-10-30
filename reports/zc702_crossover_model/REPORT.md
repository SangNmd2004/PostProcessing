# Báo Cáo Định Lượng Điểm Giao Thoa (Crossover) Giữa Hai Profile PUB02

- **Thời gian:** 20261027T050711Z
- **Hạng mục:** `PUB02` (Analytical $f$ and attempts model vs code/QBER/$r_0$/$\Delta$ and crossover proof)
- **Nguồn số đo phần cứng ZC702:** [tong_hop.csv](../zc702_phase_profile_20261027T015821Z/tong_hop.csv)
- **Mô hình toán:** [efficiency_throughput_crossover.py](../../model/efficiency_throughput_crossover.py)

## 1. Cơ Sở Dữ Liệu Thời Gian Phần Cứng Đo Thật Trên Kit (PL 50 MHz)

| Thành Phần Thực Thi | `EFFICIENCY` (Code `r34`, 5 attempt) | `THROUGHPUT` (Code `r56`, 1 attempt) | Đơn Vị |
|---|---:|---:|:---:|
| Nạp dữ liệu PS DMA (`median_PS_load_us`) | 17.68 | 17.95 | µs |
| Giải mã LDPC PL (`median_PS_ir_poll_us`) | 677.76 | 36.55 | µs |
| Xác minh Tag 64-bit (`verification_call_us`) | 23.39 | 23.41 | µs |
| Băm Hankel PA 1024-bit (`PA1024_call_us`) | 22.73 | 22.73 | µs |

## 2. Kết Quả Dự Đoán Điểm Giao Thoa Thông Lượng $\lambda^*$

### Cấu Hình Đơn Ngữ Cảnh ($K=1$)
- Công suất xử lý tối đa của `EFFICIENCY`: **1475.4 blocks/s** (bị giới hạn bởi thời gian giải mã 677.8 µs)
- Công suất xử lý tối đa của `THROUGHPUT`: **27356.0 blocks/s** (thời gian giải mã chỉ 36.6 µs)
- Điểm giao thoa thông lượng lý thuyết: **1941.4 blocks/s**
  - Khi $\lambda < \lambda^*$: `EFFICIENCY` cho tốc độ khóa bí mật cao hơn do hiệu suất rò rỉ tối ưu ($Y_E > Y_T$).
  - Khi $\lambda > \lambda^*$: `EFFICIENCY` chạm ngưỡng bão hòa (2037759 bit/s), trong khi `THROUGHPUT` tiếp tục tăng trưởng tới 28714248 bit/s.

### Cấu Hình 4 Ngữ Cảnh ($K=4$) Che Độ Trễ
- Nhờ 4 ngữ cảnh xen kẽ che RTT (hệ số tăng tốc $\sim \times 3.5$), công suất decoder tăng mạnh:
  - Công suất `EFFICIENCY` ($K=4$): **5164.0 blocks/s**
  - Công suất `THROUGHPUT` ($K=4$): **42724.1 blocks/s**
- Điểm giao thoa thông lượng dự đoán: **6794.8 blocks/s**

## 3. Ý Nghĩa Khoa Học Cho Bài Báo
- Chứng minh bằng toán học chặt chẽ và số đo phần cứng rằng việc chuyển đổi thích ứng giữa hai chế độ (`Backlog-Adaptive Switching`) là tối ưu: không bị kẹt ở mức thông lượng thấp khi tải cao, và không lãng phí khóa thô khi tải thấp.
