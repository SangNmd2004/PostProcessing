> Khôi phục ngày 31/10/2026 từ kế hoạch thí nghiệm gốc. Bốn mô hình bên dưới là đề xuất cần kiểm chứng theo giả định riêng. Xem [suy diễn resource/scheduling](reports/publication_plan_20261026/RESOURCE_MODEL_DERIVATION.md), [đặc tả crossover](reports/publication_plan_20261026/CROSSOVER_MODEL_SPEC.md) và [kế hoạch nghiệm thu](reports/publication_plan_20261026/EXPERIMENT_PLAN.md) để đối chiếu phần đã triển khai.

# Kế Hoạch Thiết Kế Thí Nghiệm & Mô Hình Toán Cho Bài Báo Khoa Học

Tài liệu này chi tiết hóa toàn bộ chiến lược công bố khoa học, bao gồm: tiêu đề bài báo, 3 trụ cột đóng góp, 4 mô hình toán học bắt buộc có, thiết kế thí nghiệm đối chiếu trên kit ZC702, kế hoạch thống kê FER và danh mục hình ảnh/bảng biểu dự kiến cho bản thảo.

---

## 1. Tiêu Đề Bài Báo & Tạp Chí Mục Tiêu

### Tiêu Đề Dự Kiến (Working Title)
> **"A Low-Cost, Latency-Hiding, and Finite-Key Aware Post-Processing SoC Architecture for Discrete-Variable Quantum Key Distribution"**  
> *(Kiến trúc SoC chi phí thấp, che độ trễ và nhận biết độ dài khóa hữu hạn cho khâu hậu xử lý DV-QKD)*

### Lựa Chọn Tạp Chí / Hội Nghị Mục Tiêu
1. **Nhóm Mục Tiêu Thực Tế (Hoàn thành Giai đoạn 1 & 2):**
   - **IEEE Access** (Impact Factor ~3.4, Open Access, chu kỳ bình duyệt nhanh 4–6 tuần, phù hợp bài kiến trúc hệ thống thực nghiệm).
   - **Entropy (MDPI)** (Special Issue on Quantum Information & Cryptography).
   - **Hội nghị Quốc Tế:** QCrypt (Annual Conference on Quantum Cryptography), IEEE FPT (Field Programmable Technology), hoặc IEEE ISCAS.
2. **Nhóm Mục Tiêu Nâng Cao (Khi hoàn thành thêm Giai đoạn 3 với mã rate 0.95 và TRNG vật lý):**
   - **IEEE Transactions on Very Large Scale Integration (VLSI) Systems (TVLSI)**.
   - **IEEE Transactions on Circuits and Systems I: Regular Papers (TCAS-I)**.

---

## 2. Ba Trụ Cột Đóng Góp Khoa Học (Core Contributions)

Tránh tuyệt đối việc lấy hiệu suất rò rỉ $f$ hoặc xung nhịp $F_{max}$ làm luận điểm cạnh tranh vì $f=1{,}2-1{,}9$ và $50-70\text{ MHz}$ không phải là thế mạnh so với các thiết kế trên FPGA UltraScale+ đắt tiền. Thay vào đó, bài báo tập trung vào 3 đóng góp kiến trúc hệ thống thực tế:

```
                  +-------------------------------------------------------------+
                  | Luận điểm: Hậu xử lý DV-QKD che RTT & nhận thức Finite-Key |
                  +------------------------------+------------------------------+
                                                 |
         +---------------------------------------+---------------------------------------+
         |                                       |                                       |
+--------v----------------------+  +-------------v-----------------+  +------------------v--------------------+
| Trụ Cột 1: Đa Ngữ Cảnh        |  | Trụ Cột 2: Điều Khiển 2 Chế Độ|  | Trụ Cột 3: Tích Lũy Finite-Key        |
| - 4 Contexts xen kẽ           |  | - EFFICIENCY vs THROUGHPUT    |  | - Thuật toán Lim (2014)               |
| - Dùng chung APP/C2V/SGN      |  | - Hysteresis tự chuyển        |  | - WAIT / EMIT / ABORT / split         |
| - Không tăng BSRAM            |  | - Khóa bão hòa 8.67 Mbit/s    |  | - Đưa khóa 0 -> 470 kbit ở MODERATE   |
| - Tăng tốc x3.48 che trễ RTT  |  | - Điểm giao thoa dự đoán được |  | - Nhận thức biến động kênh thực tế    |
+-------------------------------+  +-------------------------------+  +---------------------------------------+
```

