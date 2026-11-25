# Kế hoạch thực nghiệm tiếp theo và gate nghiệm thu

Nguồn chuẩn: [35 đầu việc](../zc702_work_items.csv), [ma trận 46 strata dự kiến](../publication_experiment_matrix.csv), [claim/evidence](../zc702_claim_evidence.csv). Các con số strata là kế hoạch, không phải kết quả đã chạy.

## P1 – coupled stream

Đã có EMIT không-split và split→ABORT với nguồn simulated decoy, buffer thật, exact NTT đối chiếu. Còn rà soát transcript/leakage/selection/ε, thêm fault cases và phân tích tối đa buffer/timeout. Không coi seed fixture hay dữ liệu mô phỏng là chứng minh an toàn quang thực.

## Timing và lập lịch

Đã bổ sung [profiler 36 ca K=1 và PA nhiều pass](../zc702_profiling_20261027/REPORT.md), có PMU/global timer, span DMA/IR/verification/PA/UART và đối chiếu source raw. PA lớn 103 pass đo khoảng 342,3 ms trong các call, chưa gồm seed UART hay IR/accumulation. Đây là dữ liệu latency có scope, không thay production throughput. Mỗi code dùng fixture khác nhau; không dùng hình timing này làm rate ablation.

Đã có 36 phép đo DDR IR ở K=1/2/4, reveal-delay 0/0,1/1/10 ms, 32 job/phép đo và ba lần lặp. Chưa có UART-network RTT thực, arrival queue/crossover hay full secret-key throughput. Bước tiếp là đo riêng DMA/load/decode/reveal/verify/PA, model nhiều tài nguyên và kiểm chứng workload mới. Chỉ hiệu chỉnh trên training, đóng băng model trước held-out.

Muốn chứng minh bộ nhớ “không tăng BRAM”, phải so build thực K=1 và K=4 hoặc baseline nhiều decoder phù hợp; chỉ tắt context trên cùng bitstream bốn bank không đủ chứng minh.

## FER và ablation

Pilot 256 trial độc lập đã được kiểm tra. Campaign 10.000 q=3%/r23/NMS+GS đã hoàn tất và raw verifier PASS: 9.998 success, 2 discard, 0 wrong codeword; FER=0,0002, Wilson hai phía 95% [0,00005485; 0,00072900]. [Báo cáo](../zc702_fer_20261026T160934Z/REPORT.md). Tiếp theo mở các strata QBER/code đã chọn trước, không thay tham số giữa trial để đạt mục tiêu FER. Kết quả tại một điểm không thay cho ma trận profile/QBER dự kiến.

Mỗi stratum phải báo: n độc lập, discard, sai codeword theo ground truth, verification reject nếu thực sự chạy tag, lỗi transport và lỗi hardware. CIs pointwise không tự thành coverage đồng thời toàn sweep. Nếu điều chỉnh sample size theo kết quả phải dùng phương pháp tuần tự phù hợp; hiện campaign đã chốt n=10.000, không dừng sớm khi CI thuận lợi.

Ablation mô hình đã chạy 1.000 input ghép cặp cho OMS/random, OMS/GS, NMS/GS. Chưa có ba-way board ablation hoặc các tầng dynamic/switching/multicontext được kiểm soát trên cùng dữ liệu. Mean f trên tập success khác nhau dễ gây selection bias; báo thêm tương phản trên cùng tập success. Không suy giảm FER có ý nghĩa từ vài sự kiện fail.

## Finite-key/policy model

Từ cùng nguồn mô phỏng phải dự đoán ℓ(N), first-EMIT và quyết định split/abort trước phép kiểm chứng. Phân biệt API `ell_out` (0 khi WAIT) với candidate finite-key length của model. Thời gian replay ảo, thời gian quang mô phỏng và wall time board là ba đại lượng khác nhau.

Rà soát việc IR chọn bỏ block phụ thuộc lỗi và cường độ ảnh hưởng các giả định decoy; không chỉ so hai bản hàm cùng công thức rồi gọi là chứng minh. Nguồn tham khảo chính: [Lim et al.](https://arxiv.org/abs/1311.7129).

## Các hướng kiến trúc

Rate 0,95/0,40 phải qua [feasibility](../RATE_095_FEASIBILITY.md), matrix/rank/degree/delta và ABI trước ROM/RTL. Code dài hơn giữ 128 lane vẫn cần mở NCOL, RAM/ROM/địa chỉ và buffer. PA NTT/MMH-MH trong PL là dự án riêng; NTT PC hiện chỉ là oracle kiểm tra. TRNG vật lý cần nguồn và đánh giá thích hợp, không suy entropy từ health-test/MMIO PASS.

70 MHz cần implementation riêng và regression nếu muốn tuyên bố hoạt động ở clock đó. Route cũ có WNS −3,069 ns khi áp constraint 70 MHz; hệ thống đã chạy vẫn 50 MHz. Không nới constraints hoặc quy đổi thông lượng tuyến tính để thay số đo.

Tài nguyên thực thi: một board/COM3, một tác vụ board mỗi lần, tối đa hai thread cho Vivado, các model worker chạy tuần tự theo process. Không chạy tool mặc định tạo worker theo toàn bộ CPU trên máy 8 GB. Kiểm tra RUNNING_JOBS trước mọi lệnh nạp board.
