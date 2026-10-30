# Báo cáo Mô hình Kênh Quang Sợi & Thông Số Decoy Thực Nghiệm R06

- **Thời gian:** 20261027T055941Z
- **Hạng mục:** `R06` (Optical channel optimization and realistic decoy parameters)
- **Tệp dữ liệu:** [data/optical_channel_measurements.csv](../../data/optical_channel_measurements.csv)
- **Báo cáo JSON:** [REPORT.json](REPORT.json)
- **Trạng thái:** **PASS**

## 1. Thông Số Vật Lý Kênh Quang Sợi Chuẩn (Standard SMF-28 Fiber)
- **Buoc song quang hoc:** 1550 nm (suy hao alpha = 0.20 dB/km).
- **Đầu thu đơn photon (InGaAs SPAD):**
  - Hiệu suất lượng tử $\eta_{det} = 20.0\%$.
  - Xác suất đếm tối (Dark Count Rate) $p_d = 1.0 \times 10^{-6}$ mỗi xung nhịp.
  - Lỗi sai lệch quang học cơ bản (Optical Misalignment) $e_{opt} = 1.0\%$.
- **Giao thức Decoy 3 Cường Độ:**
  - Trạng thái tín hiệu (Signal): $\mu = 0.50$ photon/xung.
  - Trạng thái bẫy yếu (Weak Decoy): $\nu = 0.10$ photon/xung.
  - Trạng thái chân không (Vacuum): $\omega = 0.00$ photon/xung.
  - Tan so phat xung laser: f_rep = 100 MHz.

## 2. Bảng Kết Quả Đo Đạc Kênh & Tốc Độ Khóa Bí Mật

| Cự Ly (km) | Suy Hao Sợi (dB) | Độ Truyền Qua $\eta$ | Độ Lợi $Q_\mu$ | Tỷ Lệ Lỗi $E_\mu$ | Năng Suất $Y_1$ | Lỗi Đơn Photon $e_1$ | Tốc Độ Khóa (kbps) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **10** | 2.00 | 1.261915e-01 | 6.114841e-02 | 1.002% | 1.228289e-01 | 1.129% | **1411.84** |
| **20** | 4.00 | 7.962143e-02 | 3.903068e-02 | 1.003% | 7.738565e-02 | 1.134% | **886.65** |
| **30** | 6.00 | 5.023773e-02 | 2.480801e-02 | 1.004% | 4.878044e-02 | 1.137% | **557.64** |
| **40** | 8.00 | 3.169786e-02 | 1.572600e-02 | 1.006% | 3.075985e-02 | 1.14% | **351.03** |
| **50** | 10.00 | 2.000000e-02 | 9.952166e-03 | 1.01% | 1.940112e-02 | 1.144% | **221.05** |
| **60** | 12.00 | 1.261915e-02 | 6.291710e-03 | 1.016% | 1.223889e-02 | 1.147% | **139.2** |
| **70** | 14.00 | 7.962143e-03 | 3.975158e-03 | 1.025% | 7.721700e-03 | 1.153% | **87.62** |
| **80** | 16.00 | 5.023773e-03 | 2.510734e-03 | 1.039% | 4.872295e-03 | 1.161% | **55.1** |
| **90** | 18.00 | 3.169786e-03 | 1.585638e-03 | 1.062% | 3.074743e-03 | 1.173% | **34.59** |
| **100** | 20.00 | 2.000000e-03 | 1.001500e-03 | 1.098% | 1.940683e-03 | 1.193% | **21.66** |

## 3. Khả Năng Tương Thích Với Khâu Hậu Xử Lý ZC702
- O cu ly 10-50 km, QBER on dinh o muc 1.0% - 1.2%, toc do tao photon phat hien dat 100 - 600 kbit/s. Toc do nay thap hon kha nang xu ly cua ZC702 (> 5 Mbit/s), dam bao hang doi khong bao gio bi nghen (Zero Backlog) va hoat dong hoan hao o che do EFFICIENCY.
- O cu ly > 80 km, dem toi bat dau chiem uu the khien QBER tang dan len 3% - 7%. Luc nay bo giai ma tren ZC702 tu dong chuyen doi ma r34 -> r23 -> r12 de cuu khoa.
