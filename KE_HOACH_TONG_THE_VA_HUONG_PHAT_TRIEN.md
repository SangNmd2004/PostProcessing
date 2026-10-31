> Khôi phục ngày 31/10/2026 từ kế hoạch gốc. Các giai đoạn và tiêu chí dưới đây là roadmap; trạng thái thực tế đọc tại [35 đầu việc](reports/zc702_work_items.csv) và [tiến độ dự án](reports/TIEN_DO_TOAN_BO_DU_AN.md).

# Kế Hoạch Tổng Thể: Tích Hợp Hệ Thống, Đo Đạc & Xuất Bản Bài Báo

Kế hoạch này tích hợp toàn diện:
1. Lộ trình nghiệm thu chức năng trên ZC702 từ [KE_HOACH_HOAN_THANH_MUC_TIEU_ZC702.md](KE_HOACH_HOAN_THANH_MUC_TIEU_ZC702.md).
2. 8 hướng phát triển kiến trúc trong Mục 10 của tài liệu gốc [Lõi IR Blind Reconciliation (Copy).md](<Lõi IR Blind Reconciliation (Copy).md>).
3. Các tiêu chuẩn khoa học và mô hình toán bắt buộc để hoàn thiện một bài báo quốc tế chất lượng (IEEE Access, Entropy hoặc Hội nghị QKD/FPGA).

---

## 1. Cơ Cấu 4 Giai Đoạn Triển Khai (Phased Roadmap)

```
Giai Đoạn 1: Khép Kín Chuỗi Pipeline Thực Tế (End-to-End Finite-Key Buffer)
 [P1] Ghép buffer khóa đã xác minh với decoy stats ---> [P02] Loại bỏ mẫu PE ---> Xuất ell bit bí mật
                                                               |
Giai Đoạn 2: Đo Đạc Timeline, Kiểm Chứng Mô Hình & Chiến Dịch Thống Kê
 [P06/PUB05] Đo timeline phần cứng & quét RTT ---------> [PUB01] Kiểm chứng mô hình hàng đợi S(K)
 [PUB07/P08] Chiến dịch FER 10^4 khối & 95% CI --------> [PUB02] Kiểm chứng điểm giao thoa Profile
 [PUB06] Nghiên cứu Ablation có kiểm soát ------------> [PUB04] Báo cáo ngân sách eps_cor
                                                               |
Giai Đoạn 3: Cải Tiến Kiến Trúc Nâng Cao (High-Impact Features)
 [R02] Mã LDPC rate cao ~0.95 cho QBER < 1% -----------> [P03] Tích hợp nguồn TRNG vật lý trên kit
 [P05] Tối ưu đường găng & thử timing 70 MHz ----------> [R04] Thiết kế PA lớn qua NTT (Dài hạn)
                                                               |
Giai Đoạn 4: Viết Bản Thảo & Công Bố Khoa Học (Publication & Submission)
 [PUB08] Hoàn thiện bản thảo bài báo -----------------> Đối chiếu Ma Trận Bằng Chứng ---> Nộp bài
```

---

## 2. Chi Tiết Từng Giai Đoạn & Tiêu Chí Nghiệm Thu

### Giai Đoạn 1: Khép Kín Chuỗi Pipeline Trên Bộ Đệm Khóa Thực
*Trọng tâm: Đưa hệ thống từ trạng thái "kiểm thử khối rời rạc" sang "hệ thống hoàn chỉnh đầu-cuối".*

- **Hạng mục P1 (Ưu tiên số 1):**
  - Ghép trực tiếp vùng nhớ DDR chứa khóa đã qua giải mã LDPC và xác minh tag với bộ gom Decoy Finite-Key trên ARM.
  - Khi bộ gom ra quyết định `EMIT`, kích hoạt lõi PA băm đa lượt và **cắt đúng $\ell$ bit bí mật** theo công thức Lim (2014).
  - Khi ra quyết định `ABORT`, xóa trắng toàn bộ dữ liệu trong bộ đệm (zeroize).
  - Khi ra quyết định `EMIT, split`, phát tại điểm tối ưu và giữ lại phần đuôi chưa bão hòa cho phiên sau.