1. **Trụ Cột 1 - Bộ giải mã đa ngữ cảnh chia sẻ bộ nhớ (Memory-Shared Multi-Context):**
   - Trong DV-QKD, việc hỏi–đáp thông tin công bố qua kênh cổ điển Alice–Bob tạo ra độ trễ Round-Trip Time (RTT từ $100\text{ }\mu\text{s}$ đến vài phần nghìn giây), khiến phần cứng giải mã thường xuyên bị nhàn rỗi (idle).
   - Kiến trúc đề xuất giữ 4 khối ngữ cảnh thường trú (`CTX_W = 2`), dùng chung toàn bộ các mảng nhớ tính toán lớn APP, C2V, SGN; chỉ nhân bản độ sâu bộ đệm CH và SYN RAM.
   - Kết quả: Che hoàn toàn thời gian trễ RTT, tăng tốc thông lượng $\times 3{,}48$ mà **không tiêu tốn thêm bất kỳ khối Block RAM (BSRAM) nào**.
2. **Trụ Cột 2 - Bộ điều khiển thích ứng Backlog hai chế độ (Backlog-Adaptive Dual-Mode Controller):**
   - Đa số các công trình trước đây chỉ cố định một chiến lược giải mã.
   - Hệ thống tích hợp hai chế độ hoạt động: `EFFICIENCY` (ưu tiên rò rỉ thấp, $f=1{,}50$) khi tải thấp và `THROUGHPUT` (công bố trước $r_0$ bit để hội tụ ngay sau 1 lần thử, đạt thông lượng bão hòa $8{,}67\text{ Mbit/s}$ so với $5{,}81\text{ Mbit/s}$ của EFFICIENCY) khi tải cao.
   - Cơ chế trễ (hysteresis) tự động chuyển đổi dựa trên độ dài hàng đợi khối khóa thô, với điểm giao thoa thông lượng được dự đoán chính xác bằng mô hình toán.
3. **Trụ Cột 3 - Bộ gom khối Decoy nhận thức độ dài hữu hạn (Finite-Key Block Accumulator):**
   - Áp dụng cận hữu hạn Lim et al. (2014) kết hợp máy trạng thái tự động thích ứng với sự thay đổi của kênh truyền quang (`WAIT`, `EMIT`, `ABORT`, `split`).
   - Đột phá thực nghiệm: Trong kịch bản suy hao và nhiễu trung bình (`MODERATE`), đánh giá từng khối đơn lẻ đều cho độ dài khóa hữu hạn $\ell \le 0$ (buộc phải hủy bỏ toàn bộ), nhưng bộ gom tích lũy tự động đã trích xuất thành công **$470\text{ kbit}$** khóa bí mật an toàn.

---

## 3. Bốn Mô Hình Toán Học Bắt Buộc Có & Phương Pháp Kiểm Chứng

Mô hình chỉ có giá trị khoa học khi **dự đoán được trước** các chỉ số hệ thống, sau đó đối chiếu độ lệch với số đo thực tế trên kit ZC702 (không phải là làm khớp đường cong sau khi đo).

### Mô Hình 1: Mô Hình Hàng Đợi & Lập Lịch Đa Ngữ Cảnh (Queueing & Multi-Context Scheduling)
- **Đại lượng dự đoán:** Hệ số tăng tốc thông lượng $S(K)$ theo số lượng ngữ cảnh $K$, thời gian giải mã một lần thử $T_{\text{dec}}$, thời gian trễ vòng lặp kênh cổ điển $\text{RTT}$, và thời gian truyền DMA/UART $T_{\text{trans}}$.
- **Công thức giải tích ban đầu:**
  $$S(K) \approx \min\left(K, 1 + \frac{\text{RTT}}{T_{\text{dec}} + T_{\text{trans}}}\right)$$
- **Vùng bão hòa:** Dự đoán ngưỡng RTT tối thiểu để 4 ngữ cảnh đạt tới mức tăng tốc bão hòa lý thuyết ($\approx \times 3{,}5 - \times 4{,}0$).
- **Phương pháp kiểm chứng:** Đo đạc bằng bộ đếm chu kỳ ARM PMU trên kit ZC702 ở các mức RTT giả lập: $100\text{ }\mu\text{s}$, $500\text{ }\mu\text{s}$, $1\text{ ms}$, $5\text{ ms}$, $10\text{ ms}$ cho cả $K=1$ và $K=4$.

