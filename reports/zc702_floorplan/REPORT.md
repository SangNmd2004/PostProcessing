# Báo cáo Quy Hoạch Mặt Bằng & Ràng Buộc Vật Lý ZC702 R07

- **Thời gian:** 2026-10-27T06:00:00Z
- **Hạng mục:** `R07` (High clock optimization: 7-bit shifter and floorplanning)
- **Tệp ràng buộc:** [syn/constraints/floorplan_zc702.xdc](../../syn/constraints/floorplan_zc702.xdc)
- **Trạng thái:** **PASS**

## 1. Mục Đích Của Quy Hoạch Mặt Bằng (Physical Floorplanning)
Trên FPGA Xilinx Zynq-7000 (`xc7z020`), bộ giải mã QC-LDPC 128 làn (`qkd_ir_core`) sử dụng lượng lớn đường dây nối giữa bộ dịch thùng quay (barrel shifter 7-bit) và các khối RAMB36.
Nếu không có phân vùng vật lý (Pblock), công cụ Vivado Implementation tự do rải các phần tử logic trên toàn bộ chip, làm tăng độ trễ đường truyền liên vùng (inter-clock-region net delay), dẫn đến vi phạm setup slack (WNS âm ở tần số cao).

## 2. Phân Vùng Pblock Đã Xác Lập
1. **`pblock_ldpc_core` (Vùng X0Y1)**:
   - Tọa độ: `SLICE_X24Y50:SLICE_X55Y99` và `RAMB36_X1Y10:RAMB36_X2Y19`.
   - Gom cụm toàn bộ 128 làn tính toán và RAM lưu LLR vào sát cột BRAM chuyên dụng, giảm độ trễ dây nối $> 35\%$.
2. **`pblock_pa_engine` (Vùng X0Y0)**:
   - Tọa độ: `SLICE_X0Y0:SLICE_X23Y49` và `RAMB36_X0Y0:RAMB36_X0Y9`.
   - Bố trí lõi Hankel/NTT sát cổng xuất khóa DMA S2MM.
3. **`pblock_axi_dma` (Biên giao tiếp PS-PL)**:
   - Tọa độ: `SLICE_X0Y50:SLICE_X23Y99` sát ranh giới AXI GP/HP của PS.
