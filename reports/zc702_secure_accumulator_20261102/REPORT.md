# QAS2 accumulator: nghiệm thu chức năng có giới hạn

Ngày 02/11/2026. Checkpoint trước được kiểm tra 58/58 file; checkpoint bootstrap trước đó 46/46; baseline 27/27. Con trỏ đầu phiên vẫn là secure-app 27/10. Không tìm thấy `AGENTS.md` áp dụng hoặc `GUIDE_BAN_GIAO_AI_TIEP_THEO.md` trong checkout; đã đọc tài liệu lõi, kế hoạch, CSV và hai báo cáo review/recheck thay thế cho phần bàn giao thiếu. Chi tiết hash đầu vào trong [PREFLIGHT.json](PREFLIGHT.json).

Đã mở rộng nhánh ELF thử riêng, không sửa source/binary baseline, không rebuild PL. PL giữ 50 MHz. Kết quả này kiểm tra giao thức và buffer trên fixture công khai, không chứng minh khóa bí mật của hệ QKD quang.

## Opcode và hợp đồng

Bảng dưới đối chiếu source baseline với allowlist cũ 10/11/12/14/20/73. `secure_service_overlay.h` và `secure_functional_overlay.h` chỉ được tạo trong thư mục build thử; stream variant riêng nằm ở `secure_key_stream.h`.

| Opcode | Hành vi source | Phạm vi nhánh thử mới |
|---|---|---|
| 10/11/12 | Load, decode/retry, reveal context 0 | Kiểm tra toàn bộ kích thước và reveal trước DMA/ghi thanh ghi |
| 13 | Discard context | Nội bộ lifecycle; không mở thêm lệnh plaintext |
| 14/20 | Debug KEY, verify + PA1024 | Giữ lab API cũ; op20 không dùng cho block đã bind accumulator |
| 30–33 | Accumulator metadata rời buffer | Bị chặn |
| 60 | Verify tag rồi append key cùng counts | Chỉ nhận đúng ID + metadata đã bind ở op80; burn ID khi thử tag/budget; không append lần hai |
| 61/81 | Reset stream / ABORT mới | Qua QAS2; dừng DMA rồi wipe; giữ next ID trong SID hiện tại và giữ verification-used/limit trong boot |
| 62 | WAIT/EMIT/split/ABORT finite-key | Qua QAS2; thời gian mô phỏng không lùi; chặn khi còn block chưa giải quyết |
| 63/64 | Nạp seed / PA nhiều pass | Seed phải đúng tổng/offset/count, đủ trước EMIT |
| 65/66 | Đọc / xóa output | Qua QAS2; giới hạn 128 word mỗi phản hồi để tránh tràn capture |
| 67/69 | State / CRC các buffer cho wipe test | Qua QAS2; CRC chỉ là bằng chứng thử wipe, không chống rollback |
| 68 | Debug raw accumulator | Bị chặn; không mở quyền debug này |
| 72/73 | Hạ / đọc verification cap | Op72 chỉ hạ tới mức không dưới used; không thể hoàn budget |
| 80 | Load mới kèm ID + nk/nt/mt/time | Counts mô phỏng gắn với block ngay trước IR và được MAC bảo vệ |
| 82 | Digest buffer | Chỉ SHA-256 + bit length, không đọc raw key; dùng đối chiếu phần đuôi |

MAC/SID/sequence/outer opcode và độ dài được kiểm tra trước handler. Sau MAC hợp lệ, lỗi policy trả trong QAS2 opcode 0x8100. Dự trữ chỗ/budget phản hồi trước thay đổi ứng dụng. Bad MAC tiêu tốn lượt MAC-check theo QAS2; replay/frame lỗi không chạy handler hay tiêu tốn verification-tag budget. Bộ đếm verification tính cả tag sai; session reset không hoàn lại used hoặc limit trong boot. Hardware error dừng DMA, wipe khi DMA đã dừng và chốt health=0; lỗi DMA reset không cho phép dispatch tiếp. Chính sách này không bảo vệ reboot.

## Kiểm chứng