- **Hạng mục P02:**
  - Khấu trừ chính xác 256 bit mẫu dùng ước lượng lỗi (PE) khỏi bộ đệm trước khi băm PA, hoặc tính toán đầy đủ lượng rò rỉ này vào số hạng $\text{leak}_{EC}$.
- **Hạng mục P04:**
  - Định dạng gói tin giao tiếp cổ điển giữa Alice và Bob có thêm trường kiểm tra tính xác thực (Wegman-Carter MAC) và chống tấn công phát lại (Replay protection).
- **Tiêu chí hoàn thành Giai đoạn 1:**
  - Một phiên chạy sinh ra luồng khóa bí mật có độ dài $\ell$ bit chính xác, có biên bản kiểm tra rò rỉ và đối chiếu bit-exact với mô hình toán Python.

### Giai Đoạn 2: Đo Đạc Timeline, Kiểm Chứng Mô Hình & Chiến Dịch Thống Kê
*Trọng tâm: Cung cấp đầy đủ số liệu đo đạc thực nghiệm thay thế cho các số liệu ngoại suy lý thuyết.*

- **Hạng mục P06 / PUB05 (Đo đạc timeline phần cứng):**
  - Dùng bộ đếm chu kỳ ARM PMU để phân rã chi tiết thời gian: $T_{\text{DMA}}$, $T_{\text{IR}}$ (compute thuần trong PL), $T_{\text{RTT}}$ (chờ Alice), $T_{\text{verify}}$, $T_{\text{PA}}$, $T_{\text{UART}}$.
  - Quét thực tế trên kit ở các mức RTT: $0{,}1\text{ ms}, 0{,}5\text{ ms}, 1\text{ ms}, 5\text{ ms}, 10\text{ ms}$.
- **Hạng mục PUB01 (Kiểm chứng mô hình hàng đợi):**
  - Đối chiếu số đo thực nghiệm của 1 và 4 ngữ cảnh với mô hình lý thuyết:
    $$S(K) \approx \min\left(K, 1 + \frac{\text{RTT}}{T_{\text{dec}}}\right)$$
  - Xác định chính xác vùng bão hòa khi $K=4$.
- **Hạng mục PUB02 (Kiểm chứng điểm giao thoa Profile):**
  - Đo thông lượng khóa bí mật thực tế tại các tốc độ khóa thô đầu vào khác nhau (từ 1 đến 40 Mbit/s).
  - Xác nhận điểm giao thoa lý thuyết nơi chế độ `THROUGHPUT` vượt qua `EFFICIENCY` (bão hòa $8{,}67$ vs $5{,}81\text{ Mbit/s}$).
- **Hạng mục P08 / PUB07 (Chiến dịch FER $\ge 10^4$ khối):**
  - Thu thập tối thiểu $10^4$ khối độc lập cho mỗi điểm QBER.
  - Phân loại rõ ràng: khối bị hủy do decoder, khối sai codeword bị tag bắt, lỗi phần cứng.
  - Tính toán khoảng tin cậy 95% (Wilson score / Rule-of-Three) để chứng minh đạt mức $\text{FER} \sim 10^{-3}$.
- **Hạng mục PUB06 (Ablation Study):**
  - Thực hiện bảng đối chiếu đầy đủ từng bước tối ưu trên cùng tập dữ liệu: Baseline $\to$ +GS $\to$ +NMS $\to$ +Dynamic $\to$ +Profile $\to$ +4-Context.
- **Hạng mục PUB04 (Ngân sách an toàn $\varepsilon_{cor}$):**
  - Tính toán cận union bound: $\varepsilon_{cor} \le N \cdot 2^{-64}$.
  - Xác nhận với $\varepsilon_{cor} = 10^{-15}$, số khối tối đa trong một phiên là $N_{\max} \approx 18.446$ khối ($\approx 50\text{ Mbit}$ khóa thô), vừa đủ an toàn cho khối tích lũy 16 Mbit ($\approx 5.786$ khối).

### Giai Đoạn 3: Cải Tiến Kiến Trúc Nâng Cao
*Trọng tâm: Nâng cao chất lượng kỹ thuật và tạo điểm khác biệt vượt trội so với các bài báo khác.*

