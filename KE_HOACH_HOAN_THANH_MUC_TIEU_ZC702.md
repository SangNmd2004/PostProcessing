# Chuẩn bị hoàn thành mục tiêu IR Blind Reconciliation trên ZC702

Ngày cập nhật: 26/10/2026. Phạm vi đã thống nhất: **Alice mô phỏng trên PC; đầu vào hiện có là CSV BB84 mô phỏng**. Tài liệu gốc: [Lõi IR Blind Reconciliation (Copy).md](README.md).

## 1. Kết quả mới đã hoàn thành

### Cập nhật phiên thực thi tiếp theo

- **Đã đo pha trên board, 27/10:** [36 ca UART/PS/PL](reports/zc702_profiling_20261027/REPORT.md), 288 snapshot và 1.908 dòng phase. Profiler dùng PMU Cortex-A9 và global timer, đối chiếu counter PL riêng cho IR; KEY/PA đều khớp. [PA lớn](reports/zc702_key_stream_20261027T020445Z/PROFILE_REPORT.md) đo 103 pass/1.213.835 →104.768 bit: PA calls 342,276 ms, finalize/wipe 42,179 ms. P06/PUB05 vẫn PARTIAL vì chưa đo arrival/crossover, pure RTL PA và multi-context production phases.
- **Gate xác minh dùng chung đã chạy trên board, 27/10:** [42 kiểm tra và replay TX/RX](reports/zc702_verification_budget_20261027T014110Z/REPORT.md), op20/op60 cùng cap, tag sai tính lượt, reset buffer không hoàn lượt, hết lượt chặn xác minh tiếp. Mặc định 18.446 lượt mỗi lần khởi động firmware; host chỉ được giảm cap. Còn session ID xác thực, persistence qua reset/mất nguồn và phân bổ composable epsilon; PUB04 vẫn PARTIAL.
- **P1 chức năng đã khép kín trên board với dữ liệu mô phỏng cùng phiên:** buffer sau verification → NK/NT/MT cùng block → quyết định finite-key → PA nhiều pass. [EMIT không-split](reports/zc702_key_stream_20261026T153858Z/REPORT.md): 439 block, 1.213.835 bit đầu vào → 104.768 bit đầu ra, 103 pass, tail=0. [Split→ABORT](reports/zc702_key_stream_20261026T153016Z/REPORT.md): 512 block đã thêm tổng cộng, phát prefix 1.213.835 →104.768 bit, giữ đúng 19.355 bit đuôi rồi ABORT khi đuôi xấu đủ điều kiện. Đã replay độc lập request/log, đối chiếu NTT số nguyên, đọc lại tail và kiểm tra CRC toàn bộ buffer xóa.
- **Đã đo DDR replay IR K=1/2/4:** [36 phép đo](reports/zc702_latency_20261026T155148Z/REPORT.md), ba lần/điều kiện. K=4 tăng khoảng 3,59× ở trễ reveal giả lập 1 ms và 3,74× ở 10 ms trên bốn vector lặp lại. Đây không phải thông lượng khóa bí mật, RTT mạng thực hoặc mẫu FER độc lập.
- **STA trên route hiện có:** [sweep 50/55/60/70 MHz](build/zc702/timing_trials/existing_route_frequency_sweep.csv). 70 MHz cho WNS −3,069 ns; không đạt trên route này. Chỉ đổi constraint trong bộ nhớ, không route lại, không tăng clock board hoặc thay bitstream 50 MHz.
- **FER độc lập đã đủ 10.000 trial tại một điểm:** [báo cáo và kiểm chứng raw](reports/zc702_fer_20261026T160934Z/REPORT.md), QBER BSC 3%, r23/NMS+GS: 9.998 SUCCESS, 2 DISCARD, 0 wrong codeword, không có hardware mismatch. FER=0,0002; Wilson hai phía 95% [0,00005485; 0,00072900]. Cận trên thấp hơn 10⁻³ tại điểm thử này; không suy ra toàn bộ QBER/code/policy. Phép đo không chạy tag/PA. [Receipt hoàn tất](reports/FER_LATEST_COMPLETE.json); COM3 đã được giải phóng.
- Kế hoạch công bố và đầu việc được chuẩn hóa ở [35 work items](reports/zc702_work_items.csv), [46 điều kiện dự kiến](reports/publication_experiment_matrix.csv), [ngân sách verification/FER](reports/VERIFICATION_AND_FER_BUDGET.md). Điều kiện chưa chạy vẫn ghi PLANNED/TODO.

