# Báo cáo Mô Phỏng Lưu Lượng Điều Tốc & Điểm Giao Thoa PUB02 / P06

- **Thời gian:** 20261027T072418Z
- **Hạng mục:** `P06` (Throughput & 4-context benchmark) · `PUB01` (Queueing model) · `PUB02` (Profile crossover proof)
- **Tệp nguồn:** [run_paced_arrival_benchmark.py](../../syn/zc702/run_paced_arrival_benchmark.py) · [efficiency_throughput_crossover.py](../../model/efficiency_throughput_crossover.py)
- **Ranh giới kiểm chứng:** **Mô phỏng hàng đợi sự kiện rời rạc dựa trên tham số đo kit; KHÔNG PHẢI phép đo luồng arrival trực tiếp qua UART/JTAG.**
- **Trạng thái:** **PARTIAL_QUEUE_SIMULATION_EVALUATED**

## 1. Thiết Kế Mô Phỏng Lưu Lượng Điều Tốc (Paced Traffic Model)
Mô phỏng quá trình phát sinh khối photon thô theo tốc độ điều tốc $\lambda$ (blocks/s) quét qua điểm giao thoa lý thuyết:
- **Đơn ngữ cảnh (K=1)**: $\lambda^* = 1941.4$ blocks/s (~5.37 Mbit/s raw key).
- **Đa ngữ cảnh (K=4)**: $\lambda^* = 6794.8$ blocks/s (~18.8 Mbit/s raw key).

Mỗi kịch bản so sánh 3 chính sách điều phối:
1. **EFFICIENCY Cố Định**: Ưu tiên năng suất khóa ($Y_{eff} = 1382.5$ bit/block), độ trễ giải mã 677.8 us.
2. **THROUGHPUT Cố Định**: Ưu tiên thông lượng ($Y_{thr} = 1050.7$ bit/block), hội tụ sau 1 vòng (36.6 us).
3. **ADAPTIVE (Hysteresis)**: Tự động chuyển `THROUGHPUT` khi hàng đợi $Q \ge 4$ và hồi về `EFFICIENCY` khi $Q \le 1$.

## 2. Bảng Kết Quả Mô Phỏng Đơn Ngữ Cảnh (K = 1)

| Tốc Độ $\lambda$ (blocks/s) | EFF Secret (Mbit/s) | THR Secret (Mbit/s) | ADAPTIVE Secret (Mbit/s) | Hàng Đợi EFF | Hàng Đợi THR | Chính Sách Thắng |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **500** | 0.661 | 0.503 | 0.659 | 0.09 | 0.00 | **EFFICIENCY** |
| **1000** | 1.471 | 1.119 | 1.429 | 1.49 | 0.00 | **EFFICIENCY** |
| **1500** | 1.868 | 1.494 | 1.863 | 34.58 | 0.01 | **EFFICIENCY** |
| **1941** | 1.868 | 2.020 | 2.407 | 58.82 | 0.02 | **THROUGHPUT** |
| **2500** | 1.869 | 2.624 | 3.005 | 61.05 | 0.03 | **THROUGHPUT** |
| **3500** | 1.869 | 3.652 | 3.997 | 62.34 | 0.06 | **THROUGHPUT** |
| **5000** | 1.869 | 5.369 | 5.637 | 63.06 | 0.17 | **THROUGHPUT** |

## 3. Bảng Kết Quả Mô Phỏng Đa Ngữ Cảnh (K = 4)

| Tốc Độ $\lambda$ (blocks/s) | EFF Secret (Mbit/s) | THR Secret (Mbit/s) | ADAPTIVE Secret (Mbit/s) | Hàng Đợi EFF | Hàng Đợi THR | Chính Sách Thắng |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **2000** | 2.783 | 2.115 | 2.766 | 0.25 | 0.01 | **EFFICIENCY** |
| **4000** | 5.454 | 4.148 | 5.157 | 25.46 | 0.05 | **EFFICIENCY** |
| **6000** | 5.530 | 6.311 | 7.287 | 61.64 | 0.13 | **THROUGHPUT** |
| **6795** | 5.530 | 7.003 | 7.925 | 62.65 | 0.15 | **THROUGHPUT** |
| **8000** | 5.530 | 8.456 | 9.223 | 62.73 | 0.29 | **THROUGHPUT** |
| **10000** | 5.530 | 10.349 | 10.909 | 63.28 | 0.67 | **THROUGHPUT** |
| **15000** | 5.530 | 15.000 | 14.997 | 63.68 | 54.62 | **THROUGHPUT** |

## 4. Kết Luận Khoa Học & Ranh Giới Nghiệm Thu
1. **Điểm giao thoa lý thuyết $\lambda^*$**:
   - Dưới $\lambda^*$: `EFFICIENCY` tối ưu hóa năng suất khóa hữu hạn, đạt thông lượng cao hơn.
   - Vượt $\lambda^*$: năng lực giải mã bão hòa, `EFFICIENCY` bị nghẽn hàng đợi, trong khi `THROUGHPUT` giải phóng hàng đợi nhanh hơn.
2. **Bộ điều khiển ADAPTIVE**:
   - Bám theo đường bao trên (upper hull) của hai chế độ trong mô phỏng hàng đợi.
3. **Ranh giới nghiệm thu:**
   - Kết quả trên là mô phỏng hàng đợi trên host từ các tham số đo rời rạc; chưa chứng minh secret-key throughput hoặc crossover đo trực tiếp trên kit.
   - Nghiệm thu board yêu cầu truyền luồng arrival thật qua DMA/UART với scheduler hardware và đo lường trực tiếp.
