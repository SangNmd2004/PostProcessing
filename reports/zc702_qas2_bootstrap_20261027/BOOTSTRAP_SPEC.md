# Bootstrap QBH1 cho QAS2 — prototype host

Đây là handshake ứng dụng thử nghiệm dùng primitive chuẩn, **không phải giao thức chuẩn hóa hay đã có chứng minh bảo mật độc lập**. Hai đầu handshake hiện chạy Python; C chỉ nhận khóa đã dẫn xuất để xử lý QAS2 data trong test host. Chưa có ARM handshake, UART integration, root-key storage, durable budget hoặc forward secrecy.

## Trust và freshness

Provisioner tin cậy cung cấp root PSK32byte có entropy thích hợp và hai peer ID16byte khác nhau. Không nhận PSK/peer ID từ frame chưa xác thực. Root PSK không được lấy từ PA public seed. Nonce32byte mỗi phía mặc định dùng OS CSPRNG trên PC; injection deterministic chỉ dùng fixture. Không gọi đây là entropy vật lý trên kit.

Mỗi connection dùng object handshake mới. Malformed frame, sai MAC, sai peer/transcript hoặc sai thứ tự làm object CLOSED; caller phải bỏ connection và tạo attempt mới với nonce mới. Không có retransmission/timer trong module: dispatcher phải đặt timeout và gọi abort, không tự cấp lại phiên cũ. Có thể rate-limit bootstrap trước khi ghép transport.

## Bốn thông điệp

Mọi frame bắt đầu ASCII `QBH1` và kind1byte. UInt32 little-endian; các field byte array có độ dài cố định. Mọi tag HMAC-SHA25632byte đầy đủ.

| Kind | Payload trước tag | Số byte cả tag | Key/label xác thực |
|---:|---|---:|---|
| 1 ClientHello | magic4,kind1,AliceID16,BobID16,nonceA32,proposed_limit4 | 105 | root PSK / client-hello |
| 2 ServerHello | magic4,kind1,SHA256(ClientHello cả tag)32,nonceB32,chosen_limit4 | 105 | root PSK / server-hello |
| 3 ClientFinished | magic4,kind1,transcript_hash32 | 69 | derived client-finished key |
| 4 ServerFinished | magic4,kind1,transcript_hash32 | 69 | derived server-finished key |

Tag tính trên `QKD/QAS2/bootstrap/v1/ || label || 0x00 || payload`. Limit server chọn min(client,server), trong1..1.000.000; Alice kiểm tra không vượt đề xuất. Peer ID/nonce/limit/challenge đều được ràng buộc qua HMAC và transcript.

`transcript_hash = SHA256(ClientHello || ServerHello)`, gồm cả hai tag. HKDF-SHA256 dùng IKM=rootPSK, salt=nonceA||nonceB, info=`QKD/QAS2/session/v1/ || transcript_hash || / || purpose`.

Các purpose tách biệt: `sid`16byte, `alice-to-bob`16byte, `bob-to-alice`16byte, `client-finished`32byte, `server-finished`32byte. HKDF theo [RFC5869](https://www.rfc-editor.org/rfc/rfc5869.html); HMAC test vectors theo [RFC4231](https://www.rfc-editor.org/rfc/rfc4231.html). Dùng primitive chuẩn không tự chứng minh tính an toàn của state machine/protocol bao quanh.

Bob chỉ ESTABLISHED sau kiểm tra ClientFinished và tạo ServerFinished; Alice chỉ ESTABLISHED sau kiểm tra ServerFinished. Không export key trước trạng thái này. `take_provisioning()` chỉ được dùng một lần trên object, chuyển sang CONSUMED. Provisioning chứa secret chỉ dành cho caller tin cậy; không serialize/log/reuse nó. Chặn export lần hai không thể ngăn caller độc hại sao chép/reprovision secret đã được cấp.

## Giới hạn được giữ công khai

- Replay ClientHello cũ có thể được Bob xác thực lại, nhưng ClientFinished cũ không khớp challenge nonceB mới. Điều này phụ thuộc nonceB thực sự mới, không phải persistent replay database.
- Nếu cả hai nonce lặp với cùng PSK/IDs/limit thì SID/keys lặp. Test xác nhận giới hạn này; chưa có cơ chế durable chống entropy-source rollback trên board.
- Không forward secrecy: lộ PSK cùng transcript có thể làm lộ khóa phiên dẫn xuất. Không tuyên bố QKD composable/unconditional authentication.
- Python bỏ tham chiếu secret khi abort/finish, không cam kết xóa mọi bản sao vật lý trong RAM. Chưa có secure provisioning PC→board.
- Session freshness cho QAS2 không giải quyết budget correctness của IR/accumulator qua reset. PUB04 vẫn cần trusted monotonic durable state và atomic authenticated commit riêng.
- Bob có thể hoàn tất local state trước khi Alice nhận ServerFinished; chưa có policy buffering/retry cho mất thông điệp cuối. Không dispatch application data phía Alice trước local key confirmation.

## Gate tiếp theo

Review đặc tả/threat model trước port ARM. Chọn primitive implementation C được pin và có vectors RFC; kiểm chứng Python↔C handshake, timeout/abort và dispatch state. Sau đó triển khai trusted root provisioning/entropy trên kit, durable accounting và transport riêng. Chỉ chuyển baseline sau regression thật; không gửi QBH1/QAS2 cho firmware UART hiện tại vì dispatcher cũ chưa hỗ trợ.