Các kết quả dưới đây là mốc nghiệm thu trước P1 mới; giữ để truy vết.

Đã bổ sung firmware, công cụ chạy và bằng chứng thực thi trên kit, vượt ra ngoài việc lập kế hoạch:

| Hạng mục | Kết quả thực tế | Bằng chứng |
|---|---|---|
| Toàn bộ CSV với NMS ×0,75 + GS | 84/84 lượt khớp tham chiếu; 31 sửa đúng, 53 discard | [Báo cáo CSV](build/zc702/uart_runs/20261026T123153Z/REPORT.md), [CSV gộp](reports/zc702_uart_20261026T123153Z/bao_cao_gop.csv) |
| Bộ điều khiển trên ARM | Chạy hàm profile/plan/next_reveal/update trích từ driver tham chiếu; đối chiếu từng quyết định với mô hình | [Báo cáo chức năng](reports/zc702_functional_20261026T123225Z/REPORT.md) |
| EFFICIENCY / THROUGHPUT / adaptive | 21 ca/profile; tổng 63 ca gồm 39 IR sửa đúng, 18 loại sớm và 6 decoder discard | [Tổng hợp profile](reports/zc702_functional_20261026T123225Z/tong_hop.csv) |
| Trao đổi reveal theo kết quả phần cứng | PC Alice chỉ trả reveal sau phản hồi attempt; ARM quyết định số reveal dựa trên n_usc thực | [Chi tiết attempt](reports/zc702_functional_20261026T123225Z/tung_attempt.csv) |
| IRQ lõi QKD | 71/71 attempt nhận đúng một IRQ, trạng thái SUCCESS/FAIL khớp; ISR mask nguồn | [Biên bản kiểm tra thô](reports/zc702_functional_20261026T123225Z/verified_evidence.json) |
| IR → bỏ D → verification → PA | 39 KEY được đối chiếu; 38 đầu ra PA 1024 bit khớp tham chiếu; một tag cố ý sai bị từ chối, không phát PA cuối cùng | [Chi tiết phiên](reports/zc702_functional_20261026T123225Z/chi_tiet_phien.csv) |
| WAIT / EMIT / ABORT / split | 8 quyết định trên ARM khớp mô hình; đầu vào là thống kê decoy mô phỏng độc lập | [Ca decoy mô phỏng](reports/zc702_functional_20261026T123225Z/decoy_mo_phong.csv) |
| Bốn context trên board | Nạp cả bốn bank HOLD, cùng đưa vào hàng đợi; ba context sửa đúng và một discard, gắn đúng frame KEY với context | [Bốn context](reports/zc702_functional_20261026T123225Z/bon_context.csv) |

Hai lượt CSV cũ dùng OMS + puncture ngẫu nhiên được giữ nguyên. Các báo cáo đối chiếu cũ là đánh giá tại thời điểm trước các phép thử mới; dùng bảng này và các receipt liên kết để xem trạng thái hiện tại.

## 2. Cách chạy lại và nghiệm thu chức năng

Điều kiện: kit đã bật; JTAG và UART COM3 nối máy; không có terminal khác chiếm COM3; `hw_server` ở cổng 3121. Dùng bộ bitstream/XSA/BSP hiện tại đã đạt timing 50 MHz. Các lệnh dưới đây reset/nạp board như các lượt đã được thực hiện.

Chạy từ thư mục gốc dự án:

```powershell
python .\syn\zc702\run_acceptance.py --port COM3
```

Launcher lần lượt build ELF chung, tạo bộ NMS+GS từ toàn bộ CSV, chạy và xuất báo cáo CSV, rồi chạy các profile/IR→PA/IRQ/accumulator/bốn context và kiểm tra log thô. Mỗi bước phải có mã thoát 0; một bước lỗi thì dừng. Không chạy lại synthesis/implementation; các bước chạy tuần tự phù hợp máy RAM 8 GB. Launcher đã chạy trọn bảy bước và PASS tại [receipt 20261026T123115Z](build/zc702/acceptance_runs/20261026T123115Z/result.json). Bộ này không tự bao gồm các phép thử stream P1 và benchmark mới; dùng các lệnh tương ứng trong nhật ký. Luôn kiểm tra job hiện tại trước khi dùng COM3.

