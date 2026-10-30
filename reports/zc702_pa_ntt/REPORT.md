# Báo cáo Nghiên cứu và Mô hình Hóa NTT Privacy Amplification R04

- **Thời gian:** 20261027T072418Z
- **Hạng mục:** `R04` (Large-block PA via NTT-based MMH-MH / Toeplitz hashing)
- **Tệp nguồn:** [pa_ntt_model.py](../../model/pa_ntt_model.py) · [pa_ntt_top.v](../../rtl/pa/pa_ntt_top.v)
- **Trạng thái:** **RESEARCH_FEASIBILITY_VERIFIED**

## 1. Hạn Chế Của Lõi Hankel Hiện Tại & Đột Phá Bằng Phép Biến Đổi NTT
Lõi PA Hankel phần cứng hiện tại trên ZC702 sử dụng kiến trúc mảng nhân ma trận - vector systolic với độ phức tạp tính toán:
O(n \cdot \ell)
- Ở khối nhỏ ($n = 2765$ bit, $\ell = 1024$ bit): Hankel xử lý chỉ mất **22.7 us**, nhanh hơn nhiều so với tốc độ kênh.
- Tuy nhiên, trong DV-QKD tích lũy khối lớn (Finite-Key Accumulation $N = 10^7 - 10^8$ bit để triệt tiêu tổn hao bảo mật):
  - Lõi Hankel đòi hỏi $> 10^{13}$ chu kỳ, mất hàng chục giây đến vài phút cho một phiên băm.
  - Ma trận Toeplitz/Hankel có tính chất dịch vòng, cho phép nhúng vào bài toán tích chập vòng (Cyclic Convolution) chiều dài $N_{conv} \ge n + \ell$:
Y = H \cdot X = INTT(NTT(X) \odot NTT(S))
Y = H \cdot X = INTT(NTT(X) \odot NTT(S))
## 2. Bảng So Sánh Hiệu Năng & Tốc Độ Tăng Tốc (Speedup)

| Kịch Bản Khối | Chiều Dài Khóa Vào $n$ | Chiều Dài Khóa Bí Mật $\ell$ | Thời Gian Hankel $O(n \cdot \ell)$ | Thời Gian NTT $O(N \log N)$ | Hệ Số Tăng Tốc (Speedup) | Bộ Nhớ DDR3 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **10 kbit** | $10^4$ | 1.024 | 1.60 ms | 0.88 ms | **1.8x** | 0.12 MB |
| **100 kbit** | $10^5$ | 16.384 | 256.0 ms | 8.85 ms | **28.9x** | 1.00 MB |
| **1 Mbit** | $10^6$ | 131.072 | 20.48 s | 158.33 ms | **129.3x** | 16.00 MB |
| **10 Mbit** | $10^7$ | 1.048.576 | 1638.40 s (~27 phút) | 1.83 s | **895.3x** | 128.00 MB |
| **100 Mbit** | $10^8$ | 10.485.760 | 131.072 s (~36 giờ) | 21.08 s | **6217.8x** | 1024.00 MB |

## 3. Khả Thi Phần Cứng & Ngân Sách Băng Thông DDR3 Trên ZC702
1. **Dung Lượng DDR3**:
   - Board ZC702 tích hợp 1 GB DDR3 SDRAM (Micron MT41J256M8HX-15E).
   - Với khối $10^7$ bit, bộ đệm NTT 32-bit chỉ chiếm **128 MB (12.5% RAM)**, hoàn toàn khả thi.
2. **Băng Thông AXI HP Slave**:
   - Cong PS HP AXI slave (High-Performance 64-bit bus @ 150 MHz) cung cap thong luong burst > 1200 MB/s.
   - Thời gian nạp/xả toàn bộ khối 10 Mbit qua Simple DMA chỉ mất **106.67 ms**.
   - Tổng thời gian hoàn tất phiên băm 10 Mbit: **1.94 s** (so với 27 phút của Hankel, nhanh hơn **895 lần**).
