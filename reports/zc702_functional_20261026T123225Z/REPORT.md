# Nghiệm thu chức năng: ARM + IR + xác minh + PA

Lượt `20261026T123225Z` trên ZC702, PL 50 MHz; Alice mô phỏng PC, UART, seed công khai từ PC OS CSPRNG.

| Policy | Ca thử | IR sửa đúng | Loại sớm | Decoder discard | PA khớp | Tag bị từ chối |
|---|---:|---:|---:|---:|---:|---:|
| efficiency | 21 | 13 | 6 | 2 | 12 | 1 |
| throughput | 21 | 13 | 6 | 2 | 13 | 0 |
| adaptive | 21 | 13 | 6 | 2 | 13 | 0 |

Đã đối chiếu log thô: 71 attempt, 39 KEY, 38 PA; 8 quyết định accumulator mô phỏng; 4 context trong phép thử nhiều bank.

ARM chạy các hàm chọn profile/plan/next_reveal/update trích từ driver tham chiếu. Host chỉ mô phỏng Alice, cấp syndrome/reveal và kiểm tra mô hình sau từng phản hồi phần cứng. KEY đọc từ DMA được bỏ 307 vị trí D, đệm zero tới 2784 bit, rồi đi qua PA FPGA để tạo tag 64 bit và hash 1024 bit. Một tag được cố ý làm sai; firmware từ chối và không phát PA cuối cùng cho ca đó.

Bốn context được nạp HOLD và cùng đưa vào hàng đợi. DMA nhận từng frame; cờ SUCCESS duy nhất xác định context trước khi nhận frame tiếp. Kiểm tra dừng nếu ownership mơ hồ; không giả định DDR giữ TUSER. Phép thử này chưa xác nhận mức tăng thông lượng hay RTT theo tài liệu.

Thống kê decoy trong phép thử accumulator lấy từ phiên mô phỏng có sẵn; không ghép với khóa CSV và chưa phát khóa tích lũy theo độ dài finite-key. PE 256 bit của ca IR là mẫu công khai trong harness, vẫn nằm trong đầu vào hash chức năng; chưa có xử lý loại mẫu/tính leakage để tuyên bố khóa bí mật. Backlog là kích thích được lập trước để kiểm tra hysteresis, không phải hàng đợi đo từ luồng quang.

IRQ lõi QKD đã được đối chiếu ở 71 attempt trong lượt này; ISR mask nguồn, polling vẫn dùng để chờ kết quả. Chưa xác nhận ngắt DMA hay bộ lập lịch hoàn toàn theo ngắt. Chưa nghiệm thu 70 MHz, FER trên 10⁴ block độc lập, PA khối lớn, TRNG vật lý hay kênh xác thực Alice/Bob.

[Receipt](../../build/zc702/functional_runs/20261026T123225Z/result.json) · [UART thô](../../build/zc702/functional_runs/20261026T123225Z/uart.log)
