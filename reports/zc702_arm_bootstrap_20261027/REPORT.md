# Port bootstrap sang C/ARM và kiểm thử COM3

Đã port SHA/HMAC/HKDF và endpoint bootstrap phía Bob sang C, đối chiếu Python, build ELF thử riêng và chạy trên ZC702 qua JTAG/UART COM3. Firmware UART baseline đã được nạp lại sau thử và có log READY. Không thay baseline bitstream/ELF trên đĩa.

## Source và kiểm chứng host

- SHA-224/256 source được trích nguyên thuật toán từ [RFC6234](https://www.rfc-editor.org/rfc/rfc6234.txt), bỏ pagination của tài liệu. Giữ copyright/BSD terms trong sha.h, source URL/hash/quy trình trích ở `firmware/crypto/rfc6234/SOURCE.json`.
- `firmware/crypto/qcrypto.c/.h` cung cấp SHA256, HMAC và HKDF wrapper có kiểm tra kích thước; secret tạm được wipe trong C. HKDF info được giới hạn128byte, output tối đa8.160byte cho bootstrap, không allocation động.
- `firmware/zc702_uart/qas2_bootstrap.c/.h` là Bob endpoint cho Alice PC. Không có client handshake C; Alice vẫn Python. Nonce đầu vào/PSK phải do thành phần tin cậy cung cấp, không có entropy source mới trong module.
- Host test `test_c_bootstrap.py`: **1.731 assertion PASS**,180 bộ SHA/HMAC/HKDF đối chiếu hashlib/hmac/HKDF Python (gồm biên block, key>64byte, output nhiều block),100 handshake C Bob↔Python Alice khớp ServerHello/ServerFinished,174byte CH/CF bị lật đều bị từ chối và không export session.

Receipt: [HOST_TEST_RECEIPT.json](HOST_TEST_RECEIPT.json). Lệnh tái hiện: `python syn/zc702/test_c_bootstrap.py --output reports/NEW_C_BOOTSTRAP_RUN`.

## Kết quả board đã raw-verify

Raw run: `build/zc702/bootstrap_board_runs/20261027T101719Z/`.
ELF riêng: `build/zc702/bootstrap_test/20261027_arm_port/bootstrap_test.elf`.

| Phép thử | Kết quả | Phạm vi |
|---|---|---|
| ARM startup primitive KAT | HMAC RFC4231 case1 và HKDF RFC5869 case1 PASS | Cortex-A9, software crypto |
| Handshake hoàn tất | 22 handshake; SH/SF khớp từng byte với Python | C Bob thực trên kit, Python Alice |
| QAS2 authenticated echo | 21 echo đúng opcode/payload; payload0..16.384byte | UART hai chiều, không phải IR→PA application |
| Negative cases | Tamper CH/CF, data replay, oldSID, sai hướng, tag sai, reset-closed và cạn16MAC-check budget đều đúng kỳ vọng | Fixture test được khai báo |
| Runner checks | 149 PASS | Không phải số mẫu FER |
| Raw replay độc lập | 189 lệnh/response khớp Python Bootstrap+Session | Proof khớp SHA raw result/UART |
| Restore baseline | JTAG/MMIO receipt và `QKD_UART_READY version=1 max_words=4096` | Baseline ELF chạy lại, không regression toàn bộ IR/PA trong lượt này |

Proof độc lập: [verified_evidence.json](../zc702_bootstrap_board_20261027T101719Z/verified_evidence.json).

**Đây là ELF lab-only**: root PSK/peer IDs là fixture công khai; nonceB từ PC, không phải TRNG; lệnh provision/reset I/R không được bảo vệ và chỉ dùng trong harness. Không sử dụng firmware này làm secure channel sản phẩm. Không có tuyên bố root-key storage, authenticated enrollment hoặc TRNG đạt chuẩn. PL giữ baseline50MHz, chỉ kiểm tra IP ID; bootstrap/HMAC chạy trong PS, không phải một lõi crypto PL mới.

## Công cụ và provenance

Builder `build_bootstrap_test.py` dùng BSP/linker/libs khớp baseline, lưu ELF/hash/source snapshot/command trong build manifest. `program_bootstrap.tcl` giữ kiểm tra một Zynq/CPU/cable, load XSA/bit và MMIO ID, chỉ thay ELF đích.

`run_bootstrap_board.py` chụp TX/UART/JTAG/result và restore baseline trong finally. Phiên đã chạy được giữ source tại `runner_at_execution.py`; sau phiên này runner được bổ sung atomic checkpoint và RUNNING_JOBS tự động cho các lần tiếp tục. `verify_bootstrap_board.py` không tin riêng checklist: phát lại mọi lệnh vào model Python và kiểm tra byte response, ELF/source provenance và log restore.

Các thư mục build/run đã có proof không được ghi đè. Chọn output mới khi build tiếp. Không dùng số đo throughput hoặc latency suy từ round-trip ASCII fixture làm số hiệu năng QKD.

## Gate còn lại

P04/PUB04 vẫn PARTIAL. Đã có bằng chứng functional PS/UART của bootstrap, nhưng còn threat-model/handshake review, trusted root provisioning, nguồn nonce board, chống rollback/durable budget và dispatcher thực bảo vệ syndrome/reveal/IR→verify→PA. Freshness theo nonce không thay thế correctness epsilon toàn phiên. Không có forward secrecy hoặc thông tin-theoretic authentication proof.

Ưu tiên tiếp theo: chốt cơ chế cấp root key/nonce và chính sách phiên; thiết kế storage/atomic commit với trusted anchor; sau đó ghép envelope với các lệnh ứng dụng trên firmware riêng và chạy fault/reset regression đầy đủ. Baseline vẫn27/27 hash khớp, COM3 đã được giải phóng sau restore.
