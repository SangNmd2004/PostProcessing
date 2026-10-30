# Nhật ký thực hiện các đầu việc ZC702

Phạm vi: Alice/decoy mô phỏng, board ZC702 thật qua COM3. Kết quả mới chỉ được ghi PASS khi có receipt/log/hash và bước kiểm tra độc lập.

## Chuỗi mới đang chạy

[Kế hoạch/checkpoint hiện tại](ONGOING_RESEARCH_STAGES.md): ablation bốn tầng đã hoàn tất 1.000 pairs/4.000 evaluations, bốn pilot FER 1.000 block/điểm đã raw-verify; đang chạy qualification QBER 2% n=10.000. Followup đã xếp tự động kiểm tra actual wrong codeword và validation mô hình held-out. Dùng RUNNING_JOBS/FOLLOWUP_JOBS để biết COM3 còn bận; các dòng “COM3 được giải phóng” của đợt cũ bên dưới là lịch sử.

## Mốc hiện tại đã được xác minh

- **27/10 — profiler PS/PL/UART:** [đợt đo pha](zc702_profiling_20261027/REPORT.md): 36 ca, 288 snapshot, 1.908 phase rows, PMU/global timer và KEY/PA đã kiểm chứng. Thêm 30 snapshot/138 phase rows quanh PA tích lũy: 103 pass, 342,276 ms cho các PA calls; [counter/report PA lớn](zc702_key_stream_20261027T020445Z/PROFILE_REPORT.md). Counter đo thời gian board thật, không dùng replay clock. Hồi quy cap tag 42 ca và stream smoke trên firmware này đều PASS. P06/PUB05 còn gate production/arrival/pure RTL PA.
- **27/10 — cap xác minh chung:** [42 kiểm tra board và raw replay PASS](zc702_verification_budget_20261027T014110Z/REPORT.md). Hai entry point op20/op60 dùng chung counter; 2 tag đúng và 4 tag sai tiêu hao 6 lượt; chặn 2 lượt tiếp theo khi cap=6; reset buffer/controller/accumulator không hoàn lại lượt. Mặc định 18.446 lượt mỗi lần khởi động, cap chỉ giảm. Chưa có persistence/session ID xác thực nên không gọi là ngân sách composable toàn phiên đã hoàn tất.
- **P1 EMIT:** `key_stream_runs/20261026T153858Z`, 439 block →1.213.835 bit đầu vào →104.768 bit đầu ra, 103 pass PA, không còn tail. [Báo cáo](zc702_key_stream_20261026T153858Z/REPORT.md).
- **P1 split→ABORT:** `key_stream_runs/20261026T153016Z`, giữ đúng tail 19.355 bit sau EMIT; sau thêm dữ liệu xấu, ABORT ở 201.845 bit đuôi. NTT replay, dữ liệu/counts nguồn, tail readback và CRC buffer xóa đã kiểm tra độc lập. [Báo cáo](zc702_key_stream_20261026T153016Z/REPORT.md).
- Lượt EMIT đầu `20261026T152300Z` được giữ như thử chức năng lịch sử; có transcript ca âm dùng lại trong buffer nên không dùng ℓ của lượt đó làm claim bảo mật. Hai lượt phía trên đã dành riêng block âm và không giữ nó vào buffer.
- **DDR IR benchmark:** `latency_runs/20261026T155148Z`, 36 phép đo, K=1/2/4, trễ reveal 0/100/1000/10000 µs, 32 job/phép đo. Đây là 1.152 đánh giá bốn vector lặp lại, không phải mẫu FER độc lập. [Báo cáo/đồ thị](zc702_latency_20261026T155148Z/REPORT.md).
- **STA:** route hiện tại đạt slack dương với constraint 50/55 MHz; âm ở 60/70 MHz. Không đổi clock trên board. [Phạm vi phép thử](ZC702_STA_FREQUENCY_TRIAL.md).
- **Ablation mô hình:** 1.000 input ghép cặp, ba cấu hình OMS/random →OMS/GS →NMS/GS. Mean attempts 1,809 →1,222 →1,156; mean f trên success khoảng 1,457 →1,375 →1,367. Số fail ít, chưa có khác biệt FER có ý nghĩa từ so sánh ghép cặp. Không phải số đo FPGA. [Kiểm tra thống kê](model_ablation_20261026T162423Z/STATISTICAL_CHECK.md).
- **FER pilot:** 256 input BSC độc lập, q=3%, r23/NMS+GS, 0 lỗi; cận trên chính xác một phía 95% ≈1,16%. Chưa thể suy FER~10⁻³. Resume đã kiểm thử riêng trên 8 trial.
- **FER chính thức tại một điểm:** [10.000 trial đã postverify](zc702_fer_20261026T160934Z/REPORT.md), 9.998 success / 2 discard / 0 wrong codeword; FER=0,0002, Wilson hai phía 95% [0,00005485; 0,00072900]. Đã kiểm tra 2.500 batch receipt cùng dữ liệu UART, seed và packet. QBER BSC 3%, r23/NMS+GS, không bao gồm tag/PA.

## Trạng thái job FER cũ 26/10 và cách tiếp tục lịch sử

Chiến dịch FER **10.000 trial đã hoàn tất**, raw replay PASS, process đã thoát và **COM3 đã được giải phóng**. [Receipt](FER_LATEST_COMPLETE.json) và [RUNNING_JOBS.json](../RUNNING_JOBS.json) đã ghi VERIFIED_COMPLETE. PID/start time được giữ để truy vết, không phải job còn chạy.

```powershell
Get-Content .\build\zc702\fer_10000_stdout.log -Tail 10
Get-Content .\build\zc702\fer_10000_stderr.log -Tail 10
```

