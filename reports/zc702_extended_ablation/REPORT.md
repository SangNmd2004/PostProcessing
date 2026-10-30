# Nghiên Cứu Đánh Đổi & Triệt Tiêu Suy Hao 6 Tầng Toàn Diện (PUB06)

- **Thời gian thực hiện:** 2026-10-27T07:24:18.265496+00:00
- **Hạng mục nghiên cứu:** `PUB06` (Controlled ablation study across all optimization layers)
- **Tập dữ liệu chuẩn hóa:** 1.000 khối BSC ($q = 3\%$, mã $r_{23}$, $N = 3072$, $D = 307$, $r_0 = 0$) ghép cặp trên phần cứng Xilinx ZC702 (PL 50.0 MHz) cho 4 tầng đầu.
- **Ranh giới kiểm chứng:** Tầng 1–4 là đo thực tế trên phần cứng ZC702; Tầng 5–6 là mô hình giải tích phóng chiếu (analytical projections), không phải kết quả nghiệm thu board.
- **Trạng thái:** **PARTIAL_FOUR_BOARD_TWO_PROJECTED**

---

## 1. Bảng Tổng Hợp 6 Tầng (4 Tầng Đo Thực Trên Kit + 2 Tầng Phóng Chiếu Mô Hình)

| Tầng | Tên Tối Ưu Hóa | Số Thử Nghiệm | Thành Công | Số Lần Thử TB | $f_{IR}$ TB | Thông Lượng (Mbit/s) | Tăng Tốc Tầng | Tăng Tốc Tích Lũy | Phân Loại Chứng Cứ |
|:---:|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| **L1** | **Baseline Blind** (OMS Random) | 1.000 | 998 | 1.727 | 1.4434 | 8.63 | — | **1.00x** | BOARD_VERIFIED (Baseline OMS) |
| **L2** | **+GS Puncturing** | 1.000 | 999 | 1.203 | 1.3714 | 18.35 | **+112.6%** | **2.13x** | BOARD_VERIFIED (Degree-matched GS) |
| **L3** | **+NMS-0.75 Decode** | 1.000 | 999 | 1.146 | 1.3638 | 24.18 | **+31.8%** | **2.80x** | BOARD_VERIFIED (NMS alpha=0.75) |
| **L4** | **+ET/PP** (Dừng sớm & Hậu xử lý) | 1.000 | 999 | 1.155 | 1.3650 | 27.48 | **+13.7%** | **3.18x** | BOARD_VERIFIED (ET=12, PP=1,2,16) |
| **L5** | **+Adaptive Backlog Switching** | Model | Model | N/A (Model) | N/A (Model) | 37.29 | **+35.7%** | **4.32x** | MODEL_PROJECTED (+35.7% queue gain) |
| **L6** | **+4-Context RTT Hiding** | Model | Model | N/A (Model) | N/A (Model) | 121.18 | **+225.0%** | **14.04x** | MODEL_PROJECTED (3.250x DDR model factor) |

---

## 2. Bảng Phân Tích Chênh Lệch Ghép Cặp (Paired Contrasts)

| Bước Chuyển Tầng | Thay Đổi Số Vòng Giải Mã | Giảm Hệ Số Tiết Lộ $\Delta f_{IR}$ | Tăng Thông Lượng (Mbit/s) | Tỷ Lệ Tăng Tốc Tầng | Tốc Độ So Với Gốc | Phân Loại |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **L1 $\to$ L2 (+GS Puncturing)** | -0.524 (-30.3%) | -0.0720 (-5.0%) | +9.72 | **+112.6%** | **2.13x** | Đo thực board |
| **L2 $\to$ L3 (+NMS-0.75)** | -0.057 (-4.7%) | -0.0076 (-0.6%) | +5.83 | **+31.8%** | **2.80x** | Đo thực board |
| **L3 $\to$ L4 (+ET/PP)** | +0.009 (+0.8%) | +0.0012 (+0.1%) | +3.30 | **+13.7%** | **3.18x** | Đo thực board |
| **L4 $\to$ L5 (+Adaptive Switching)** | Model | Model | +9.81 | **+35.7%** | **4.32x** | Phóng chiếu mô hình |
| **L5 $\to$ L6 (+4-Context Architecture)**| Model | Model | +83.89 | **+225.0%** | **14.04x** | Phóng chiếu mô hình |

---

## 3. Ranh Giới Nghiệm Thu & Diễn Giải Khoa Học

1. **Kết quả đo thực tế trên phần cứng ZC702 (Tầng 1–4)**:
   - Đo trên 1.000 khối BSC ghép cặp ($q = 3\%$).
   - Tăng thông lượng thực tế từ $8.63$ Mbit/s lên **$27.48$ Mbit/s** (hệ số tăng tốc **3.18x**).
   - $f_{IR}$ giảm từ $1.443$ xuống $1.365$.
2. **Phóng chiếu giải tích mô hình (Tầng 5–6)**:
   - Tầng 5 (+Adaptive switching) áp dụng hệ số mô phỏng hàng đợi (+35.7%).
   - Tầng 6 (+4-Context RTT Hiding) áp dụng hệ số mô hình DDR RTT (3.250x tại RTT = 1 ms).
   - Con số **$121.18$ Mbit/s** và **$14.04$x** được xác định là kết quả phóng chiếu mô hình (analytical model projection), KHÔNG PHẢI phép đo raw trực tiếp trên kit.
   - Nghiệm thu cấp độ board cho 6 tầng toàn vẹn yêu cầu thiết kế và đo kiểm thí nghiệm lưu lượng đồng thời trên cùng bộ dữ liệu.
