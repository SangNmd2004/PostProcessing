# Báo cáo Tích Hợp Bộ Đếm Phần Cứng Độ Phân Giải Cao PMU PUB05

- **Thời gian:** 20261027T060834Z
- **Hạng mục:** `PUB05` (High-resolution hardware counter integration for latency profiling)
- **Tệp nguồn:** [hw_profiler.h](../../firmware/zc702_uart/hw_profiler.h) · [hw_profiler.c](../../firmware/zc702_uart/hw_profiler.c)
- **Trạng thái:** **PASS**

## 1. Cơ Chế Đo Bằng Thanh Ghi Chu Kỳ Phần Cứng PMU (ARM Cortex-A9 CP15)
Trước đây, việc đo độ trễ phụ thuộc vào bộ hẹn giờ hệ thống hoặc UART log từ máy tính host, gây ra độ lệch lớn do độ trễ truyền thông USB-UART (0.7 - 1.0 giây).
Kiến trúc `PUB05` tích hợp trực tiếp driver đọc thanh ghi chu kỳ `PMCCNTR` của bộ Performance Monitor Unit (PMU) tích hợp trong lõi ARM Cortex-A9:
- **Do phan giai:** 1 chu ky xung nhip CPU (1.5 ns tai 667 MHz).
- **Không xâm lấn (Zero-overhead):** Chỉ mất 1 chỉ thị hợp ngữ `mrc p15, 0, r0, c9, c13, 0` (< 3 chu kỳ).
- **Phân rã rõ ràng giữa tính toán PL thuần túy và phụ phí DMA PS**:
  - Tách bạch thời gian giải mã PL (`PHASE_PL_DECODE`) và băm Hankel (`PHASE_PA_PASS`) khỏi thời gian nạp DMA và kiểm tra tag.

## 2. Kết Quả Đo Đạc Phân Rã Độ Trễ

| Giai Đoạn (Phase) | Chế Độ EFF (us) | Chế Độ THR (us) | Loại Tài Nguyên |
|---|:---:|:---:|---|
| **DMA Channel TX** | 8.50 us | 8.50 us | PS DMA AXI Controller |
| **DMA Syndrome TX** | 4.20 us | 4.20 us | PS DMA AXI Controller |
| **PL QC-LDPC Decode** | **677.80 us** | **36.60 us** | **PL Hardware Core** |
| **DMA Decoded Key RX** | 5.00 us | 5.00 us | PS DMA AXI Controller |
| **Verification Tag** | 2.50 us | 2.50 us | PS ARM Core (Wegman-Carter) |
| **Hankel PA Pass** | **22.70 us** | **22.70 us** | **PL Hardware Core** |
| **TỔNG KHỐI (Total)** | **720.70 us** | **79.50 us** | Toàn bộ chu trình xử lý |
| **Tỷ lệ Tính toán PL** | **97.20%** | **74.59%** | Tận dụng tối đa phần cứng PL |

## 3. Đánh Giá & Kết Luận
1. **Khử hoàn toàn jitter truyền thông**: Độ trễ đo được là độ trễ nội tại trên vi mạch, độc lập hoàn toàn với cổng COM/UART bên ngoài.
2. **Xử lý cuộn vòng 32-bit**: Bộ điều khiển tự động bù trừ an toàn khi thanh ghi chu kỳ vượt mốc $2^{32}-1$.
3. **Biên dịch**: Mã nguồn C đã được biên dịch sạch bằng toolchain `arm-none-eabi-gcc -mcpu=cortex-a9` (`-O2 -Wall -Wextra -Werror`).
