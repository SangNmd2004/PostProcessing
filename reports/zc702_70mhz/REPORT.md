# Báo cáo Phân Tích Đóng Thời Gian 70 MHz Zynq PL P05

- **Thời gian:** 2026-10-27T06:01:00Z
- **Hạng mục:** `P05` (70 MHz Zynq PL system implementation and timing closure)
- **Tệp báo cáo STA:** [build/zc702_70mhz/timing_routed.rpt](../../build/zc702_70mhz/timing_routed.rpt)
- **Trạng thái:** **PARTIAL** (Đã hoàn thiện báo cáo phân tích đường trễ tới hạn; giữ nguyên baseline 50 MHz trên board vật lý theo quy chuẩn cam kết)

## 1. Phân Tích Đường Trễ Tới Hạn (Critical Path Analysis)
Phân tích thời gian tĩnh (Static Timing Analysis - STA) trên lưới định tuyến hiện tại của chip Zynq-7000 (`xc7z020clg484-1`) ở chu kỳ xung nhịp mục tiêu $T_{{clk}} = 14.286\\text{ ns}$ (70.0 MHz):
- **Worst Negative Slack (WNS)**: $-3.069\\text{ ns}$ (vi phạm điều kiện setup).
- **Worst Hold Slack (WHS)**: $+0.045\\text{ ns}$ (thỏa mãn điều kiện hold).
- **Đường trễ tới hạn**: Bắt đầu từ thanh ghi tầng thứ 5 của bộ dịch thùng quay `u_shifter/g_stage[5]` đi qua 11 mức cổng logic tổ hợp tới thanh ghi tính giá trị nhỏ nhất của cây nút kiểm tra `u_check_update/tree_min1_reg[5]`.
  - Độ trễ logic (Logic Delay): $5.120\\text{ ns}$ (30.9%).
  - Độ trễ đường dây (Net Routing Delay): $11.435\\text{ ns}$ (69.1%).

## 2. Giải Pháp Tối Ưu Đóng Thời Gian
1. **Chèn thanh ghi đường ống (Pipelining)**:
   - Cấu hình tham số `PIPE_AT = 3` trong [`qc_cyclic_shifter.v`](../../rtl/ldpc/qc_cyclic_shifter.v) để chèn 1 tầng flip-flop vào giữa bộ dịch 7-bit, ngắt đôi độ trễ tổ hợp.
2. **Quy hoạch mặt bằng Pblock**:
   - Áp dụng file ràng buộc [`floorplan_zc702.xdc`](../../syn/constraints/floorplan_zc702.xdc) để cô lập bộ giải mã trong vùng `X0Y1`, triệt tiêu đường dây chạy xuyên vùng.
   - Ước tính WNS sau tối ưu: $+2.466\\text{ ns}$ tại 70 MHz.

## 3. Nguyên Tắc Bảo Toàn Baseline
Theo quy chuẩn nghiêm ngặt của dự án:
- Board phần cứng ZC702 tiếp tục duy trì hoạt động ở **50.0 MHz** (WNS dương $+2.645\\text{ ns}$) để bảo đảm an toàn điện áp, nhiệt độ và tính ổn định tuyệt đối của các phép đo.
- Tuyệt đối không tuyên bố sai sự thật là "board ZC702 đang chạy ở 70 MHz".
