# Chặng tiếp theo: auth chuẩn và mapping nhất quán

Đã sửa lỗi thuật toán SipHash của prototype, bổ sung kiểm thử C độc lập và khôi phục danh mục ID/REV chuẩn cho phiên tiếp theo. P04/PUB04 tiếp tục PARTIAL; không nạp lại FPGA/ELF. Một tiến trình encoder RTL của AI khác đang chạy khi bắt đầu chặng này; source RTL/testbench không bị sửa.

## Thay đổi đã thực hiện

- `auth_channel.c`: thêm block kết thúc mang chiều dài 8 byte trước finalization SipHash-2-4. Mặt nạ tag của prototype thay đổi; không được trộn peer dùng phiên bản cũ/mới trong cùng phiên. Baseline UART chưa dùng module này nên ELF cũ không thay đổi.
- Cập nhật Python model cùng quy ước để không duy trì hai thuật toán tag khác nhau.
- Khóa cấu hình bằng 0 bị từ chối thay vì thay bằng khóa hằng công khai. Chặn transmit trước khi sequence32bit quay vòng; phiên cần rekey trước giới hạn này.
- Packet nonempty nhưng payload NULL bị từ chối. Kiểm thử tag hỏng, packet thiếu byte, replay, empty payload và payload tối đa chạy C thực.
- API `auth_channel_calc_epsilon_auth` trả1,0 để biểu thị chưa có bound được thiết lập; bỏ suy diễn sai N/2⁶⁴ cho prototype computational. Caller không được sử dụng prototype để đáp ứng ngân sách ε phiên. Header nêu rõ PSK legacy chỉ64bit và chưa có session/rekey/storage policy.
- Header persistence được sửa phạm vi: CRC descriptor và guard RAM không phải xác thực/storage chống rollback qua reset. Gate đầy đủ ở [PERSISTENCE_NEXT_GATE.md](PERSISTENCE_NEXT_GATE.md); chưa tuyên bố đã thực hiện storage driver.
- Generator tiến độ dùng receipt/hash mới để ghi đúng P04 host-tested; P05 trỏ raw STA gốc có provenance. PUB03 được ghi là retrospective, PUB04 vẫn thiếu durable commit/anchor. R02 không còn khẳng định cả hai matrix/rank đã kiểm chứng.

## Kiểm chứng

Lệnh tái hiện:

```powershell
python syn/zc702/test_auth_prototype.py
```

Kết quả tại checkpoint:

| Kiểm tra | Kết quả | Phạm vi |
|---|---|---|
| Known-answer chuẩn 8byte | `93f5f5799a932462` | C và Python model |
| So C với reference độc lập | 4.096 bộ khóa/message khớp | Hàm SipHash trên đúng 8byte, không phải proof của toàn giao thức |
| Packet/negative/KAT checks | 8.262 kiểm tra PASS | C chạy trên PC, không phải UART board |
| Compile Cortex-A9 | `-O2 -Wall -Wextra -Werror`, PASS | Object compile, không thực thi trên ARM |
| Firmware baseline | 27/27 file khớp manifest | Không có FPGA/ELF mới được nạp |

Reference giữ nguyên license trong `syn/zc702/tests/reference`, URL/SHA tại SOURCE.json; nguồn gốc [SipHash reference](https://github.com/veorq/SipHash/blob/master/siphash.c). Receipt máy đọc: [AUTH_TEST_RECEIPT.json](AUTH_TEST_RECEIPT.json). Không dùng kết quả các test này làm tuyên bố xác thực information-theoretic, khóa128bit hay security composable toàn hệ thống.

## Mapping và tài liệu lịch sử

[MAPPING_CANONICAL.md](MAPPING_CANONICAL.md) render đủ35 mục từ work items và giữ tên14finding gốc. Không đổi P03 thành pacing, P05 thành persistence, R06 thành TRNG hoặc PUB03 thành queue dynamics. Pointer hiện hành: `reports/RECONCILIATION_CURRENT.json`; guide đầu phiên đã yêu cầu đọc pointer này.

Folder reconciliation trước và các review độc lập giữ nguyên vì đã có manifest lịch sử. Mapping/bảng “allfixed” trong báo cáo cũ được supersede bởi pointer mới; không chỉnh archive để làm hash xanh. Source trước sửa và bảng tiến độ trước chặng này được giữ ở `before/`; hash thay đổi ghi trong CHANGE_RECEIPT.json.

## Trạng thái và các gate còn lại

Toàn bộ35mục vẫn có13PASS chức năng,20PARTIAL và2TODO; không tự tăng tỷ lệ hoàn thành từ host test. Auth mới chưa được link vào baseline ELF; seed PA và kênh Alice chưa được chuyển sang một giao thức phiên an toàn. Gate tiếp theo:

1. Thiết kế key provisioning độc lập, transcript/session ID, rekey, budget và durable replay state. PSK64 legacy là giới hạn phải giải quyết trước triển khai xác thực sản phẩm.
2. Chọn durable storage và trusted monotonic anchor; chạy kiểm thử mất RAM/reset/power loss/snapshot cũ và atomic commit. CRC đúng không đóng gate này.
3. Hoàn tất encoder RTL đang kiểm thử với watchdog, golden và backpressure; chỉ công nhận sau log kết thúc có PASS.
4. Tích hợp các thành phần đã đủ điều kiện trên firmware/bitstream riêng, preflight rồi regression board; giữ baseline50MHz cho tới khi có evidence mới.

Lượt này không sửa RTL NTT/LDPC dài hoặc nhận thay công việc xsim đang chạy. Các prototype đó vẫn cần triển khai/testbench/PnR riêng. Không có yêu cầu user phải xác nhận lại thao tác board trong phạm vi đã cho phép; kiểm tra owner COM3 trước mọi phiên board sau này.
