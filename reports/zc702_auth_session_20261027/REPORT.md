# Chặng xác thực phiên: QAS2

Đã bổ sung lớp đóng gói/xác minh phiên độc lập trong `firmware/zc702_uart/auth_session.c/.h`, dùng SipHash-2-4 reference hiện đã pin SHA/license. Baseline board vẫn50MHz, không thay bitstream/ELF. Source encoder RTL và tiến trình xsim đang được AI khác xử lý không bị can thiệp.

## Kết quả thực hiện

- Session ID16byte, hai khóa128bit theo hai chiều, role Alice/Bob và sequence bắt đầu1.
- MAC bao phủ header+payload; không nhận packet sai phiên/sai hướng/replay hoặc packet bị sửa.
- Packet length/capacity được kiểm tra; không dùng packed-pointer cast, hỗ trợ buffer in-place.
- Reset xóa khóa và đóng context; mở lại phiên chỉ qua API cấp phiên tin cậy.
- Hạn mức gửi và số lần kiểm tra MAC tách riêng. Tag sai tiêu lượt kiểm tra; không cho packet chưa xác thực đẩy sequence đã nhận lên cao.

Lệnh tái hiện: `python syn/zc702/test_auth_session.py`.

| Kiểm tra | Kết quả | Phạm vi |
|---|---|---|
| C unit/negative checks | 518 PASS,9cỡ payload,104byte tamper | PC host |
| Chuẩn SipHash | Reference pinned, KAT empty-message khớp | Primitive reference; kiểm thử helper8byte riêng ở chặng trước vẫn giữ nguyên |
| Cortex-A9 compile | C session và reference đều PASS, `-O2 -Wall -Wextra -Werror` | Chưa execute trên ARM |
| Baseline manifest | 27/27 hash khớp | Không có deployment mới |
| Cấp lại SID/khóa cũ sau mất RAM | Vẫn có thể nhận frame cũ; test ghi KNOWN_LIMITATION | Gate durable freshness chưa đạt |

Receipt có source hash và lệnh chạy: [SESSION_TEST_RECEIPT.json](SESSION_TEST_RECEIPT.json). Wire format/hợp đồng đầy đủ: [AUTH_SESSION_PROTOCOL.md](../../firmware/zc702_uart/AUTH_SESSION_PROTOCOL.md).

## Phạm vi và việc còn lại

P04 vẫn PARTIAL. Lớp mới bỏ giới hạn key64 của API legacy bằng cách nhận đầy đủ key128 mỗi hướng, nhưng không tự tạo entropy, không làm handshake, không persist replay state và không chứng nhận security QKD. Key/SID trong unit test là fixture công khai.

PUB04 vẫn PARTIAL. Reset đóng transport không thay thế trusted anti-rollback; nếu thành phần cấp phiên dùng lại SID/key thì vẫn có replay. Cần handshake freshness hoặc durable monotonic anchor và atomic authenticated commit trước khi ghép vào firmware thực. Không tự sửa legacy persistence thành “đã an toàn” bằng một guard RAM.

Hướng tiếp tục: triển khai PC-Alice interoperable framing và provisioner theo một đặc tả được chốt; thiết kế durable freshness/budget; sau đó tích hợp vào ELF riêng, regression trên board với malformed/tamper/replay/reset. Nếu luận điểm yêu cầu information-theoretic authentication thì phải chọn construction/quản lý fresh pad tương ứng; QAS2 hiện chỉ là computational prototype.

Danh mục35ID và14REV vẫn theo mapping chuẩn. Không cộng host test thành một mục board PASS và không thay đổi số13PASS/20PARTIAL/2TODO.