- **Hạng mục R02 (Mã LDPC rate cao $\sim 0{,}95$):**
  - Thiết kế ma trận cơ sở $24 \times 4$ ($m=256$ bit syndrome) để cứu vùng QBER thấp ($< 1\%$).
  - Hạ $f$ từ $\ge 1{,}90$ xuống $\le 1{,}30$.
  - Mở rộng trường chọn mã thanh ghi CFG từ 2 bit lên 3 bit và cập nhật bảng GS.
- **Hạng mục P03 (Nguồn TRNG trên chip):**
  - Tích hợp lõi Ring Oscillator hoặc Metastability TRNG vào PL ZC702 để cấp seed cho lõi băm PA.
  - Tích hợp bộ kiểm tra sức khỏe trực tuyến (Repetition Count & Adaptive Proportion Tests) theo chuẩn NIST SP 800-90B.
- **Hạng mục P05 (Timing 70 MHz trên Zynq):**
  - Phân tích đường găng sau route trong Vivado.
  - Chèn thanh ghi pipeline tại các giao tiếp AXI nếu cần để đạt timing closure 70 MHz trên XC7Z020.
  - Lưu ý: Nếu hệ thống chỉ ổn định ở 50–60 MHz, bài báo vẫn bảo vệ vững chắc vì thông lượng tăng tuyến tính theo xung nhịp.
- **Hạng mục R04 (PA khối lớn qua NTT - Hướng dài hạn):**
  - Nghiên cứu kiến trúc băm Toeplitz dựa trên phép nhân đa thức NTT trong bộ nhớ DDR3 cho khối khóa lớn ($10^7 - 10^8$ bit).

### Giai Đoạn 4: Viết Bản Thảo & Công Bố Khoa Học
*Trọng tâm: Đóng gói bài báo hoàn chỉnh, đúng chuẩn format và gửi tới tạp chí phù hợp.*

- **Lựa chọn tạp chí / hội nghị mục tiêu:**
  - *Mục tiêu 1 (Khả thi cao):* **IEEE Access**, **Entropy (MDPI)** hoặc **QCrypt / FPGA Conference**. (Yêu cầu: Hoàn thành đủ Giai đoạn 1 & 2).
  - *Mục tiêu 2 (Tham vọng cao):* **IEEE Transactions on VLSI Systems (TVLSI)** hoặc **IEEE TCAS-I**. (Yêu cầu: Hoàn thành thêm Giai đoạn 3 với mã rate 0.95 và TRNG vật lý).
- **Cấu trúc bản thảo dự kiến:**
  1. *Introduction:* Nút cổ chai trễ RTT và thách thức độ dài khóa hữu hạn trong DV-QKD thực tế.
  2. *System Architecture:* SoC ZC702 chi phí thấp, 4 ngữ cảnh dùng chung bộ nhớ, luồng DMA.
  3. *Mathematical Modeling:* Mô hình hàng đợi $S(K)$, điểm giao thoa profile và cận tích lũy $\varepsilon_{cor}$.
  4. *Implementation Details:* Bộ giải mã Layered NMS $\times 0{,}75$, đục lỗ GS, băm Hankel PA và bộ gom Decoy.
  5. *Experimental Results:* Bảng đo timeline thực tế, kiểm chứng mô hình toán, FER 95% CI và nghiên cứu Ablation.
  6. *Literature Comparison & Conclusion:* Đối chiếu với các công bố trên Virtex-7 và ZCU102.

---

## 3. Ma Trận Theo Dõi Tiến Độ & Bảng Giao Việc

Toàn bộ 35 đầu việc chuẩn hóa được ánh xạ chi tiết tại:
- File CSV: [plans/WORK_ITEMS.csv](reports/zc702_work_items.csv)
- Ma trận bằng chứng: [plans/CLAIM_EVIDENCE_MATRIX.csv](reports/zc702_claim_evidence.csv)

Mỗi đầu việc phải tuân thủ nghiêm ngặt quy trình:  
$$\text{Thiết kế} \to \text{Thực thi Code} \to \text{Đo trên Board} \to \text{Lưu Receipt \& Log} \to \text{Cập nhật Ma Trận}$$
Tuyệt đối không đánh dấu PASS nếu chỉ mới chạy mô phỏng phần mềm hoặc dự đoán lý thuyết.