### Mô Hình 2: Mô Hình Hiệu Suất Rò Rỉ $f$ & Điểm Giao Thoa Profile
- **Đại lượng dự đoán:** Hiệu suất rò rỉ kỳ vọng $f(q)$ và số lần thử trung bình $E[A]$ theo mã được chọn, mức QBER $q$, số bit công bố trước $r_0$ và bước công bố $\Delta$.
  $$f = \frac{m - d + r_0 + \sum_{i=1}^{A-1} \Delta_i}{(n - d) \cdot h(q)}$$
- **Dự đoán điểm giao thoa:** Dự đoán chính xác tốc độ khóa thô đầu vào $R_{\text{raw}}^*$ mà tại đó chế độ `THROUGHPUT` bắt đầu cho lượng khóa bí mật thực tế cao hơn chế độ `EFFICIENCY` (theo số liệu sơ bộ là quanh mức $14 - 18\text{ Mbit/s}$).
- **Phương pháp kiểm chứng:** Chạy sweep tự động trên kit ZC702 với tối thiểu $10^3$ khối độc lập cho mỗi điểm QBER.

### Mô Hình 3: Mô Hình Tích Lũy Finite-Key & Thời Gian Đến EMIT Đầu Tiên
- **Đại lượng dự đoán:** Độ dài khóa bí mật hữu hạn $\ell(N)$ theo số khối tích lũy $N$, thời gian trung bình $T_{\text{emit}}$ để đạt quyết định `EMIT` đầu tiên, và điều kiện kích hoạt `ABORT` hoặc `split` theo tham số kênh Gamma-Gamma.
- **Phương pháp kiểm chứng:** Chạy các phiên dữ liệu mô phỏng vật lý đa dạng (`WEAK`, `MILD`, `MODERATE`), ghi nhận số lần split/abort và so sánh sai lệch giữa dự đoán giải tích với bộ đệm thực tế trên kit ZC702.

### Mô Hình 4: Phân Bổ Ngân Sách An Toàn & Cận $\varepsilon_{cor}$ Tích Lũy
- **Đại lượng dự đoán:** Xác suất lỗi xác minh tích lũy toàn phiên $\varepsilon_{cor}^{\text{accum}}$ cho thẻ tag băm Hankel 64-bit qua $N$ khối:
  $$\varepsilon_{cor}^{\text{accum}} \le N \cdot 2^{-64}$$
- **Phân tích ranh giới giới hạn:**
  - Nếu dành trọn ngân sách $\varepsilon_{cor} = 10^{-15}$ cho khâu tag xác minh:
    $$N_{\max} = 10^{-15} \cdot 2^{64} \approx 1{,}84 \times 10^4 \text{ khối}$$
  - Với kích thước khối $n = 3072$ bit (lấy 2765 bit khóa), $N_{\max}$ tương đương khoảng **$\approx 50{,}9\text{ Mbit}$ khóa thô**.
  - Đối với phiên gom khối lớn 16 Mbit ($\approx 5\,786$ khối), số lượng khối này nằm sát ngưỡng an toàn ($\approx 31{,}4\%$ ngân sách tối đa).
- **Ý nghĩa bài báo:** Đây là phân tích lý thuyết quan trọng mà rất ít bài báo FPGA thực hiện, chứng minh rằng việc chọn độ dài tag 64-bit là tối ưu cho các phiên thu thập dưới 50 Mbit.

---

## 4. Thiết Kế Các Chiến Dịch Thí Nghiệm Đo Đạc

### Thí Nghiệm 1: Phân Rã Độ Trễ Timeline Phần Cứng Bằng ARM PMU
- Gắn thanh ghi bộ đếm chu kỳ phần cứng Cortex-A9 (`ARM_PMU_CCNT`) vào driver bare-metal.
- Xuất bảng dữ liệu microsecond chi tiết cho từng khối:
  - $T_{\text{DMA\_in}}$ (Nạp LLR + Syndrome vào PL).
  - $T_{\text{IR\_compute}}$ (Thời gian giải mã QC-LDPC trong PL).
  - $T_{\text{Alice\_RTT}}$ (Thời gian chờ Alice qua mạng).
  - $T_{\text{Verify}}$ (Băm Hankel tag 64-bit).
  - $T_{\text{PA}}$ (Băm Hankel PA 1024-bit).
  - $T_{\text{DMA\_out}}$ (Truyền khóa ra DDR).
  - $T_{\text{UART}}$ (Overhead truyền nhận gói tin thử nghiệm).

### Thí Nghiệm 2: Nghiên Cứu Ablation Có Kiểm Soát (Bảng Bắt Buộc)
Giữ nguyên cùng một tập vector thử nghiệm và cùng seed ngẫu nhiên, đo đạc lần lượt 7 cấu hình:

