# Đối soát lần hai sau sửa lỗi, 27/10/2026

Kết luận: đã tiến bộ đúng hướng ở bảng trạng thái và một số lỗi cụ thể, nhưng **chưa đủ cơ sở công nhận “toàn bộ REV01–REV14 đã sửa triệt để/ALL_PASSED”** trong báo cáo của AI thực hiện. Phần mềm host được cải thiện; chưa có bằng chứng các prototype mới đã tích hợp và nghiệm thu trên ZC702.

Kiểm tra độc lập chỉ ghi vào thư mục này. Không sửa code triển khai, bảng trạng thái chính, báo cáo đối soát của AI kia hoặc bộ review trước. Không mở COM3/JTAG. Tại đầu phiên có một tiến trình RTL test `tb/run_syndrome_encoder_tb.py`; tôi không chạy thêm xsim hoặc can thiệp tiến trình đó. Kết quả RTL cần đối chiếu lại sau khi chủ tiến trình kết thúc.

## 1. Những sửa đổi đã xác nhận

| Nội dung | Kiểm tra lại | Kết luận được phép |
|---|---|---|
| Bảng tiến độ | Work items hiện có 13 PASS, 20 PARTIAL, 2 TODO | Đã rút tỷ lệ 32/35. 13/35 vẫn là tỷ lệ theo đầu mục, không phải công sức |
| Baseline | 27 file khớp firmware manifest | Baseline đã bảo toàn; không dùng hash này chứng minh module mới đã triển khai |
| Ba chặng board trước | Chạy lại raw verifier FER q2, wrong-codeword, schedule vào thư mục riêng; cả ba returncode0 | Các kết quả cũ tiếp tục hợp lệ trong phạm vi đã công bố |
| CRC persistence | Compile và chạy C mới: fresh restore rc0, offset CRC72 | Lỗi tính CRC trên padding trước đây đã sửa |
| Queue hole | C stress40 vòng: failed_round=−1, head=tail=16 | Regression cũ không còn tái hiện trong trường hợp này |
| Replay seq0 | C: lần đầu rc0, replay rc−2 | Lỗi bỏ kiểm tra seq0 đã sửa |
| Profiler mới | Host C chạy; compile Cortex-A9 `-O2 -Wall -Wextra -Werror` rc0 | Lỗi include/API đã sửa; chưa phải số đo PMU/PL mới trên board |
| Syndrome model | So với matrix thật của ir_model: 0 bit khác ở cả r12/r23/r34/r56 | Lỗi matrix giả trong Python model đã sửa |
| Matrix rate0,95 | Không còn trùng chênh lệch shift giữa hai check-row | Không còn 4-cycle theo kiểm tra này; chưa xác nhận rank/FER/decoder/ABI |
| Paced/ablation | Đã ghi queue simulation và tách L1–L4 board / L5–L6 projection; yield cộng theo từng block | Phạm vi diễn giải đúng hơn; chưa thêm phép đo crossover/ablation L5–L6 trên board |

Receipt: [RECHECK_RECEIPT.json](RECHECK_RECEIPT.json), [RAW_REPLAY_RECEIPT.json](RAW_REPLAY_RECEIPT.json). Test C do AI kia viết được tôi compile lại với source hiện tại và executable đặt ở thư mục này. Compile ARM profiler có [log](arm_profiler_compile.log).

## 2. Các điểm còn sai hoặc chưa hoàn tất

### RC01 — High: SipHash mới không khớp thuật toán chuẩn

`firmware/zc702_uart/auth_channel.c` thêm SipRound nhưng `siphash24_64` xử lý block dữ liệu rồi đi thẳng vào finalization; thiếu block kết thúc chứa chiều dài của message 8 byte trong SipHash-2-4 chuẩn.

Tôi tải implementation chính thức để compile đối chiếu cùng key00..0f, message00..07:

```text
SipHash reference: 93f5f5799a932462
Code dự án:       ab0200f58b01d137
equal = 0
```

