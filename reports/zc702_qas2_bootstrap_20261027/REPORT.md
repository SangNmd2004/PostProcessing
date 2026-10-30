# Chặng bootstrap: PSK, transcript và dẫn xuất phiên

Đã triển khai prototype handshake bốn thông điệp trong `syn/zc702/qas2_bootstrap.py` dùng HMAC-SHA256 và HKDF-SHA256 qua thư viện Python. Sau xác nhận, hai phía nhận SID/khóa QAS2 riêng cho hai chiều; không export trước xác nhận hoặc export lần hai trên cùng object.

Lệnh tái hiện:

```powershell
python syn/zc702/test_qas2_bootstrap.py --output reports/NEW_BOOTSTRAP_RUN
```

## Bằng chứng đã chạy

| Kiểm tra | Kết quả | Giới hạn |
|---|---|---|
| HMAC-SHA256 | RFC4231 case1 PASS | Primitive stdlib Python |
| HKDF-SHA256 | RFC5869 cases1,3 PASS | Bao gồm expand nhiều block và salt/info rỗng |
| Handshake hoàn tất | 100 phiên host; SID,keys,limit khớp | Nonce fixture deterministic công khai |
| Tamper transcript | Lật từng348byte trên4message, đều bị từ chối và CLOSED | Không phải phép ước lượng xác suất giả mạo |
| Negative/state | Wrong PSK, wrong peer ID, nonce không hợp lệ, trộn transcript, replay finished, export sớm/lặp bị chặn | Python state machine |
| Khóa dẫn xuất dùng với C | Alice Python→QAS2 C và C→Python ở100phiên đều khớp payload | C chạy host, không ARM handshake/UART |
| Tổng assertion | 1.161 PASS | Có nhiều kiểm tra trên cùng fixture, không phải FER samples |
| Cả hai nonce tái sử dụng | Có thể lặpSID/keys, test giữ KNOWN_LIMITATION | Chưa chứng minh durable freshness |

Receipt/source hash/lệnh compile ở [BOOTSTRAP_TEST_RECEIPT.json](BOOTSTRAP_TEST_RECEIPT.json). Bốn binary fixture là thông điệp host test công khai, không phải UART capture. Đặc tả đầy đủ và gate còn lại: [BOOTSTRAP_SPEC.md](BOOTSTRAP_SPEC.md).

HMAC vectors tham chiếu [RFC4231](https://www.rfc-editor.org/rfc/rfc4231.html), HKDF tham chiếu [RFC5869](https://www.rfc-editor.org/rfc/rfc5869.html). Các test này xác nhận primitive/functional interop được nêu, không phải chứng minh một handshake mới có đầy đủ tính chất bảo mật.

## Trạng thái dự án

P04 vẫn PARTIAL: root provisioning, entropy/trusted freshness trên board, C/ARM implementation của handshake và QAS2 dispatcher thật còn thiếu. Đây là computational PSK path, không forward secret hoặc information-theoretic; chưa thỏa các claim bảo mật QKD toàn hệ thống.

PUB04 vẫn PARTIAL: session-key freshness không thay thế cơ chế bảo vệ budget IR/verification qua reset/power loss. Không sửa descriptor RAM thành “đã an toàn” hoặc cho phép reset để refund budget. Baseline50MHz/bitstream/ELF không thay đổi, không mở COM3/JTAG và không sửa tiến trình encoder RTL khác.

Gate tiếp theo: đối soát đặc tả, port HMAC/HKDF+state machine lên C với vectors RFC/Python interop → timeout/dispatch/secure provisioning trên firmware riêng → durable accounting → regression board. Giữ13PASS chức năng/20PARTIAL/2TODO, không tăng tỷ lệ theo host test.
