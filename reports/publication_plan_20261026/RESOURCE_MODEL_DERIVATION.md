# Mô hình lập lịch PS/DMA và decoder dùng chung

Mục đích là dự đoán thời gian DDR IR với K=1/2/4 và độ trễ REVEAL được chèn trước. Đây chưa phải mô hình thông lượng khóa bí mật hay phân bố photon đến. Module: `model/zc702_resource_model.py`; phép thử dự kiến: `syn/zc702/run_schedule_validation.py`.

## Chu kỳ decoder

Với code c, số iteration I và số cạnh E trong base matrix, mô hình dùng:

```text
C_attempt = 28 + I * C_iteration(c)
            + 1(final_USC) * (E + 8 * number_of_layers + 1)

C_iteration: r12=248, r23=211, r34=199, r56=179 cycles
T_attempt_us = C_attempt / 50
```

Hệ số 28 gồm 26 chu kỳ S_LOAD và hai chu kỳ quan sát start/done của scheduler. Thành phần cuối là đường tính USC/popcount ở lần decode thất bại. Công thức chỉ áp dụng cho cohort ET=PP=0, r0=0; success ở iteration limit bị loại khỏi phép thử dự đoán vì không phân biệt được strict convergence với đường USC từ trace rút gọn. Job cuối phải hội tụ. Không suy rộng công thức này sang PP hay ET đã bật.

Đối chiếu hồi cứu đã có 248 batch ×4 vector khớp tổng busy cycles; hai batch có đường đi nhập nhằng được ghi riêng. Kết quả này dùng để kiểm tra công thức, không được gọi là kiểm chứng latency trên dữ liệu mới. Evidence: `reports/resource_model_20261027/retrospective_check.json` và `retrospective_cycle_checks.csv`.

## Hai tài nguyên

Decoder xử lý tối đa một attempt tại một thời điểm. PS/DMA xử lý load hoặc reveal tuần tự nhưng có thể chồng lên decoder của context khác. Lập lịch decoder round robin theo context sẵn sàng; thứ tự PS ưu tiên initial load, load job tiếp theo, rồi reveal theo context.

- L: chi phí trung bình mỗi job, đơn vị µs/job. Intercept này gộp quản lý/output/control, không phải số đo input-load thuần.
- R: chi phí retry, đơn vị µs/revealed bit, gộp dispatch trung bình.
- W: độ trễ được chèn sau khi PS có thể quan sát decode FAIL. W không bao gồm một stack mạng quang thực.
- Trace iteration/attempt/reveal là đầu vào từ golden. Mô hình chưa dự đoán trace hoặc FER từ QBER.

Với K=1, không có overlap giữa các job, nên tổng thời gian của J job là:

```text
T1 = sum_decode_time + J*L + R*sum_revealed_bits
     + W*number_of_retry_transitions
```

Với nhiều context, mô phỏng discrete-event giữ riêng thời điểm hoàn tất CPU và decoder. Event reveal chỉ trở thành sẵn sàng sau khi FAIL được PS quan sát và W kết thúc. Một context chỉ được tái sử dụng khi job cũ hoàn tất. Thời gian dự đoán phải lớn hơn hoặc bằng cả tổng busy time của decoder lẫn tổng service time của CPU. Các self-check kiểm tra cận này, trường hợp K=1 và bảo toàn decoder work khi L=R=W=0.

Ước lượng `min(K, 1+RTT/T_dec)` chỉ giải thích trực giác trong trường hợp đơn giản. Nó không thay mô hình hai tài nguyên khi load/reveal đáng kể hoặc attempt khác nhau giữa các job.

## Đóng băng và phép thử tiếp theo

Tập training dùng trial ID ở nửa đầu ablation; held-out dùng nửa sau, input hash không giao nhau. Mỗi phía chọn trước bốn vector có độ phức tạp attempt khác nhau khi có thể, không chọn theo latency cần dự đoán. Do vector đã có trong ablation, thuật ngữ held-out ở đây nói tới dữ liệu timing K/RTT mới, không nói đầu vào hoàn toàn chưa từng chạy board.

1. Đo K=1, jobs=4, RTT=0 trên training, ba lần lặp/vector; fit L,R không âm từ phần thời gian ngoài decoder.
2. Lưu tham số, hash model/source và thời điểm monotonic trước phép thử held-out.
3. Dự đoán trước mỗi phép đo held-out; đo K=1/2/4 × RTT=0/100/500/1.000/5.000/10.000 µs ×3 lần lặp, jobs=32.
4. Raw verifier kiểm tra thứ tự thời gian, packet, chu kỳ decoder và tính lại mọi dự đoán. Không fit lại bằng held-out.

Ngưỡng đã chốt trong runner là trung bình sai lệch tuyệt đối ≤10% và lớn nhất ≤20%, với:

```text
e_i = 100 * (T_board_i - T_prediction_i) / T_prediction_i
mean_absolute_error_pct = mean(abs(e_i))
```

Mẫu số là prediction, không phải board measurement; không gọi chỉ số này là MAPE theo mẫu số giá trị thực. Đây là ngưỡng kỹ thuật, không phải khoảng tin cậy. Raw replay PASS và model accepted là hai kết luận riêng. Nếu không đạt, giữ kết quả âm và dùng training/model mới cùng một tập kiểm chứng timing mới; không chỉnh theo bộ held-out này rồi gọi đó là kiểm chứng dự đoán.

## Giới hạn và bước tiếp

Chưa mô hình hóa riêng IRQ, tranh chấp output KEY, UART sản phẩm, PA, xác minh hoặc arrival/backlog. Bốn vector lặp lại dùng đo timing không phải mẫu FER độc lập. Sau phép thử này, cần traffic được điều tiết và chính sách EFFICIENCY/THROUGHPUT trên cùng workload để kiểm chứng điểm giao; xem [đặc tả crossover](CROSSOVER_MODEL_SPEC.md). Không dùng mô hình này chứng minh thiết kế bốn context không tăng BRAM: điều đó cần hai bản kiến trúc tổng hợp độc lập.