| Cấu Hình | Mô Tả Kỹ Thuật | $f$ Trung Bình | Số Vòng Lặp TB | Số Lần Thử TB | Thông Lượng Khóa Sửa |
|---|---|---|---|---|---|
| **Ablation 0** | Baseline: Đục lỗ ngẫu nhiên, giải OMS, bước cố định $\Delta=16$, không ET | — | — | — | — |
| **Ablation 1** | + Grouping & Sorting (GS) cho 307 vị trí $D$ | — | — | — | — |
| **Ablation 2** | + Layered Normalized Min-Sum (NMS $\alpha = 0{,}75$) | — | — | — | — |
| **Ablation 3** | + Dừng sớm (Early Termination) & Post-Processing (PP) | — | — | — | — |
| **Ablation 4** | + Chế độ Dynamic: công bố trước $r_0$ bit và $\Delta$ thích ứng | — | — | — | — |
| **Ablation 5** | + Bộ điều khiển Hysteresis tự chuyển `EFFICIENCY` / `THROUGHPUT` | — | — | — | — |
| **Ablation 6** | + Kiến trúc 4 Ngữ Cảnh (Multi-Context RTT hiding) | — | — | — | — |

### Thí Nghiệm 3: Chiến Dịch Thống Kê FER $\ge 10^4$ Khối Độc Lập
- Tự động hóa bộ sinh $10^4$ khối ngẫu nhiên độc lập cho từng điểm QBER: $1\%$, $2\%$, $3\%$, $5\%$, $7\%$.
- Tính khoảng tin cậy 95% Wilson Score Interval cho tỷ lệ lỗi khung:
  $$p \in \frac{\hat{p} + \frac{z^2}{2n} \pm z\sqrt{\frac{\hat{p}(1-\hat{p})}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}} \quad (z = 1{,}96)$$
- Tách biệt rõ ràng các sự kiện:
  - Khối bị decoder hủy (Discard).
  - Khối hội tụ sai codeword nhưng bị tag 64-bit chặn lại (Caught by tag).
  - Khối sai codeword lọt qua tag (Undetected error - kỳ vọng bằng 0).

---

## 5. Danh Mục Hình Ảnh & Bảng Biểu Dự Kiến Cho Bản Thảo

### Danh Mục Hình Vẽ (Figures)
1. **Fig. 1:** Sơ đồ kiến trúc tổng quan hệ thống hậu xử lý DV-QKD trên SoC ZC702 (phân chia PS/PL, 4 Simple DMAs, DDR3).
2. **Fig. 2:** Cấu trúc chi tiết lõi giải mã QC-LDPC 4 ngữ cảnh với mảng nhớ APP/C2V/SGN dùng chung và cơ chế gối layer.
3. **Fig. 3:** Sơ đồ máy trạng thái bộ điều khiển Backlog Hysteresis và bộ gom Decoy Finite-Key (`WAIT`, `EMIT`, `ABORT`, `split`).
4. **Fig. 4:** Đồ thị tốc độ tăng tốc $S(K)$ lý thuyết so với số đo thực nghiệm trên board theo độ trễ RTT ($0{,}1 - 10\text{ ms}$).
5. **Fig. 5:** Đồ thị thông lượng khóa bí mật thực tế theo tốc độ khóa thô đầu vào, thể hiện rõ điểm giao thoa giữa EFFICIENCY và THROUGHPUT.
6. **Fig. 6:** Đường cong hội tụ tích lũy khóa bí mật hữu hạn $\ell(N)$ theo thời gian trong môi trường nhiễu loạn Gamma-Gamma.
7. **Fig. 7:** Biểu đồ thác lỗi (Waterfall curves) và phân bố số lần thử của 4 mother codes sau khi tối ưu GS và NMS.

### Danh Mục Bảng Biểu (Tables)
1. **Table I:** Tham số và đặc tính kiến trúc của 4 Mother Code QC-LDPC ($Z_c=128, n=3072$).
2. **Table II:** Phân rã thời gian thực thi (Latency Breakdown) đo bằng ARM PMU cycle counter cho từng giai đoạn.
3. **Table III:** Bảng kết quả nghiên cứu Ablation Study qua 7 tầng tối ưu hóa.
4. **Table IV:** Kết quả chiến dịch đo FER trên $\ge 10^4$ khối kèm khoảng tin cậy 95%.
5. **Table V:** Sử dụng tài nguyên trên chip Xilinx XC7Z020 (LUT, FF, BRAM, DSP) và so sánh với cấu hình 1 context.
6. **Table VI:** Bảng so sánh toàn diện với các công trình công bố quốc tế (Paper A, B, C, D).
