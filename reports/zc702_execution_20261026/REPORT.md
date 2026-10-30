# Kết quả đợt triển khai ZC702 ngày 26–27/10/2026

Đã triển khai và kiểm thử phần hậu xử lý cổ điển DV-QKD trên ZC702 thật: IR trong PL, điều khiển/buffer/finite-key trên PS và PA Hankel trong PL. Alice, nguồn BB84/decoy và seed phục vụ kiểm thử vẫn là mô phỏng. Clock board giữ 50 MHz; không tổng hợp lại RTL trong đợt này.

| Hạng mục | Kết quả đã kiểm chứng | Bằng chứng |
|---|---|---|
| P1: khóa đã verify + decoy cùng block → finite-key → PA | 439 block, 1.213.835 bit đầu vào → 104.768 bit đầu ra qua 103 pass, toàn bộ word khớp NTT tham chiếu | [EMIT](../zc702_key_stream_20261026T153858Z/REPORT.md) |
| Split và ABORT | Sau EMIT giữ đúng 19.355 bit tail; thêm dữ liệu xấu dẫn đến ABORT ở 201.845 bit; kiểm tra tail và CRC các buffer đã xóa | [Split/ABORT](../zc702_key_stream_20261026T153016Z/REPORT.md) |
| Scheduler K=1/2/4 | 36 phép đo DDR replay, ba lần mỗi điều kiện; K=4 nhanh hơn K=1 khoảng 3,59× ở trễ reveal 1 ms và 3,74× ở 10 ms | [Số đo và đồ thị](../zc702_latency_20261026T155148Z/REPORT.md) |
| FER tại một điểm | 10.000 input BSC độc lập, q=3%, r23/NMS+GS: 9.998 sửa đúng, 2 discard, 0 wrong codeword; 0 hardware mismatch | [FER](../zc702_fer_20261026T160934Z/REPORT.md) |
| Ablation ghép cặp trên mô hình | 1.000 input × 3 cấu hình; mean attempts 1,809 → 1,222 → 1,156; chưa phải số đo board | [Thống kê](../model_ablation_20261026T162423Z/STATISTICAL_CHECK.md) |
| STA trên route đang dùng | WNS tại 50/55/60/70 MHz: +2,645 / +0,827 / −0,688 / −3,069 ns | [Phạm vi phép thử](../ZC702_STA_FREQUENCY_TRIAL.md) |

FER quan sát là 0,02%; Wilson hai phía 95% [0,005485%; 0,072900%]. Cận trên thấp hơn 0,1% tại riêng điểm q=3%/r23/NMS+GS. Không suy ra FER cho QBER/code/profile khác. Phép đo FER không chạy tag hoặc PA; không gọi wrong codeword là lỗi đã bị tag bắt.

Benchmark K/RTT bao gồm DMA và kiểm tra correctness trong vòng đo, loại UART và PA. Bốn vector được lặp lại để đo scheduler; 1.152 lượt đánh giá đó không phải mẫu FER độc lập. Trễ được chèn sau khi PS phát hiện FAIL, chưa phải RTT mạng vật lý. Mô hình được đóng băng trước validation; sai số khoảng 18% ở zero-delay đa context vẫn cần giải thích bằng overlap load/decode.

Đầu ra PA ở đây là kết quả chức năng khớp tham chiếu. Seed công khai NumPy PCG64, thời gian nguồn replay ảo, chưa có nguồn quang/TRNG vật lý hay chứng minh kênh cổ điển được xác thực. Chọn block thích nghi, split và ngân sách composable ε còn cần rà soát độc lập. Không dùng số bit đầu ra này làm chứng nhận khóa bí mật an toàn.

Firmware mới nhận dữ liệu UART, giữ khóa/counts cùng block, kiểm tra tag trước append, stream seed và PA nhiều pass. Lượt âm tag sai không được đưa vào buffer của hai run P1 chính thức. Lượt thử EMIT ban đầu `20261026T152300Z` vẫn giữ để truy vết nhưng có transcript âm dùng lại, không dùng cho claim bảo mật.

Các log TX/RX, packet CRC/SHA, seed và reference đã giữ để replay. Kiểm chứng độc lập đối chiếu source/counts, toàn bộ word PA, tail/wipe; FER kiểm chứng 2.500 batch receipt với 10.000 input, packet và kết quả phần cứng. [Receipt hoàn tất](../FER_LATEST_COMPLETE.json), [ma trận claim/bằng chứng](../zc702_claim_evidence.csv).

Các việc tiếp theo, theo thứ tự:

1. Cưỡng chế ngân sách verification toàn phiên, fault recovery và gate seed/protocol; rà soát giả định finite-key/adaptive selection. Command đọc khóa debug phải bỏ/khóa trong sản phẩm.
2. Ablation có ghép cặp trên board; mở rộng FER theo từng QBER/code sau pilot. Chưa chạy toàn bộ ma trận kế hoạch.
3. Đo các pha UART/IR/chờ Alice/verify/PA và arrival/backlog; kiểm chứng điểm giao hai profile bằng mô hình dự đoán trước.
4. Cải thiện mô hình scheduling bằng training mới, rồi validation độc lập. K=1/K=4 trên cùng bitstream chưa chứng minh tiết kiệm BRAM so với hai kiến trúc build riêng.
5. Tách nhánh nghiên cứu code/rate mới, tối ưu PnR và PA NTT phần cứng. STA đổi constraint không phải Fmax board; 70 MHz hiện chưa đạt. [Feasibility rate](../RATE_095_FEASIBILITY.md).

[Kế hoạch nghiệm thu](../../KE_HOACH_HOAN_THANH_MUC_TIEU_ZC702.md), [35 đầu việc](../zc702_work_items.csv), [nhật ký](../EXECUTION_TRACKER.md), [thiết kế thí nghiệm công bố](../publication_plan_20261026/EXPERIMENT_PLAN.md). Bộ 46 điều kiện vẫn ghi dự kiến vì khác workload/định nghĩa với các phép đo DDR và FER một điểm vừa thực hiện.

Chiến dịch nền đã hoàn tất, không còn runner giữ COM3. Giữ giới hạn máy 8 GB: một Vivado nặng tại một thời điểm, tối đa hai luồng; các job UART chạy tuần tự.