Run cụ thể: `build/zc702/fer_runs/20261026T160934Z`. `result.json` complete=true; `verified_batches.jsonl` và toàn bộ TX/RX được giữ. Receipt hoàn tất trỏ đúng n=10.000, QBER/code và report. Không resume run đã hoàn tất; các lệnh khôi phục dưới đây chỉ áp dụng nếu một run tương lai bị dừng trước khi đủ mẫu.

Nếu process đã dừng trước khi đủ dữ liệu, đọc stderr/receipt trước; chỉ resume sau khi xử lý nguyên nhân và không có app khác giữ COM3:

```powershell
python .\syn\zc702\run_fer_campaign.py --trials 10000 --qber .03 --code r23 --seed-base 1000000 --resume .\build\zc702\fer_runs\20261026T160934Z
```

Không chạy thêm lệnh nạp board/UART hoặc thay model/firmware đang dùng trong lúc job còn chạy. Đây mới là một stratum q=3%/r23; hoàn tất 10.000 mẫu không hoàn tất toàn bộ ma trận QBER/policy/ablation.

Các dòng “đang chạy/chờ” trong mục lịch sử bên dưới thuộc giai đoạn đầu phiên, không phải trạng thái hiện tại.

## Lịch sử đầu phiên tiếp tục 26/10/2026

1. **Kiểm kê bộ bàn giao:** đã kiểm tra 335 file theo manifest của `artifacts/AI_HANDOFF_ZC702_20261026`; không sai hash/kích thước. Điều này xác nhận tính nguyên vẹn bản sao, không xác nhận nội dung khoa học của tài liệu tổng hợp. G?i b?n giao v? receipt n?y ?? ???c d?n theo y?u c?u ng?y 30/10/2026; c?u tr?n ghi nh?n l?n ki?m k? l?ch s?.
2. **P1 – buffer khóa và decoy cùng block:** đã bổ sung `key_stream.h`, `uart_session.py`, `run_key_stream.py`. Thử nhanh trên board đã thêm đúng ba block/8.295 bit sau xác minh; tag sai không thêm khóa hoặc thống kê. Đây là smoke, chưa phải EMIT toàn phiên.
3. **P1 – PA nhiều lượt:** đã bổ sung tham chiếu Hankel bằng NTT số nguyên chính xác, đối chiếu 18 kích thước với mô hình trực tiếp. Chờ đối chiếu toàn bộ đầu ra lớn trên board.
4. **Phiên EMIT:** đang chạy `python syn/zc702/run_key_stream.py --scenario emit`. Tiến độ/receipt mới nằm trong `build/zc702/key_stream_runs/`, console tại `build/zc702/key_stream_emit_latest.log`. Không khởi động thêm ứng dụng chiếm COM3 trong lúc phiên còn chạy.

## Thứ tự tiếp tục đã cập nhật

1. Rà soát và cưỡng chế ngân sách verification theo toàn phiên; bổ sung fault recovery, seed/protocol và phân tích adaptive selection. P1 EMIT/split/ABORT chức năng đã PASS, không chạy lại nếu không có thay đổi.
2. Mở rộng ablation có ghép cặp trên board; kết quả ba cấu hình hiện tại mới là model-only. Sau pilot mới chạy 10⁴ block cho từng stratum QBER/code cần công bố.
3. Đo các pha UART/IR/chờ Alice/verify/PA, arrival/backlog thật và điểm giao EFFICIENCY/THROUGHPUT. Benchmark DDR K/RTT đã có; chưa thay cho end-to-end.
4. Sửa mô hình overlap bằng training mới rồi đóng băng trước validation mới; không khớp lại số đo đã dùng để kiểm chứng.
5. Clock 70 MHz, code/rate mới, TRNG và PA NTT phần cứng là các nhánh riêng. Giữ baseline 50 MHz và regression; không đánh dấu hoàn thành khi mới có feasibility.

## Ranh giới và các điểm cần sửa trong nhận xét cũ

- `TONG_HOP_KET_QUA_VA_KE_HOACH_ZC702.md` và bản trong bundle có các câu vượt bằng chứng: “an toàn tuyệt đối”, chuỗi tích lũy đã khép kín, ×3,48 không tăng BRAM được diễn đạt như số đo ZC702. Chưa có bằng chứng để dùng các câu đó như kết luận trên board.
- 470 kbit MODERATE, điểm giao profile, mức cải thiện f/NMS/GS từ mô hình chưa phải phép đo board được kiểm soát.
- Mã gần 0,95 không chỉ thay ROM: 24 cột/4 layer cho rate 5/6, không phải 0,95; m=256 tương ứng hai layer và rate 11/12. Cần xét lại m,d,rank và trường chọn mã.
- Cận 0 lỗi/n ở mức một phía 95% phải ghi rõ phương pháp; `1-0.05^(1/n)` là cận nhị thức chính xác khi không lỗi, không gắn nhãn Wilson cho cùng con số đó.
- `run_key_stream` dùng PE từ cơ sở X riêng, không công bố mẫu Z. Các bản CSV cũ vẫn có giới hạn PE của chúng.
- Timestamp replay dùng thời gian ảo để kiểm tra gate age; không báo như thời gian quang hay thời gian board đo được. Việc chọn/giữ block thích nghi và ngân sách composable ε vẫn cần rà soát bảo mật riêng.

## Nguồn sơ cấp cho bước rà soát toán

[Lim et al., Concise Security Bounds for Practical Decoy-State QKD](https://arxiv.org/abs/1311.7129). Việc khớp mô hình/công thức trong mã không tự chứng minh mọi giả định giao thức hiện tại thỏa điều kiện của bài báo.
