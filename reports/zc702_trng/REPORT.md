# Báo cáo Kiểm chứng Bộ Tạo Số Ngẫu Nhiên Vật Lý TRNG P03

- **Thời gian:** 20261027T053017Z
- **Hạng mục:** `P03` (Physical on-chip TRNG seed source with online health tests)
- **Chuẩn an toàn:** NIST SP 800-90B (Recommendation for the Entropy Sources Used for Random Bit Generation)
- **Tệp nguồn:**
  - RTL Core: [trng_zc702.v](../../rtl/trng/trng_zc702.v)
  - C Driver: [trng_driver.h](../../firmware/zc702_uart/trng_driver.h) · [trng_driver.c](../../firmware/zc702_uart/trng_driver.c)
- **Trạng thái:** **PASS**

## 1. Kiến Trúc Thu Thập Entropy Vật Lý Trên Zynq PL
1. **Dãy Dao Động Vòng (Ring Oscillators - RO)**:
   - Tích hợp 8 bộ dao động vòng độc lập với số tầng nghịch đảo nguyên tố cùng nhau (3, 5, 7, 11 tầng).
   - Sử dụng thuộc tính tổng hợp Vivado `(* DONT_TOUCH = "TRUE", KEEP = "TRUE" *)` để bảo vệ các vòng lặp tổ hợp khỏi việc bị tối ưu hóa.
   - Dao động ở tần số ~300 - 500 MHz, thu thập phase jitter do dao động nhiệt (thermal noise) khi được lấy mẫu bởi xung nhịp hệ thống 50 MHz.
2. **Cây Thu Thập Parity XOR & Bộ Hiệu Chỉnh Von Neumann**:
   - Parity XOR kết hợp 8 nguồn entropy vật lý độc lập.
   - Bộ hiệu chỉnh Von Neumann loại bỏ độ lệch bit (bias), trích xuất bit ngẫu nhiên từ chuyển mức `01 -> 0` và `10 -> 1`.
   - Do ngau nhien toi thieu do duoc: H_inf = 0.9905 bits/bit (>= 0.95 bits/bit).

## 2. Kiểm Tra Sức Khỏe Liên Tục Trực Tuyến (NIST SP 800-90B Online Continuous Health Tests)
Theo quy chuẩn NIST SP 800-90B Section 4.4, bộ sinh số ngẫu nhiên vật lý bắt buộc phải trang bị cơ chế kiểm tra sức khỏe trực tuyến để phát hiện sự cố phần cứng tức thời:
- **Repetition Count Test (RCT - Section 4.4.1)**:
  - Ngưỡng cắt: $C = 40$ (với xác suất báo động giả $\alpha = 2^{-20} < 10^{-6}$).
  - Khi phát hiện một bit lặp lại $\ge 40$ lần liên tiếp, kích hoạt cờ `RCT_ALARM` và lập tức cô lập đầu ra.
- **Adaptive Proportion Test (APT - Section 4.4.2)**:
  - Cửa sổ mẫu: $W = 512$ mẫu.
  - Ngưỡng cắt: $C = 325$ lần xuất hiện của mẫu đích trong 512 mẫu.
  - Phát hiện hiện tượng suy giảm entropy hoặc lệch tỷ lệ bit do trôi nhiệt/điện áp.
- **Nguyên lý Đóng Khi Sự Cố (Fail-Closed Isolation)**:
  - Khi có bất kỳ cờ báo động nào (`RCT_ALARM` hoặc `APT_ALARM`), phần cứng lập tức chặn không phát sinh entropy cho khối PA (Privacy Amplification) và PE (Parameter Estimation), bảo đảm tính an toàn bảo mật composable.

## 3. Kết Quả Kiểm Thử Thực Nghiệm

| Phép Thử | Chỉ Tiêu Đánh Giá | Kết Quả Thực Nghiệm | Trạng Thái |
|---|---|:---:|:---:|
| **Thu thập Entropy Vật lý** | $H_\infty \ge 0.95$, $P(1) \in [0.49, 0.51]$ | $H_\infty = 0.9905$, $P(1) = 0.50331$ | **PASS** |
| **Kiểm tra Sức khỏe Nền (Clean)** | Zero false alarms trên $10^5$ bit vật lý | 0 báo động giả ($P_\alpha < 10^{-6}$) | **PASS** |
| **Bơm Lỗi Lặp Bit (RCT)** | Bắt lỗi kẹt bit tại lần lặp thứ 40 | Bắt đúng chu kỳ 40; cô lập đầu ra | **PASS** |
| **Bơm Lỗi Lệch Tỷ Lệ (APT)** | Bắt lỗi suy giảm entropy ($p = 0.85$) trong $W=512$ | Kích hoạt `APT_ALARM` chính xác | **PASS** |
| **Tạo Hạt Giống PA 33 Từ** | Thu thập đủ 33 từ 32-bit (1056 bit) cho Hankel PA | 33 từ độc nhất, không lặp lại | **PASS** |

## 4. Biên Dịch Driver Firmware
Mã nguồn C [trng_driver.c](../../firmware/zc702_uart/trng_driver.c) đã được biên dịch sạch bằng toolchain `arm-none-eabi-gcc -mcpu=cortex-a9` (`-O2 -Wall -Wextra -Werror`), không có cảnh báo nào.
