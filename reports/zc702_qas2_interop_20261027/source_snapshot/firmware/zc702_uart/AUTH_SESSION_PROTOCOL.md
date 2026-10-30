# Prototype xác thực phiên QAS2

Module: `auth_session.c/.h`; MAC: SipHash-2-4 reference, tag64bit, key128bit mỗi hướng. Đây là lựa chọn xác thực computational phục vụ kiểm thử, chưa thỏa một yêu cầu xác thực information-theoretic nếu giao thức QKD đặt yêu cầu đó. Không link vào baseline UART và không cung cấp handshake hay nguồn entropy.

## Wire format

| Offset byte | Số byte | Nội dung |
|---:|---:|---|
| 0 | 4 | ASCII `QAS2` |
| 4 | 1 | Version2 |
| 5 | 1 | Hướng0=Alice→Bob,1=Bob→Alice |
| 6 | 2 | Opcode, little-endian |
| 8 | 16 | Session ID công khai |
| 24 | 4 | Sequence little-endian, bắt đầu1 |
| 28 | 4 | Payload length little-endian |
| 32 | length | Payload, tối đa16.384byte |
| 32+length | 8 | SipHash MAC của toàn bộ header và payload |

Kích thước frame=40+length. Không phụ thuộc packing/alignment của struct host/ARM. Không nhận frame legacy `QAUT` hay version khác. Hướng, opcode, SID, sequence và length đều nằm trong MAC; frame sai hướng/phiên hoặc replay bị loại trước chạy MAC. Sequence tăng nghiêm ngặt; frame mất thứ tự bị loại. Đây không phải replay-window cho UDP.

## Cấp phiên và reset

1. `qas_reset` xóa context/khóa, mặc định đóng; không nhận/gửi packet.
2. Chỉ thành phần cấp phiên tin cậy gọi `qas_open` với SID mới và hai khóa riêng. Không lấy tham số cấp phiên từ packet chưa được xác thực. Khóa test trong unit test công khai, không dùng ngoài fixture.
3. Cả hai peer phải dùng cùng cặp khóa theo chiều Alice→Bob/Bob→Alice và role đối ứng. API từ chối khóa/SID toàn0 và hai khóa bằng nhau; việc không bằng nhau không chứng minh độc lập hoặc đủ entropy, trách nhiệm cấp khóa vẫn ở provisioner.
4. Context đang active không được mở lại; rekey phải đi qua trusted close/reset và cấp phiên mới. API giới hạn số frame gửi và số MAC checks theo `packet_limit`, tối đa1.000.000. Đây là giới hạn vận hành, không phải chứng minh epsilon.
5. MAC sai vẫn tính một check và không tăng sequence đã nhận; retry đúng có thể được chấp nhận nếu chưa hết budget. Packet malformed/replay/saiSID không chạy MAC. Sau reset, budget/sequence trong RAM mất; không được cấp lại SID/khóa cũ.

**Giới hạn được kiểm thử công khai:** nếu caller reset rồi tái cấp đúng SID/khóa cũ, frame cũ có thể được nhận lại. Unit test ghi rõ KNOWN_LIMITATION, không đánh dấu gate rollback đã đạt. Muốn chống trường hợp này cần handshake với freshness được xác thực hoặc trusted persistent anchor. Không dùng CRC, session ID công khai hay chữ ký tự lưu trong cùng snapshot thay anchor.

`qas_wrap` có tham số capacity, không ghi frame nếu thiếu chỗ và không tiêu sequence; hỗ trợ payload nằm cùng buffer bằng cách memmove payload trước ghi header. `qas_unwrap` xóa outputs khi lỗi. Khi thành công, payload pointer tham chiếu buffer caller: giữ buffer bất biến đến khi dispatch hoàn tất, không để DMA ghi đè sau kiểm tra MAC.

## Kiểm thử và gate tích hợp

PC-Alice codec độc lập ở `syn/zc702/qas2_pc.py`; interoperability test ở `syn/zc702/test_qas2_interop.py`. Đây là codec transport-independent, không mở COM3 và chưa tương thích dispatcher UART baseline. Stream collector chỉ thu frame; bắt buộc MAC unwrap trước dispatch. Giữ context theo một owner/thread.

```powershell
python syn/zc702/test_auth_session.py
```

Runner compile C host, chạy packet/negative tests, compile source và reference cho Cortex-A9; kiểm tra manifest baseline không đổi. Không mở COM3/JTAG. Test bao phủ hai chiều,9cỡ payload, lật từng104byte của một frame, replay, phản xạ, sai phiên, reset-closed, khóa sai, capacity, in-place và hết budget do MAC sai. Đây là kiểm thử thuật toán/đóng gói, không phải kiểm thử giao thức trên kit.

Gate tiếp theo là provisioner/handshake, durable state và integration trên firmware riêng. Nếu còn yêu cầu xác thực unconditional, cần chọn universal-hash/fresh-pad construction với quản lý khóa và bound tương ứng trước khi nghiệm thu. Không đổi claim P04/PUB04 thành PASS từ các test này.