Nguồn primary: [reference implementation](https://github.com/veorq/SipHash/blob/master/siphash.c), [test vectors](https://github.com/veorq/SipHash/blob/master/vectors.h). Source reference được giữ nguyên license trong `reference/`; probe [recheck_auth.c](recheck_auth.c) gọi đúng hàm static trong source dự án, không viết lại thuật toán dự án.

Điều này không chứng minh có thể tái dùng ngay tấn công SplitMix cũ; nó chứng minh claim “SipHash-2-4 chuẩn đã kiểm chứng” chưa đúng. Kiểm thử hiện tại chỉ kiểm tra tag đổi/round-trip/tamper, không có known-answer test độc lập. Hai nửa key được suy từ một PSK64bit nên không suy ra 128bit key security; header vẫn gọi information-theoretic, chưa phù hợp với việc dùng deterministic PRF. Giữ P04 PARTIAL, dùng implementation chuẩn có test vectors và nêu rõ giả định bảo mật trước tích hợp.

### RC02 — High: CRC đã sửa, chống rollback qua reset chưa có

Guard mới so với session RAM hiện tại chặn được downgrade khi RAM còn trạng thái. Probe độc lập mô phỏng RAM mới khởi tạo:

```text
previous_used = 10
cold_restore_old_snapshot_rc = 0
used_after_restore = 0
```

`session_persist_restore` chưa có trusted counter/epoch lưu ngoài trạng thái vừa bị reset, chưa xác minh auth_tag và chưa commit storage thật. Bản CRC cũ hợp lệ vẫn có thể được phục hồi vào RAM trống. Đây chưa phải tính năng bảo vệ ngân sách phiên qua reset. API còn đọc destination trước khi restore; cần quy định khởi tạo destination rõ ràng, vì test của AI kia khai báo `restored` chưa khởi tạo. Không công nhận host test một warm object là nghiệm thu persistence toàn phiên.

### RC03 — High: báo cáo đối soát đổi nghĩa của ID và REV

Bảng “35 mục” trong `reports/zc702_reconciliation_20261027/REPORT.md` không khớp danh mục chuẩn:

| ID | Mục tiêu chuẩn trong work items | Bị ghi thành trong báo cáo đối soát |
|---|---|---|
| P02 | PE accounting/sample removal | Paced arrival controller |
| P03 | Physical TRNG | Backpressure/throttle |
| P05 | Timing closure70MHz | Session persistence |
| P08 | FER≥10.000 | Adaptive rate selector |
| R06 | Optical channel/dataset | Physical TRNG |
| R07 | Clock/floorplan optimization | Optical calibration |
| PUB03 | Finite-key accumulation | Paced queue dynamics |
| PUB07 | FER statistical campaign | Energy/resource utilization |

Ngay F07 bị đổi từ verification tag sang ring-buffer; P01 bị ghép với số throughput ablation không phải throughput chuỗi IR→PA đầy đủ. Dãy REV cũng bị đổi: REV01 gốc là nâng PASS bằng file tồn tại, báo cáo mới dùng REV01 cho syndrome encoder; REV11 gốc là timing provenance lại dùng cho tiến độ. Do đó “ACCEPTED cả14REV” không chứng minh 14 phát hiện gốc đã được xử lý. Cần giữ nguyên ID, tên mục, tiêu chí và ánh xạ từng finding gốc. Đây là việc cần sửa sớm để tránh AI sau làm lệch hướng.

### RC04 — High: claim cũ chưa được đồng bộ hoặc gắn cảnh báo

Work items đã hạ trạng thái nhưng report TRNG vẫn ghi PASS, entropy vật lý0,9905; optical report vẫn gọi bảng mô hình là đo đạc; timing70MHz mới thiếu provenance vẫn tồn tại như report đo thật. Không yêu cầu xóa archive lịch sử: cần ghi chú superseded/current-scope và chỉ dẫn rõ trong index/report hiện hành.

Các gate PE/adaptive finite-key/prospective freeze, timing provenance, RTL NTT/LDPC dài chưa có evidence mới đủ để đóng. NTT chỉ bổ sung hằng MAX_RADIX2_NTT_LEN và ước lượng partitioning; `fast_toeplitz_ntt_hash` vẫn gọi transform lớn trực tiếp, chưa có implementation overlap-add và chưa có guard `(q−1)%N==0` tại entry point. Không dùng bảng complexity được sửa làm bằng chứng algorithm/runtime đã hỗ trợ khối lớn.

### RC05 — Medium: checkpoint chưa bảo toàn tuyệt đối và thiếu tính đầy đủ của kiểm thử

Manifest của bộ đối soát AI kia khớp đủ17file, không thiếu/thừa trong folder đó. Tuy nhiên đối chiếu manifest review độc lập cũ có một mismatch: `reproduce_c_issues.exe`. Tức ít nhất binary đã thay đổi so với checkpoint cũ, dù báo cáo nói toàn bộ thư mục review giữ read-only. Không thấy bằng chứng các raw board result bị sửa; cần ghi nhận rebuild này, giữ bản gốc khi có thể và không tự ghi đè review để chạy test.

`ALL_PASSED` hiện chỉ là các command/marker được test suite chọn đều pass. Suite chưa có KAT SipHash, reset/storage rollback, xác nhận provenance timing hoặc nghiệm thu mọi RTL. Tên “all14fixed” cần thay bằng danh sách test thực thi và remaining gate. Hash-before trong bảng thay đổi có nhiều mục chỉ là `64c2...`, chưa đủ để đối chiếu độc lập.

### RC06 — Medium: gate TRNG và kết quả RTL còn cần làm đúng phạm vi

Báo cáo đối soát đặt gate TRNG bằng NIST SP800-22. Nghiệm thu nguồn entropy cần kế hoạch đánh giá noise source/min-entropy, dữ liệu restart và health tests phù hợp [NIST SP800-90B](https://csrc.nist.gov/pubs/sp/800/90/b/final); không đóng P03 chỉ từ bộ statistical tests800-22. Đây là chỉnh tiêu chí kiểm chứng, chưa phải nhận định nguồn entropy hiện có đã đạt.

Test encoder RTL mới có source/ROM/shifter và golden vector, là bước đúng. Tại lúc kiểm tra, `xsim.log` mới tới dòng “Testing Rate r12”; chưa có marker toàn bộ rate PASS. Testbench có các vòng `while(!busy)`, `while(!tvalid)`, `while(!done)` chưa có watchdog, nên không được coi process đang chạy là test đạt. Tôi không sửa/chạy lại phần RTL đang do AI kia quản lý; chỉ xác nhận Python model đã khớp matrix thật.

## 3. Đối chiếu các REV gốc

Xem [REV_STATUS.csv](REV_STATUS.csv). Không đánh số lại finding. Các sửa CRC/queue/replay/include/matrix là regression fix có kiểm chứng; triển khai board và chứng cứ bảo mật còn là gate riêng. Relabel mô phỏng là sửa báo cáo, không phải hoàn tất tính năng phần cứng.

## 4. Thứ tự xử lý nên tiếp tục

1. Sửa mapping ID/REV và đồng bộ report/index về trạng thái thực; giữ nguyên danh mục mục tiêu chuẩn.
2. Thay hoặc sửa SipHash theo reference chuẩn, chạy known-answer tests độc lập; xác định mô hình computational authentication, key/session/replay budget.
3. Thiết kế persistence/monotonic state qua reset có storage và authentication thật; test cold reset/rollback, không chỉ RAM object còn sống.
4. Hoàn tất RTL encoder với timeout, log kết thúc và nhiều input/backpressure; tiếp tục NTT/LDPC dài ở prototype riêng.
5. Sau đó mới tích hợp vào ELF/bitstream riêng, preflight và regression trên board. Baseline50MHz giữ nguyên cho tới khi bằng chứng cho phép chuyển.

Review này không xác nhận toàn bộ hệ đã an toàn hoặc hoàn tất 35 mục. Các raw verifier được chạy lại ở output riêng; code triển khai và bảng chính không bị sửa bởi lượt đối soát này.
