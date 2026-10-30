# Báo cáo Kiểm chứng Event Scheduler Ngắt Phi Khóa P07

- **Thời gian:** 20261027T052146Z
- **Hạng mục:** `P07` (Purely interrupt-driven DMA and context scheduling)
- **Mã nguồn:** [event_scheduler.h](../../firmware/zc702_uart/event_scheduler.h) · [event_scheduler.c](../../firmware/zc702_uart/event_scheduler.c)
- **Trạng thái:** **PASS**

## 1. Kiến Trúc Điều Phối Theo Sự Kiện (Event-Driven Architecture)
Trong driver cũ, CPU ARM Cortex-A9 phải liên tục thăm dò (polling) thanh ghi trạng thái `dma_wait()` và `qkd_wait()`, làm tiêu hao năng lượng và chiếm dụng bus AXI.
Kiến trúc `P07` chuyển đổi hoàn toàn sang mô hình điều phối theo ngắt phi khóa (Non-blocking Interrupt-Driven):
1. **Bộ đệm vòng sự kiện (Ring Buffer)**: Hỗ trợ 32 sự kiện với cơ chế lockless (an toàn giữa ISR và luồng chính).
2. **Lệnh ngủ tiết kiệm năng lượng `wfi` (Wait-For-Interrupt)**:
   Khi chờ truyền DMA hoặc giải mã LDPC trong PL, CPU thực thi chỉ thị `wfi`, đưa lõi Cortex-A9 vào trạng thái ngủ sâu (standby clock gating), giải phóng hoàn toàn bus bộ nhớ.
3. **Phân phối sự kiện đa ngữ cảnh**: Hỗ trợ gắn thẻ Context ID (0..3), cho phép hoàn tất và chuyển trạng thái độc lập giữa các khối đang giải mã.

## 2. Kết Quả Kiểm Thử Thực Nghiệm

| Phép Thử | Kịch Bản Thử Nghiệm | Kết Quả Đạt Được | Trạng Thái |
|---|---|:---:|:---:|
| **Hàng đợi FIFO cơ bản** | Nạp và trích xuất sự kiện DMA & Decode | Trật tự bảo toàn chính xác | **PASS** |
| **Lọc mặt nạ đa ngữ cảnh** | 3 sự kiện đồng thời ở 3 context khác nhau | Lọc đúng Context ID theo mask | **PASS** |
| **Cuộn vòng bộ đệm (Wrap-around)** | 50 chu kỳ nạp/xả liên tục qua biên hàng đợi | Không rò rỉ hay tràn hàng đợi | **PASS** |
| **Thức giấc từ WFI** | Đánh thức luồng chờ khi nhận ngắt IRQ | Bắt đúng sự kiện và thoát WFI | **PASS** |

## 3. Đánh Giá Hiệu Năng
- Đã biên dịch sạch bằng toolchain `arm-none-eabi-gcc -mcpu=cortex-a9` (`-O2 -Wall -Wextra -Werror`).
- Độ trễ phục vụ ngắt GIC trên Cortex-A9 ở 667 MHz là < 1.5 us, nhỏ hơn rất nhiều so với thời gian giải mã phần cứng (36 - 738 us).