Chạy từng phần khi cần chẩn đoán:

```powershell
python .\syn\zc702\build_uart.py
python .\syn\zc702\run_functional_session.py --port COM3
```

Lệnh in thư mục `build/zc702/functional_runs/<UTC>/`. Xuất báo cáo bằng đường dẫn vừa nhận, ví dụ với lượt đã PASS:

```powershell
python .\syn\zc702\report_functional_session.py .\build\zc702\functional_runs\20261026T123225Z
```

Các tùy chọn `--accumulator-only` và `--multicontext-only` dùng để khoanh vùng kiểm tra. Phiên bản đầy đủ cần đủ các nhóm WEAK/MILD/MODERATE/STRONG trong CSV cho phép thử context. Mỗi lượt lưu UART thô, JTAG log, JSON tiến độ và hash firmware. ELF cũ được lưu theo hash dưới `build/zc702/uart_firmware_history/` trước build mới; bộ smoke cũ và bitstream/XSA hiện tại được giữ nguyên.

## 3. Những giới hạn cần giữ khi đánh giá

- PA/finite-key hiện đã chạy trên buffer tích lũy thật trong các lượt stream mới, nhưng đầu ra vẫn là **kiểm thử chức năng theo mô hình**, không phải khóa bí mật đã được chứng minh an toàn. ℓ được làm tròn xuống bội 64, PA nhiều lượt và chỉ trả số bit được cho phép đó.
- Alice, seed và thống kê decoy thuộc môi trường thử. Harness chức năng cũ lấy seed từ PC OS CSPRNG; stream mới dùng NumPy PCG64 công khai để tái lập. Cả hai chưa phải bằng chứng nguồn TRNG trên kit. Không suy ra entropy của nguồn quang từ các ca PASS.
- Harness CSV/profile cũ dùng mẫu 256 bit trong khóa Z và còn giới hạn leakage đó. Harness stream mới dùng X riêng cùng cửa sổ thời gian nguồn, không công bố mẫu Z. Cần rà soát bảo mật việc giữ/chọn block thích nghi, ngân sách ε và transcript trước khi tuyên bố đầu ra bí mật. Seed stream là NumPy PCG64 công khai để tái lập, khác seed OS CSPRNG của harness chức năng cũ.
- Backlog được lập trước để kiểm tra chuyển profile/hysteresis. Chưa chạy hàng đợi với nguồn vào có tốc độ thật hay đo tốc độ khóa bí mật.
- IRQ đã nhận từ lõi QKD, nhưng chờ kết quả vẫn có polling. Chưa xác nhận IRQ DMA hoặc bộ lập lịch hoàn toàn theo ngắt.
- Bốn context đã hoạt động trong phép thử nhỏ. Simple DMA không lưu TUSER trong DDR: firmware chỉ nhận một frame mỗi lần, đợi đúng một cờ SUCCESS để xác định chủ sở hữu rồi mới rearm. Có nhiều cờ thì dừng; chưa nghiệm thu tốc độ ×3,48 hoặc soak context dài hạn.

## 4. Các việc còn cần để hoàn tất phạm vi chức năng rộng hơn

