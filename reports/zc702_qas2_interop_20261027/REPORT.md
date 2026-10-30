# Chặng PC-Alice ↔ C: QAS2 interoperability

Đã bổ sung codec Python độc lập cho Alice mô phỏng và kiểm thử hai chiều với source C thật của QAS2 được compile thành thư viện host. Không mở COM3/JTAG, không thay bitstream/ELF và không sửa tiến trình RTL đang chạy của AI khác.

## Kết quả đã chạy

Lệnh tái hiện:

```powershell
python syn/zc702/test_qas2_interop.py --output reports/NEW_INTEROP_RUN
```

Chọn folder đầu ra mới khi tiếp tục, không ghi đè checkpoint đã đóng băng.

| Kiểm tra | Kết quả | Phạm vi |
|---|---|---|
| SipHash KAT | Empty-message và8byte khớp giá trị chuẩn | Python |
| Primitive differential | 300 bộ khóa/message khớp SipHash C reference, gồm multi-block/đuôi không tròn8byte | Host Python/C |
| Wire equality | 1.024 frame hai chiều khớp từng byte | Python encode ↔ C encode |
| Receive interoperability | Mỗi frame được phía Python/C đối ứng nhận đúng opcode/payload | Host mô phỏng, không UART/ARM runtime |
| Tamper/error state | Lật từng104byte, trạng thái lỗi/counter/sequence Python–C khớp | Header/payload/tag |
| Negative/session gates | Replay, phản xạ, saiSID, reset-closed và cạn budget do tag sai khớp | Volatile state |
| Chunked stream | Chunk1/7/128/4096/coalesced; truncated/malformed length | Collector một frame, giới hạn buffer |
| Tổng kiểm tra | 21.951 assertion PASS | Có nhiều kiểm tra buffer; không phải số block FER độc lập |

Machine-readable receipt: [INTEROP_RECEIPT.json](INTEROP_RECEIPT.json), source SHA và seed fixture trong receipt. Các file `fixture_*.bin` là dữ liệu test công khai; không phải capture board. C bridge chỉ phục vụ kiểm thử, không được link vào ELF sản phẩm.

## Sử dụng codec PC

Module `syn/zc702/qas2_pc.py` không tự mở serial hoặc tạo trust. Sau khi provisioner tin cậy đã cấp SID/key/limit, caller tạo `Session`, gọi `open(role, sid, key_ab, key_ba, limit)`; role0=Alice,1=Bob. Gửi bằng `wrap(opcode, payload)` và kiểm tra frame nhận bằng `unwrap(frame)`.

Với transport chia nhỏ dữ liệu, dùng `StreamDecoder.feed(chunk)`. Frame được collector trả về **chưa được xác thực**; chỉ dispatch sau `Session.unwrap` thành công. Collector reset không tự reset session/budget. Lỗi MAC không được xử lý bằng việc mở lại SID/key cũ để hoàn lại budget.

Ví dụ luồng xử lý, không kèm khóa test hoặc kết nối UART thật:

```python
from qas2_pc import Session, StreamDecoder, SessionError

alice = Session()
# Trusted provisioner supplies fresh sid, key_ab, key_ba and packet_limit.
alice.open(0, sid, key_ab, key_ba, packet_limit)
decoder = StreamDecoder()
for chunk in transport_chunks:
    for frame in decoder.feed(chunk):
        opcode, payload = alice.unwrap(frame)
        dispatch_verified(opcode, payload)
```

Caller phải xử lý `SessionError` theo chính sách phiên/transport; không tự cấp lại trust từ dữ liệu chưa xác thực. Session context dùng tuần tự, không chia sẻ giữa nhiều thread mà không khóa. Python reset chỉ bỏ tham chiếu khóa, không cam kết xóa vật lý toàn bộ bản sao trong RAM.

## Giới hạn và gate tiếp theo

P04 vẫn PARTIAL. Codec này chỉ tương thích peer QAS2; baseline UART hiện nhận protocol cũ và chưa có dispatcher QAS2. Không gửi trực tiếp frame QAS2 tới firmware cũ rồi gọi đó là integration test.

Handshake/cấp phiên tin cậy, durable freshness/budget, nonce/key policy và chứng cứ board còn thiếu. Test ghi nhận rõ cấp lại SID/key cũ sau mất RAM có thể cho replay; không đổi claim thành đã chống rollback. MAC là computational SipHash với tag64bit; không chứng nhận xác thực information-theoretic hoặc security composable toàn QKD.

Thứ tự tiếp tục: chốt bootstrap trust/handshake → PC/ARM provisioner và durable session contract → dispatcher trên firmware riêng → regression COM3 thật (tamper/replay/reset/truncated frame) → ghép IR→verify→PA dưới envelope có xác thực. Không đổi baseline trước khi các gate tương ứng có proof.
