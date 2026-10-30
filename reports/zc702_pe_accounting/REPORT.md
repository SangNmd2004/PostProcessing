# Báo cáo Kiểm chứng Hạng mục P02: PE Accounting & Sample Removal

- **Thời gian:** 20261027T045353Z
- **Hạng mục:** `P02` (PE sample leakage removal and exact error counting)
- **Trạng thái:** **PASS**
- **Nguồn:** [pe_accounting.c](../../firmware/zc702_uart/pe_accounting.c) · [pe_accounting.h](../../firmware/zc702_uart/pe_accounting.h)

## 1. Cơ Chế Xử Lý Mẫu Ước Lượng Lỗi (PE)

| Chế Độ | Cơ Chế Thu Thập Mẫu | Số Bit Khóa Bị Lộ | Độ Dài Đầu Vào PA (bit) | Lượng Rò Rỉ $\text{leak}_{\text{PE}}$ | Đảm Bảo An Toàn Composable |
|---|---|---:|---:|---:|---|
| **Mode A** *(Independent X-basis)* | Mẫu trích từ cơ sở đo $X$ (xung kiểm thử) | **0** | $2765$ | $0$ | $I(E; Z \mid X) = 0$; không rò rỉ khóa bí mật |
| **Mode B1** *(Z-basis Physical Removal)* | Mẫu 256-bit lấy từ khối $Z$, loại bỏ trước PA | $256$ | **$2509$** ($2765 - 256$) | $0$ (đã cắt bỏ) | Bit công bố bị triệt tiêu vật lý trước băm Hankel |
| **Mode B2** *(Z-basis Leakage Inflation)* | Mẫu 256-bit giữ trong PA, tính bù rò rỉ | $256$ | $2765$ | **$+256$** bit | Eve bị trừ toàn bộ thông tin qua nén ma trận PA |

## 2. Kiểm Chứng Bitwise C-Level
- Đã kiểm tra hàm trích và dồn bit `pe_remove_sample_bits` trên $2765$ bit với mặt nạ ngẫu nhiên $256$ bit:
  - Khối sau dồn: **chính xác $2509$ bit** ($79$ từ `uint32_t`).
  - Đối chiếu bit-exact $100\%$ giữa triển khai C và Python reference.
- Đã biên dịch sạch bằng toolchain `arm-none-eabi-gcc` (`-O2 -Wall -Wextra -Werror`).

## 3. Phân Bổ Ngân Sách An Toàn $\varepsilon_{\text{PE}}$
- Cận dao động hữu hạn Serfling/Hoeffding:
  $$\phi_1 \le e_1^U + \sqrt{\frac{n_k + n_t}{2 n_k n_t} \ln\left(\frac{1}{\varepsilon_{\text{PE}}}\right)}$$
- Với $\varepsilon_{\text{PE}} = 10^{-10}$, $n_k = n_t = 2600$, độ bù dao động là $\delta \approx 0.0941$, thỏa mãn cận an toàn composable toàn phiên.
