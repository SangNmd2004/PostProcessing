# Buffer verified key → finite-key → PA trên ZC702

Lượt `20261026T160423Z`, scenario `smoke`, COM3, PL 50 MHz. Alice và nguồn decoy mô phỏng.

Đã kiểm tra 23 request có CRC/hash, 2 block được thêm sau xác minh và 0 lần EMIT. NK/NT/MT được đối chiếu với đúng cửa sổ nguồn. PE lấy từ X, không lấy mẫu công khai trong Z key.

| Input bit | Output ℓ | Số lượt PA PL | Split | Tail bit |
|---:|---:|---:|---:|---:|

Mọi bit đầu ra được đối chiếu lại bằng NTT số nguyên, dùng seed từ packet thật và key thực đọc từ DMA. Không dùng kết quả FFT dấu phẩy động để quyết định PASS. Tag sai và seed thiếu phải giữ đầu ra; readback tail và CRC toàn bộ buffer xóa được ghi trong checks.csv nếu phép thử có chạy.

Đây là kiểm thử chức năng theo mô hình finite-key hiện có, chưa phải chứng nhận an toàn QKD. Cần rà soát adaptive postselection, ngân sách ε toàn phiên, seed/kênh xác thực. Timestamp điều khiển dùng đồng hồ replay ảo; không phải phép đo thông lượng quang/board. Seed PA/verification là NumPy PCG64 công khai cho replay, được giữ trong packet; không phải nguồn entropy vật lý đã kiểm chứng. Các phiên nguồn được giữ riêng theo level; chúng không được gọi là dữ liệu quang đo thật.

Ca âm có block được dùng lại trong buffer: 0. Nếu khác 0, transcript bổ sung của ca âm chưa được cộng vào leakage; chỉ dùng lượt đó cho kiểm thử chức năng, không dùng số ℓ làm tuyên bố khóa bí mật. Runner mới dành riêng block âm, không giữ lại block đó.

[UART](../../build/zc702/key_stream_runs/20261026T160423Z/uart.log) · [Receipt](../../build/zc702/key_stream_runs/20261026T160423Z/result.json)
