# QAS2 bảo vệ lệnh IR → xác minh → PA thực trên ZC702

Đã build ELF thử riêng có dispatcher QAS2, chạy trên Cortex-A9 và điều khiển các lõi IR/PA trong PL50MHz. Bốn fixture r12/r23/r34/r56 đều giải mã KEY và PA đúng. Baseline UART đã được nạp lại sau thử; không sửa binary hoặc source baseline.

## Phạm vi triển khai

`secure_app_service.h` dùng lại functional handler đã có, chỉ gọi handler sau MAC hợp lệ, opcode QAS2=0x100 và allowlist lệnh ứng dụng10/11/12/14/20/73. Output handler được capture, trả trong QAS2 opcode0x8100 có MAC. Legacy UART main được đổi tên trong translation unit riêng, không được gọi; parser thử không dispatch lệnh plaintext vào IR.

Handshake/provision/reset vẫn là lab controls từ firmware thử trước, root PSK fixture công khai và nonce từ PC. Lệnh G là diagnostic plaintext chỉ đọc counter/flags. Đây không phải secure production channel; MAC không mã hóa và lệnh đọc KEY chỉ dùng cho fixture công khai. Không đưa debug KEY readback vào giao thức QKD thật.

## Kết quả board

Raw run: `build/zc702/secure_app_runs/20261027T103117Z/`.
ELF riêng: `build/zc702/secure_app_test/20261027_integration/secure_app_test.elf`.

| Code | Attempts | KEY thực | PA1024 thực |
|---|---:|---|---|
| r12 | 2 | Khớp golden | Khớp tính độc lập từ KEY/seed |
| r23 | 2 | Khớp golden | Khớp tính độc lập từ KEY/seed |
| r34 | 1 | Khớp golden | Khớp tính độc lập từ KEY/seed |
| r56 | 1 | Khớp golden | Khớp tính độc lập từ KEY/seed |

- **78 kiểm tra runner PASS**; đây không phải independent FER campaign.
- **107 command/response raw-verified**, gồm24lượt dispatch ứng dụng đã xác thực.
- MAC sai được chặn trước load/run/verify–PA; counter dispatch, verification-used và flags không đổi so diagnostic trước/sau.
- Replay, SID phiên cũ và lệnh plaintext không dispatch vào handler. Bộ MAC và sequence phản hồi được verifier tính lại độc lập.
- Đổi/reset phiên xóa staging và key-valid, không refund verification-used trong cùng boot; cuối phiên dùng4lượt xác minh, mỗi block một lượt. Chưa có bảo vệ budget qua mất điện/CPU reboot.
- Restore baseline có JTAG/MMIO receipt và `QKD_UART_READY`;27file baseline vẫn khớp hash. Không chạy lại toàn bộ suite IR/PA baseline vì binary không thay đổi.

Proof: [verified_evidence.json](../zc702_secure_app_20261027T103117Z/verified_evidence.json). CSV KEY/PA hash đúng scope: [blocks.csv](../zc702_secure_app_20261027T103117Z/blocks.csv).

## Kiểm chứng độc lập và provenance

```powershell
python syn/zc702/verify_secure_app_board.py build/zc702/secure_app_runs/20261027T103117Z
```

Verifier đọc UART và TX, kiểm tra HMAC handshake bằng Python Bob, QAS2 command/response MAC và sequence, mô phỏng counter/flags để đối chiếu G; so decode trace và KEY với golden fixture đã pin SHA, tính lại tag và PA từ **KEY thật đọc qua phản hồi đã MAC**. Không tin riêng các cờ `key_match/pa_match` trong raw result.

Một lỗi tên trường metadata trong runner phiên đầu: `blocks.input_key_words` chứa danh sách PA16word, không phải KEY48word. Raw được giữ nguyên; proof ghi rõ và CSV mới lấy KEY/PA từ raw authenticated replies. Runner hiện đã sửa tên `key_words`/`pa_words` cho phiên sau; bản đã thực thi được giữ tại `runner_at_execution.py`. Không dùng trường nhầm tên làm bằng chứng KEY.

Builder lưu translation unit được tạo, snapshot source/manifest/BSP library hashes và ELF SHA. Bản thử chỉ giữ một ownerCOM3; baseline restore trong finally. Không overwrite build/run đã có manifest/proof.

## Gate còn lại

P04 tiếp tục PARTIAL: đã có functional authentication gate cho một tập lệnh IR/per-block verify–PA trên board, nhưng còn trusted root provisioning, nguồn nonce board, handshake review, durable state và authenticated error/control policy cho dispatcher sản phẩm. Các lệnh accumulator/split/EMIT lớn, đa context và policy controller chưa nằm trong allowlist mới; không nhận đã bảo vệ toàn chuỗi finite-key end-to-end.

PUB04 tiếp tục PARTIAL: reset phiên không refund cap trong boot là chức năng đã kiểm tra, không phải atomic persistent accounting qua reset/power loss. Root public/test data/expected PA/KEY readback là fixture, không chứng nhận secret key composable.

Thứ tự tiếp theo: chốt trust/storage và phạm vi computational authentication → thu hẹp API sản phẩm, bỏ lab provisioning/debug KEY, xác thực control/error → bảo vệ các lệnh gom khóa/EMIT và fault cases → regression reset/power-loss trên firmware riêng. Giữ baseline50MHz và mapping35ID hiện hành; không tự tăng số PASS từ một fixture integration.
