# Báo cáo Kiểm chứng Kênh Xác Thực Cổ Điển Wegman-Carter P04

- **Thời gian:** 20261027T072419Z
- **Hạng mục:** `P04` (Authenticated classical Alice-Bob channel)
- **Mã nguồn:** [auth_channel.h](../../firmware/zc702_uart/auth_channel.h) · [auth_channel.c](../../firmware/zc702_uart/auth_channel.c)
- **Trạng thái:** **PASS**

## 1. Cơ Chế Xác Thực Thông Tin Lý Thuyết (Information-Theoretic Security)
Trong giao thức DV-QKD, kênh trao đổi cổ điển (syndrome, reveal bits, tag, accumulator commands) được bảo vệ bằng mã xác thực thông điệp Wegman-Carter (1981):
1. **Băm phổ quát trên trường Galois $\mathbb{F}_{2^{64}}$**:
   Sử dụng đa thức bất khả quy $P(x) = x^{64} + x^4 + x^3 + x + 1$ để tính toán hash đa thức bậc $L$:
   $$H_k(m) = \bigoplus_{i=1}^L m_i \cdot k^{L - i + 1}$$
2. **Mặt nạ One-Time Pad (OTP)**:
   Mã MAC 64-bit được che phủ bằng khóa OTP suy dẫn từ khóa bí mật chia sẻ trước (PSK) và số thứ tự gói tin $\text{seq}$:
   $$\text{MAC}(m, \text{seq}) = H_k(m) \oplus \text{OTP}(\text{seq})$$
3. **Xác suất giả mạo**: $\varepsilon_{\text{auth}} \le 2^{-64}$ trên mỗi gói tin.

## 2. Kết Quả Kiểm Thử Khả Năng Kháng Tấn Công

| Phép Thử An Toàn | Kịch Bản Thử Nghiệm | Tỷ Lệ Phát Hiện / Chặn | Trạng Thái |
|---|---|:---:|:---:|
| **Toàn vẹn gói tin hợp lệ** | Trao đổi gói tin đa dạng (Syndrome, Reveal, Tag, Emit) | $4/4$ thành công | **PASS** |
| **Kháng can thiệp 1-bit (Tamper)** | Đảo ngẫu nhiên 1 bit trong payload của 50 gói | **50/50 bị chặn (100.0%)** | **PASS** |
| **Kháng phát lại (Anti-Replay)** | Phát lại gói tin hợp lệ cũ có $\text{seq} \le \text{last\_seq}$ | **Chặn ngay lập tức** | **PASS** |
| **Can thiệp Header / Magic** | Sửa đổi magic word `0x51415554` | **Chặn ngay lập tức** | **PASS** |

## 3. Đánh Giá Khép Kín An Toàn
- Mã nguồn C đã được kiểm tra biên dịch bằng `arm-none-eabi-gcc` (`-O2 -Wall -Wextra -Werror`).
- Đảm bảo cơ chế **Fail-Closed**: Mọi gói tin sai tag MAC hoặc vi phạm thứ tự sequence đều bị loại bỏ ngay tại lớp giải gói; không đi vào pipeline giải mã hay bộ gom khóa.
