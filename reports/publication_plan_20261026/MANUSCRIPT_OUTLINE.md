# Dàn ý bài hệ thống: phạm vi đã đo và các khoảng trống

## Tiêu đề làm việc

**Finite-Key-Aware IR and Privacy Amplification on Zynq-7020: A Hardware-in-the-Loop Study**

Hoặc: **Latency-Tolerant FPGA Post-Processing for Simulated Decoy-State BB84**.

Không dùng “provably secure real-world QKD” hoặc “real-time optical system” khi Alice/decoy vẫn là mô phỏng và chưa hoàn tất phân tích giao thức.

## Đóng góp có thể trình bày sau đối chiếu literature

1. Tích hợp PS/PL cho IR QC-LDPC, verification và PA, gồm quản lý context, DMA và buffer; nguồn lượng tử được mô phỏng trên PC. Đây là đóng góp triển khai, chưa mặc định là kiến trúc mới so với mọi công bố.
2. Đánh giá thực nghiệm tác động trễ reveal tới K=1/2/4 trên cùng thiết bị 50 MHz. K=4 đạt khoảng 3,59× và 3,74× so K=1 ở trễ thêm 1/10 ms trên workload DDR lặp lại đã công bố.
3. Luồng buffer khóa đã xác minh gắn đúng NK/NT/MT, quyết định finite-key và PA nhiều pass; kiểm tra EMIT, split-tail và ABORT bằng số đo/log board. Đầu ra là kết quả theo mô hình, không phải chứng nhận khóa bí mật thực.
4. Bộ dữ liệu thực nghiệm có nguồn/hash, paired ablation mô hình, model dự đoán đóng băng trước điều kiện kiểm chứng và FER fixed-sample theo từng stratum. Chỉ điền kết quả 10.000 trial sau khi post-verifier hoàn tất.

## Cấu trúc đề xuất

### 1. Introduction

Đặt bài toán hậu xử lý khi thời gian trao đổi cổ điển và finite-key ảnh hưởng đầu ra. Đặt câu hỏi nghiên cứu có thể kiểm chứng: K context có che được thời gian chờ trong cấu hình đã đo không; mô hình có dự đoán được K/RTT chưa dùng hiệu chỉnh không; buffer/gom có thực thi đúng quyết định và bit đầu ra không.

Không dùng Fmax hoặc f để tuyên bố vượt công bố khác. Không dùng 470 kbit MODERATE hay 43,4 Mbit/s từ mô hình như số đo ZC702.

### 2. Scope, threat model and assumptions

Phân biệt mô phỏng Alice/quang/decoy, phần cứng ZC702, nguồn seed fixture, verification và kênh xác thực chưa có. Nêu rõ PE X-basis của stream mới; các giới hạn CSV cũ và adaptive block selection. Liệt kê giả định cần để áp dụng cận finite-key và tag, thay vì xem việc gọi hàm công thức là chứng minh bảo mật.

### 3. Architecture and implementation

PS7/DDR/AXI GP0/HP0, bốn DMA Simple, IR 128 lane và bốn mother code, APP/C2V/SGN dùng chung, bank CH/SYN. Mô tả receive ownership qua sticky SUCCESS trước rearm; không cho rằng TUSER được lưu trong DDR. Mô tả verification→buffer→finite-key→multi-pass Hankel; NTT trên PC chỉ là oracle exact, không phải accelerator mới trong PL.

### 4. Models and policies

- Closed queue/service/RTT và các giả định tài nguyên dùng chung; phân biệt công thức lý tưởng với model finite workload đã chạy.
- f/attempts theo code/QBER/r0/Δ: dữ liệu ghép cặp, tập hiệu chỉnh và kiểm chứng riêng, f có/không gồm tag.
- ℓ(N), WAIT/EMIT/ABORT/split: nguồn thống kê cùng block; thời gian replay ảo khác thời gian đo.
- ε correctness toàn phiên: số lần tag, phân bổ ε và điều kiện universal hashing; không dùng bound khi seed fixture không thỏa giả định.

### 5. Experimental methodology

Môi trường Vivado/Vitis 2020.2, PL 50 MHz, nguồn/hash, fixed-point/ET/PP/GS, protocol version, seed và các cổng. Thống kê workload độc lập/có tương quan/lặp lại. Tách timer đo trên ARM, counter PL, UART, chờ Alice và tính Python. Khai báo trước FER event/mẫu số và quy tắc xử lý lỗi.

### 6. Results

1. Correctness và các ca âm, gồm hash exact, thiếu seed, wrong tag, tail và wipe check.
2. Timing/resource hiện có; thêm actual Fmax nếu có implementation và board test mới. Bảng STA thay constraint không phải số đo Fmax.
3. K/RTT: median/min/max ba lần, speedup và sai số model; công khai điểm sai số khoảng 18% tại RTT0 do model service trung bình chưa mô tả overlap đầy đủ.
4. Paired ablation: 1.000 input, ba cấu hình trong mô hình; chưa gọi là full board ablation. f so thêm trên cùng tập success để tránh đổi mẫu số.
5. FER phần cứng: chờ đủ fixed sample và post-verification; từng QBER/code có CI riêng. Không gộp vector lặp của benchmark vào mẫu độc lập.
6. Coupled finite-key buffer: emission, split và abort ở các phiên nguồn mô phỏng; không tự suy độ an toàn của output.

### 7. Related work and limitations

Đối chiếu nguồn sơ cấp theo cùng n/rate/QBER/quantization/retries/RTT/clock và IR-only hay full post-processing. Đánh giá novelty sau literature search, không dựa vào bảng A/B/C/D thiếu bibliographic details. Nêu giới hạn nguồn quang mô phỏng, seed công khai, chưa DMA IRQ fully event-driven, chưa resource ablation K=1 vs4 compiled builds, chưa PA NTT trong PL.

### 8. Conclusion

Kết luận đúng phạm vi đã đo, không mở rộng sang an toàn hệ quang thực. Hướng tiếp: protocol/security review, board ablation/profile crossover, throughput với arrival queue thật, code/rate mới sau feasibility và PA lớn.

## Hình và bảng

| Artifact | Trạng thái |
|---|---|
| Sơ đồ PS/PL/Alice-sim và đường dữ liệu | Có backbone; cần hình minh họa chuẩn hóa, phân biệt mô phỏng/board |
| K/RTT speedup và throughput | Đã có PNG/SVG trong `reports/zc702_latency_20261026T155148Z/` |
| Timing lanes từng context | Chưa có event trace đủ chi tiết; không vẽ từ total time rồi gọi là trace đo |
| Predicted vs measured và residual | Có CSV model-error; nên thêm hình và thử workload held-out mới |
| Paired attempts/f/FER ablation | Có 1.000 paired model inputs; thiếu cùng ablation trên board |
| ℓ(N), first-EMIT, split-tail | Có coupled runs; cần phân biệt candidate ℓ của model với API ell_out=0 khi WAIT |
| FER vs QBER và CI | Mới pilot, một chiến dịch 10.000 đang chạy; chưa có sweep nhiều QBER |
| Resource/timing/clock table | 50 MHz đã đo; 70 MHz không đạt trên constraint trial của route cũ |
| Literature comparison normalized | Chưa đủ primary references/điều kiện tương đương |

Ứng viên venue do người dùng đề xuất: IEEE Access, Entropy, hội nghị FPGA/quantum communication; TCAS-I/TVLSI là hướng tham vọng nếu có thêm kết quả. Cần kiểm tra scope, phí, chính sách và công bố gần đây trước chọn; không dự báo chấp nhận chỉ từ prototype PASS.
