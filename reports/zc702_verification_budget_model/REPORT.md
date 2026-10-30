# Báo cáo Phân Tích Ngân Sách Xác Minh & Cận An Toàn Composable PUB04

- **Thời gian:** 20261027T050408Z
- **Hạng mục:** `PUB04` (Cumulative correctness security bound $\varepsilon_{\text{cor}} \le N \cdot 2^{-64}$ tag budget analysis)
- **Mã nguồn:** [session_persistence.h](../../firmware/zc702_uart/session_persistence.h) · [session_persistence.c](../../firmware/zc702_uart/session_persistence.c)
- **Trạng thái:** **PASS**

## 1. Cơ Sở Toán Học & Cận Hợp (Union Bound)
Trong giao thức DV-QKD, mỗi thẻ tag băm Hankel 64-bit có xác suất đụng độ tối đa $2^{-64}$ dưới khóa băm ngẫu nhiên độc lập.
Đối với phiên làm việc gồm $N$ lần kiểm tra tag (bao gồm cả các tag hợp lệ và tag bị từ chối):
$$\varepsilon_{\text{cor}}^{\text{session}} \le \sum_{i=1}^N \varepsilon_{\text{cor}}^{(i)} \le N \cdot 2^{-64}$$

Với ngân sách an toàn composable chuẩn $\varepsilon_{\text{cor}} = 10^{-15}$:
$$N_{\max} = \lfloor 10^{-15} \cdot 2^{64} \rfloor = \mathbf{18.446\text{ khối}}$$
Khối lượng khóa thô tối đa tương ứng ($n=3072$, $2765$ bit khóa):
$$\text{Volume}_{\max} = 18.446 \times 2765\text{ bit} \approx \mathbf{51.0\text{ Mbit}}$$

## 2. Bảng Đánh Đổi Ngân Sách $\varepsilon_{\text{cor}}$

| Ngân Sách $\varepsilon_{\text{cor}}$ | Số Khối Kiểm Tra Tối Đa ($N_{\max}$) | Dung Lượng Khóa Thô Tối Đa |
|:---:|:---:|:---:|
| $10^{-16}$ | **1,844** | 5.1 Mbit |
| $10^{-15}$ | **18,446** | 51.0 Mbit |
| $10^{-14}$ | **184,467** | 510.1 Mbit |
| $10^{-12}$ | **18,446,744** | 51005.2 Mbit |

## 3. Đánh Giá Phiên Tích Lũy Lớn 16 Mbit ($5.786$ Khối)

| Tỷ Lệ Discard/Tag Lỗi | Khối Cần Giữ | Tổng Lượt Kiểm Tra | $\varepsilon_{\text{cor}}$ Tiêu Thụ | Tỷ Lệ Chiếm Ngân Sách | Trạng Thái |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 0% | 5787 | 5787 | 3.137e-16 | **31.37%** | PASS |
| 10% | 5787 | 6430 | 3.486e-16 | **34.86%** | PASS |
| 30% | 5787 | 8268 | 4.482e-16 | **44.82%** | PASS |
| 50% | 5787 | 11574 | 6.274e-16 | **62.75%** | PASS |

**Kết luận an toàn:** Thậm chí ở kịch bản kênh suy hao nặng với tỷ lệ loại bỏ $50\%$ (phải thử $11.572$ lượt), tổng số lần kiểm tra vẫn chỉ chiếm $62.73\%$ ngân sách tối đa, đảm bảo an toàn tuyệt đối dưới ngưỡng $10^{-15}$.

## 4. Kiến Trúc Lưu Trữ Bền Vững (Session Persistence)
- Triển khai descriptor [session_persistence.c](../../firmware/zc702_uart/session_persistence.c) lưu trong bộ nhớ On-Chip Memory (OCM tại `0xFFFC0000`) sống sót qua các lần warm-reset của ARM Cortex-A9.
- Bộ đếm đơn điệu chống tấn công reset-rollback (`budget_used` không thể bị giảm trừ khi tái xác thực với Alice qua kênh cổ điển có xác thực).
- Kiểm tra toàn vẹn CRC-32 và cơ chế **Fail-Closed Lockout** nếu phát hiện can thiệp vào bộ nhớ bền vững.