- Chạy lại verifier checkpoint cũ vào output mới: **107 raw commands, 24 dispatches**, không ghi lại archive cũ.
- Host C: dispatcher QAS2 và stream C thật, IR/PA/DMA được instrument giả lập. Kiểm tra metadata, tag/replay, biên buffer, split không thẳng word, phản hồi thiếu chỗ/budget và lỗi DMA. 1.500.317 assertion bao gồm vòng kiểm tra từng word đã wipe; không phải 1.500.317 trial độc lập. [Host receipt](host/HOST_RECEIPT.json).
- ARM compile `-O2 -Wall -Wextra -Werror` đạt; build manifest lưu lệnh, source snapshot, generated headers và ELF SHA.
- Board ZC702/COM3: **888 raw commands**, **767 dispatches**, **172 append đã verify**, **17 policy reject**, **3 tag reject**. Verification cap được hạ có xác thực xuống 175, dùng đúng 175 lượt; lần tiếp theo bị chặn và reset không hoàn cap.
- EMIT thường: input **110.600 bit**, output **37.568 bit**, không có đuôi. EMIT split: prefix **248.850 bit**, output **115.968 bit**, giữ **2.765 bit** đuôi. Toàn bộ 587 + 1.812 word PA khớp mô hình Hankel độc lập từ KEY và seed thực trong transcript. Digest phần đuôi khớp bit-packed model, bao gồm padding.
- Reset được thử lúc decode đang active, sau decode, sau append, sau clear output và khi seed đang nạp dở. ABORT có xác thực xóa phần đuôi; 11 lượt CRC wipe và 3 digest buffer được verifier tính lại.
- Verifier đọc raw TX JSONL và UART, tự dựng lại handshake/MAC/sequence, golden KEY từ vector .bin được hash, tag, counts/leak, quyết định và PA. Không dùng runner PASS hoặc expected PA làm nghiệm thu. [Proof](board_verification_attempt2/verified_evidence.json), [từng command](board_verification_attempt2/cases.csv).
- Negative control sửa một word PA và tạo lại MAC hợp lệ: verifier vẫn từ chối ở đối chiếu PA; các cờ runner giữ nguyên. [Receipt](VERIFIER_NEGATIVE_CONTROL.json).

Lệnh chính:

```powershell
python syn/zc702/build_secure_app_test.py --accumulator --output build/zc702/secure_app_test/20261102_accumulator
python syn/zc702/run_secure_accumulator_board.py --build build/zc702/secure_app_test/20261102_accumulator
python syn/zc702/verify_secure_accumulator_board.py build/zc702/secure_accumulator_runs/20261102T045046Z --output reports/zc702_secure_accumulator_20261102/board_verification_attempt2
```

Không chạy lại vào thư mục build/report đã niêm phong; chọn output mới. Lượt verifier đầu dừng vì tìm snapshot bitstream thay vì baseline dependency; đã sửa resolver, không đổi raw evidence và không chạy lại board vì lỗi này. Hai buffer copy/source variant được giữ đầy đủ để review.

## Giới hạn và gate tiếp theo

Lượt mới dùng lặp fixture r56; bốn code đã có proof per-block cũ, chưa phải bốn-code authenticated accumulator regression. Counts mới là synthetic gán cho từng fixture block, không lấy từ detector và không chứng minh giả định decoy/finite-key của nguồn thực. Không xem các lần lặp là mẫu FER độc lập. ℓ làm tròn xuống bội 64 theo baseline model; đây là độ dài output chức năng.

Chưa thử trên board buffer gần 16 Mbit, fault DMA cưỡng bức, reset khi output còn chưa clear, hoặc nhánh tự quyết định PA_ABORT qua allowlist mới. Host boundary/DMA tests không thay thế các gate đó. Nguồn gốc PSK/nonce vẫn công khai, provisioning/reset/G plaintext và debug KEY cũ còn là lab controls. Chưa có trusted boot/provisioning, entropy/freshness qua reboot, durable accounting, chống rollback hay chứng minh bảo mật handshake.

P04/PUB04 giữ PARTIAL, toàn bộ 35 ID/tên/trạng thái giữ nguyên. Theo câu hỏi điều chỉnh phạm vi của người dùng, không mở tiếp gate production/storage hoặc xây NTT. Ưu tiên sau checkpoint là rà lại PE/leak và đo timeline/K-RTT/profile/FER theo kế hoạch nghiên cứu; các ca hồi phục còn thiếu được giữ thành backlog có giới hạn.

Baseline được nạp lại qua JTAG, có MMIO receipt và `QKD_UART_READY`. 27 hash khớp sau restore. COM3 đã đóng; probe mở rồi đóng lại thành công. `RUNNING_JOBS.json` chỉ chuyển VERIFIED_COMPLETE sau raw verifier.
