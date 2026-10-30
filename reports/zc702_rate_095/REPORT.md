# Báo cáo Thiết Kế Mã QC-LDPC Tỷ Lệ Cao 0.95 và Tỷ Lệ Thấp 0.40 R02

- **Thời gian:** 20261027T072417Z
- **Hạng mục:** `R02` (High rate ~0.95 and low rate ~0.40 LDPC mother codes)
- **Tệp nguồn:** [ldpc_rate_095_matrix.py](../../model/ldpc_rate_095_matrix.py)
- **Báo cáo phân tích gốc:** [reports/RATE_095_FEASIBILITY.md](../RATE_095_FEASIBILITY.md)
- **Trạng thái:** **PASS**

## 1. Giải Quyết Điểm Nghẽn Hiệu Suất ở Vùng QBER Thấp (< 1%)
Trong hệ DV-QKD cự ly gần (< 20 km) hoặc kênh vệ tinh chất lượng cao, QBER thường rơi vào khoảng $0.2\% - 0.5\%$.
- Mã cao nhất hiện có trên ZC702 là $r_{56}$ ($R = 0.8333$, tiết lộ $16.67\%$ syndrome).
- Tại $QBER = 0.5\%$, entropy Shannon chỉ là $h_2(0.005) = 0.0454$.
- Do đó hệ số hiệu suất $f$ bị đội lên mức phi kinh tế:
  $$f = \frac{0.1667}{0.0454} = 3.67$$
  (làm tiêu hao tới $70\%$ lượng khóa bí mật tiềm năng do tiết lộ thừa thông tin).
- Với mã **$r_{95}$ ($R = 0.9500$, $N = 5120$, $M = 256$)**:
  - Lượng tiết lộ syndrome giảm xuống chỉ còn $5.0\%$.
  - Hệ số hiệu suất $f$ giảm mạnh từ **$3.67$ xuống $1.10$** (tiết kiệm **$70.0\%$ lượng thông tin tiết lộ**).

## 2. Bảng So Sánh Hiệu Suất f(QBER) ở Vùng QBER Thấp

| QBER | $h_2(QBER)$ | $f(QBER)$ với $r_{56}$ | $f(QBER)$ với $r_{95}$ | Mức Giảm $\Delta f$ | Khóa Tiết Lộ Được Giảm |
|:---:|:---:|:---:|:---:|:---:|:---:|
| **0.1%** | 0.01140 | 14.620 | **4.386** | -10.234 | 70.0% |
| **0.2%** | 0.02071 | 8.049 | **2.414** | -5.635 | 70.0% |
| **0.3%** | 0.02934 | 5.682 | **1.704** | -3.978 | 70.0% |
| **0.4%** | 0.03756 | 4.438 | **1.331** | -3.107 | 70.0% |
| **0.5%** | 0.04541 | 3.670 | **1.101** | -2.569 | 70.0% |
| **0.7%** | 0.06029 | 2.765 | **0.829** (Vượt capacity) | N/A | 70.0% |
| **1.0%** | 0.08079 | 2.063 | **0.619** (Vượt capacity) | N/A | 70.0% |

> **Khuyến nghị hoạt động**: Mã $r_{95}$ tối ưu nhất trong dải $QBER \in [0.2\%, 0.55\%]$. Khi $QBER > 0.6\%$, kênh tự động chuyển sang $r_{56}$ và $r_{34}$.

## 3. Kế Hoạch Mở Rộng ABI & Giao Tiếp Phần Cứng
1. Mở rộng thanh ghi cấu hình `CFG[2:0]` từ 2 bit lên 3 bit:
   - `3'd0`: $r_{12}$ ($R=0.50$, $M_b=12$, $N_b=24$)
   - `3'd1`: $r_{23}$ ($R=0.67$, $M_b=8$, $N_b=24$)
   - `3'd2`: $r_{34}$ ($R=0.75$, $M_b=6$, $N_b=24$)
   - `3'd3`: $r_{56}$ ($R=0.83$, $M_b=4$, $N_b=24$)
   - `3'd4`: $r_{95}$ ($R=0.95$, $M_b=2$, $N_b=40$)
   - `3'd5`: $r_{40}$ ($R=0.42$, $M_b=14$, $N_b=24$)
2. Cập nhật bảng ROM điều phối tầng và số lượng từ DMA syndrome tương ứng.
