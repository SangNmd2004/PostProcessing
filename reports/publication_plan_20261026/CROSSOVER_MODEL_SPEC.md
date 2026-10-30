# Mô hình điểm giao profile: giả định, công thức và dữ liệu cần đo

Đây là mô hình toán có điều kiện, chưa phải điểm giao đã đo trên ZC702. Code: `model/efficiency_throughput_crossover.py`. Không dùng các số 5,81/8,67 Mbit/s lịch sử làm số đo hoặc tiêu chí bắt buộc.

Với policy p, đặt Yp = xác suất sửa đúng × số bit giữ lại trên mỗi block sửa đúng; μp là công suất input block/s. Trong trạng thái ổn định, nguồn đến λ block/s và các hàng đợi có backpressure lý tưởng, Rp(λ)=Yp×min(λ,μp). Các giá trị Y phải đến từ mô hình finite-key có giả định được xác minh; không suy bảo mật từ độ dài PA khớp tham chiếu.

Nếu YE>YT>0 và μT>μE, tại tải thấp EFF tốt hơn. Khi EFF đã bão hòa và THR chưa bão hòa, điểm giao là λ*=YE×μE/YT. Điểm giao dương hữu hạn tồn tại khi μE<λ*<μT, tương đương YT×μT>YE×μE. Nếu THR không có retained-bit saturation cao hơn EFF thì không có điểm giao như luận điểm dự kiến; phải báo đúng kết quả đó.

Với nhiều tài nguyên tuần tự, μp≤min_r(1/dr,p), trong đó dr,p là số giây chiếm dụng resource r trên mỗi input block, gồm IR, PA, kênh truyền và PS/DMA. Demand cần xét overlap và số context; không cộng parent/child profiler. Nếu PA đã là nút giới hạn cho cả hai policy, lợi thế IR có thể không chuyển thành lợi thế output. Hysteresis, burst và hàng đợi hữu hạn cần mô hình sự kiện riêng, không được kết luận từ đường bao fluid này.

Đối với blind IR fixed policy/code, r(a)=r0+min((a−1)Δ,D−r0), leakage IR của một block hoàn thành ở attempt a là m−D+r(a). Xác suất còn cần attempt a là P(A≥a), nên E[A]=Σa P(A≥a). Mean leakage trên retained correct blocks phải lấy có điều kiện theo correct success, không trộn discard hoặc wrong codeword vào mẫu giữ khóa. Tag/PE leakage cần cộng riêng theo transcript thực tế. Các xác suất outcome phải được ước lượng trên training và kiểm chứng ở held-out; mô hình này chưa tự suy chúng từ QBER/code.

Những việc cần làm để nghiệm thu PUB02:

1. Đo EFF/THR trên cùng input/PE độc lập, cùng nguồn và các mức QBER; lưu code/r0/Δ, số attempt, outcome, leak và counter từng resource.
2. Chốt cách tính Y trong scope finite-key đã chọn, ngân sách epsilon và lựa chọn block; tách dữ liệu mô phỏng và chứng nhận bảo mật.
3. Dùng training để suy μp và Yp, đóng băng λ* cùng khoảng bất định trước khi đo nguồn vào có pacing quanh điểm giao.
4. Đo held-out ở dưới/quanh/trên điểm dự đoán, cùng queue capacity/hysteresis, không điều chỉnh λ* theo target rồi gọi là dự đoán trước.
5. Báo cả trường hợp không có crossover, resource bottleneck và độ lệch do burst/hữu hạn. Hiện các số đo timing K1/PA lớn đã có, nhưng bộ hai policy với arrival thực vẫn chưa hoàn thành.

Self-check của module dùng các con số không thứ nguyên tổng hợp chỉ để kiểm tra giao điểm và identity E[A]. Không đưa chúng vào bảng kết quả board hoặc diễn giải là tốc độ khóa bí mật.