| Ưu tiên | Công việc cụ thể | Điều kiện nghiệm thu |
|---|---|---|
| P1 | Đã nối buffer/counts; còn rà soát bảo mật transcript, adaptive selection và ε toàn phiên | Giữ bằng chứng chức năng mới; không suy từ khớp mô hình thành chứng nhận an toàn |
| P1 | Đã chạy EMIT/ABORT/split nhiều pass; còn mở rộng fault injection, giới hạn verification và sản xuất | Chặn xuất khi tag/seed/DMA lỗi; kiểm tra thêm ca biên, overflow và khôi phục lỗi |
| P1 | Đã dùng phiên mô phỏng thống nhất trong `data/sessions`; còn xác minh giả định với nguồn nghiên cứu | Hash nguồn/counts/time window khớp; replay clock ảo phải tách thời gian quang và thời gian đo |
| P2 | Chạy soak context/DMA và các ca hỏng/mất gói/timeout | Không gán sai buffer/context, không xuất khóa sau lỗi; đủ ca context retry/discard và thu hồi buffer |
| P2 | Đo thời gian xử lý, IRQ DMA và throughput ở RTT xác định | Tách UART truyền dữ liệu, IR compute, chờ Alice, verification và PA; có log thời gian/counter; không dùng thời gian mô phỏng làm số đo board |
| P2 | Thử implementation 70 MHz trong workspace riêng | Setup/hold/clock/DRC đạt; bit/XSA/BSP/ELF khớp; chạy lại đầy đủ nghiệm thu. Nếu không đạt, ghi đúng giới hạn 50 MHz và tối ưu đường găng |
| P2 | FER trên ít nhất 10⁴ block độc lập, theo từng QBER/cấu hình | Tách discard, codeword sai bị tag bắt, lỗi truyền và lỗi phần cứng; không tính bản sao/chồng lặp làm mẫu độc lập |
| P3 | Nguồn seed vật lý và kênh Alice/Bob xác thực | Có thiết bị/giao thức cụ thể và kiểm tra độc lập; không dùng CRC32 để thay xác thực |

Các mục cần nguồn thực chỉ có thể nghiệm thu thực tế khi có dữ liệu/phần cứng bổ sung. Với phạm vi hiện tại, có thể chuẩn bị và kiểm chứng mô phỏng chức năng, không đánh dấu đã xác nhận an toàn hệ QKD thực.

## 5. Các hướng nghiên cứu trong mục 10 của tài liệu gốc

Đây là các thay đổi kiến trúc/nghiên cứu được đề xuất, không phải chức năng đã tồn tại và chỉ cần bật lên. Giữ riêng chúng trong bảng nghiệm thu để không nhầm với port lõi hiện tại.

| Hướng | Việc cần chuẩn bị trước khi triển khai | Tiêu chí đánh giá |
|---|---|---|
| Code dài 6144–12288 bit, giữ 128 lane | Ma trận mới, ROM/lịch layer, kích thước RAM/buffer và vector mới | Giảm f trên cùng điều kiện; đúng mô hình; tài nguyên/timing sau route; thử lại trên board |
| Thêm rate khoảng 0,95 và 0,40 | Thiết kế code, mở trường chọn code/ROM nếu cần, tái sinh bảng puncture | Cửa sổ QBER mở rộng, f/FER được đo; không chỉ thay hằng số rate |
| Kiểm thử mạch, UART và tích hợp SoC | ZC702 UART/PS/DMA đã có bằng chứng | Chỉ tiếp tục trên Zynq-7000 theo phạm vi dự án |
| PA lớn 10⁷–10⁸ bit qua NTT/MMH-MH | Thiết kế riêng datapath, bộ nhớ DDR, seed và giao thức đa pass | Bit-exact với mô hình, footprint và thời gian thực đo trên kit |
| Syndrome encoder FPGA phía Alice | Chọn giao diện, dùng lại ROM/shifter, tạo vector đối chiếu | Syndrome khớp mô hình với cả bốn mã; tích hợp hai phía |
| FER ≥10⁴ block | Bộ dữ liệu độc lập và runner soak | Như gate FER ở mục 4 |
| Cải thiện phần quang/decoy | Cần bộ thu/phát, nguồn dữ liệu và phép đo thực | Nằm ngoài khả năng xác nhận từ CSV hiện có |
| Tăng clock/shifter/ràng buộc vị trí | Profiling đường găng trên Zynq, thay đổi ở branch/workspace riêng | Timing sau route và functional regression đều đạt |

## 6. Cách đọc trạng thái nghiệm thu

Không dùng tỷ lệ phần trăm “hoàn thành dự án” khi các mục có quy mô khác nhau. Mỗi mục cần có: trạng thái `PASS_FUNCTIONAL_BOARD`, `PASS_SYNTHETIC_METADATA`, `PARTIAL` hoặc `TODO`, bằng chứng, giới hạn và gate còn thiếu. Bảng máy đọc được nằm tại [reports/zc702_acceptance_status.csv](reports/zc702_acceptance_status.csv).
