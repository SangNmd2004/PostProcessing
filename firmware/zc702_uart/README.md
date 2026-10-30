# Truyền dữ liệu kiểm thử qua UART ZC702

## Đo pha bằng PMU/global timer, 27/10/2026

[Báo cáo profiler](../../reports/zc702_profiling_20261027/REPORT.md) có 36 ca trên bốn code, 288 snapshot và 1.908 dòng phase; đồng thời đã đo PA trên buffer 1.213.835 bit qua 103 pass. Tất cả KEY/PA và log counter đã được replay độc lập. Profiler mặc định tắt, không thay bitstream/clock PL 50 MHz.

Op74 `[74,1]` bật profiler, bật CCNT của ARM với divider tắt và xóa lịch sử; `[74,0]` tắt và giữ lịch sử. Không bật/tắt khi block IR hoặc chế độ MC còn hoạt động. Op75 `[75,0xffffffff]` đọc metadata; `[75,index]` đọc một snapshot. Lưu tối đa 64 lệnh, có chỉ báo dropped; hai lệnh 74/75 không tự ghi vào lịch sử. Profiler in dữ liệu sau phép đo, ghi cả counter 64 bit của global timer và tổng các delta CCNT 32 bit hợp lệ. Span dài có nguy cơ wrap được đánh dấu invalid cho PMU, vẫn giữ global ticks.

```powershell
python .\syn\zc702\run_phase_profile.py --port COM3 --repeats 3
python .\syn\zc702\report_phase_profile.py .\build\zc702\phase_profile_runs\20261027T015821Z
python .\syn\zc702\plot_phase_profile.py .\reports\zc702_phase_profile_20261027T015821Z
python .\syn\zc702\run_key_stream.py --port COM3 --scenario emit --profile-emit
```

Thay đường dẫn bằng run vừa tạo. Với EMIT, chạy `report_key_stream.py <run>` trước rồi `report_stream_profile.py <run>`; verifier counter yêu cầu proof chức năng khớp raw result. Profiler EMIT bật sau ingest, đo decision/seed/PA/output rồi đọc lịch sử; không dùng timestamp replay để tính thời gian board.

Phase parent/child và FAIL→REVEAL chồng lấp, không cộng trùng. PA/verification call gồm cache/DMA, chưa phải pure RTL PA latency. RX/ACK wall span bao gồm chờ host/USB; host sleep không phải network RTT. Workload đọc KEY và gửi expected PA để kiểm chứng, chưa đại diện giao thức sản phẩm hoặc throughput khóa bí mật. Các code dùng fixture khác nhau nên bảng này không phải ablation rate.

## Giới hạn xác minh tag, 27/10/2026

Đã thêm bộ đếm dùng chung cho op20 và op60: mặc định 18.446 lượt trong một lần khởi động firmware; tính cả tag sai và lượt hash đã bắt đầu nhưng DMA báo lỗi. Reset controller/accumulator/buffer không hoàn lại lượt. Op72 `[72, cap]` chỉ được giảm cap, cap không nhỏ hơn số đã dùng và không đổi khi block IR còn hoạt động; op73 `[73]` đọc used/limit/remaining. Hết ngân sách thì chặn trước khi chạy hash, xóa staging input và không append/phát PA mới.

[42 kiểm tra board và replay log](../../reports/zc702_verification_budget_20261027T014110Z/REPORT.md) đã PASS, gồm tag đúng/sai ở cả hai đường và reset không hoàn lượt. Chạy lại bằng `python .\syn\zc702\run_verification_budget.py`; xuất báo cáo bằng `report_verification_budget.py <run>`.

Đây là gate kỹ thuật theo **vòng đời firmware**, chưa phải ngân sách phiên xác thực bền vững: reset CPU/nạp ELF/mất nguồn khởi tạo lại counter. Còn phải gắn session ID, lưu trạng thái và phân bổ epsilon đầy đủ. Seed vẫn là fixture công khai, chưa có chứng nhận an toàn QKD.

## Cập nhật stream, benchmark và FER ngày 26–27/10/2026

Firmware đã nối khóa sau IR và tag với buffer DDR, thống kê decoy cùng block, quyết định finite-key và PA nhiều pass trong PL. Hai phiên mô phỏng đã kiểm chứng độc lập: [EMIT 1.213.835 → 104.768 bit](../../reports/zc702_key_stream_20261026T153858Z/REPORT.md) và [split giữ tail rồi ABORT](../../reports/zc702_key_stream_20261026T153016Z/REPORT.md). Alice/decoy/seed là dữ liệu kiểm thử mô phỏng; chưa chứng nhận an toàn QKD. Các giới hạn “chưa nối PA” ở phần giao thức v1 bên dưới là lịch sử của runner v1.

Chạy từ workspace gốc, chỉ một chương trình chiếm COM3. Dùng ELF hiện tại khớp manifest; chỉ build lại khi thay mã/ABI. Mỗi lệnh sau tự tạo run mới, reset/nạp board qua JTAG và lưu bằng chứng riêng:

```powershell
python .\syn\zc702\run_key_stream.py --port COM3 --scenario smoke
python .\syn\zc702\run_key_stream.py --port COM3 --scenario emit
python .\syn\zc702\run_key_stream.py --port COM3 --scenario split
python .\syn\zc702\run_latency_benchmark.py --port COM3
python .\syn\zc702\run_fer_campaign.py --port COM3 --trials 10000 --qber .03 --code r23 --seed-base 2000000
```

Các dòng là các phép thử độc lập, chạy tuần tự theo mục tiêu cần kiểm tra. Đổi seed-base để tạo cohort mới; không gộp rerun cùng seed thành mẫu độc lập. EMIT/split dùng thời gian replay ảo, không dùng thời gian đó làm throughput quang. PA dùng lõi Hankel hiện tại; NTT số nguyên trên PC chỉ là oracle.

Nhóm lệnh functional magic `0x51465532`: 60–69 quản lý stream/seed/output/wipe, 70 nạp vector DDR, 71 đo scheduler K=1/2/4, 72–73 quản lý cap xác minh theo vòng đời firmware. Command 68 đọc buffer chỉ phục vụ kiểm thử công khai, phải bỏ/khóa trong bản sản phẩm. CRC32 bảo vệ truyền dữ liệu, không xác thực Alice. Ngân sách composable theo phiên qua nhiều lần reset vẫn chưa được cưỡng chế.

Đã đo [36 phép K/RTT](../../reports/zc702_latency_20261026T155148Z/REPORT.md) và [10.000 input BSC độc lập](../../reports/zc702_fer_20261026T160934Z/REPORT.md): 9.998 sửa đúng, 2 discard, 0 wrong codeword tại q=3%/r23/NMS+GS. Benchmark K/RTT dùng bốn vector lặp lại, loại UART/PA khỏi timing; FER không chạy tag/PA. Không cộng hai workload thành số mẫu FER.

Sau run, dùng các verifier tương ứng với đường dẫn vừa in:

```powershell
python .\syn\zc702\report_key_stream.py .\build\zc702\key_stream_runs\20261026T153858Z
python .\syn\zc702\verify_experiment_run.py latency .\build\zc702\latency_runs\20261026T155148Z
python .\syn\zc702\verify_experiment_run.py fer .\build\zc702\fer_runs\20261026T160934Z
```

FER runner đã tự chạy verifier khi hoàn tất. Nếu run dừng giữa chừng, đọc lỗi trước khi `--resume`; giữ model, firmware, args và seed đúng cohort. Xem [nhật ký và thứ tự tiếp tục](../../reports/EXECUTION_TRACKER.md).

## Cập nhật: nghiệm thu chức năng theo tài liệu IR Blind Reconciliation

Đã bổ sung vòng tương tác trực tuyến: ARM chọn profile/code/r0/reveal; PC mô phỏng Alice; KEY từ DMA được bỏ D rồi dùng lõi PA FPGA để kiểm tra tag và tạo hash. Đã chạy 63 ca profile, 71 IRQ lõi QKD, 38 PA khớp, một tag sai bị từ chối, 8 quyết định decoy mô phỏng và phép thử bốn context. Xem [kế hoạch và các gate còn thiếu](../../KE_HOACH_HOAN_THANH_MUC_TIEU_ZC702.md), [báo cáo lượt kết hợp](../../reports/zc702_functional_20261026T123225Z/REPORT.md).

```powershell
python .\syn\zc702\run_acceptance.py --port COM3
```

Lệnh nghiệm thu chức năng chạy các bước tuần tự; không tổng hợp lại FPGA. Firmware nhận thêm command chức năng qua magic `0x51465532`; giao thức vector v1 bên dưới vẫn được hỗ trợ. **Giới hạn PA chỉ chạy vector chuẩn ở phần hướng dẫn cũ bên dưới thuộc các lượt test cũ.** Luồng chức năng mới đã chạy IR→PA từng block, nhưng chưa xuất buffer khóa tích lũy theo finite-key và chưa có bằng chứng QKD an toàn từ thiết bị thực.

Firmware chung nhận vector mới qua UART COM3, 115200 baud. Không nhúng từng bộ CSV vào ELF. JTAG chỉ dùng nạp bitstream/ELF và khởi động CPU; channel, syndrome, reveal và kết quả tham chiếu của mọi khối đều truyền qua UART. Khối LDPC dài 3072 bit: 2765 bit khóa + 307 vị trí puncture. Chạy context 0, polling, PS DDR qua DMA HP0, PL 50 MHz.

## Kết quả đã chạy trên kit ngày 2026-10-26

**243/243 lượt phần cứng khớp tham chiếu**, gồm 9 vector hồi quy, 84 lượt từ CSV (21 khối × 4 mã) và 150 lượt QBER có kiểm soát (15 mức × 10 mẫu). Đã dùng toàn bộ 49.505 vị trí bit Alice/Bob của 100 dòng CSV; khối cuối mỗi nhóm chồng lên khối trước để dùng hết phần dư. Các lượt chồng lặp/thử lại mã không phải mẫu độc lập.

Trong phép quét có chọn mã theo QBER: các mức 0–8% đều sửa đúng 10/10 mẫu, mức khoảng 10% sửa đúng 5/10, các mức 12%, 15%, 18%, 20% đều discard. Đây là kết quả tập thử này, chưa phải ngưỡng QBER bảo đảm. Gói sai CRC được từ chối trước khi chạy QKD.

- [Báo cáo và bảng theo QBER/mã](../../build/zc702/uart_runs/20261026T114819Z/REPORT.md)
- [Log UART thô](../../build/zc702/uart_runs/20261026T114819Z/uart.log)
- [Kết quả từng lượt](../../build/zc702/uart_runs/20261026T114819Z/blocks.csv)
- [Biên bản kiểm tra độc lập log thô](../../build/zc702/uart_runs/20261026T114819Z/verified_evidence.json)

## Chạy lại bộ dữ liệu đã chuẩn bị

Từ thư mục gốc dự án, bật kit và nối JTAG/UART; đóng terminal khác đang chiếm COM3. Giữ `hw_server` ở cổng 3121 như phiên hiện tại. Nếu cần khởi động lại server, chạy launcher Xilinx `D:\Xilinx\Vivado\2020.2\bin\hw_server.bat -s tcp::3121` trong một terminal riêng.

```powershell
python .\syn\zc702\run_uart_campaign.py --port COM3
```

Lệnh kiểm tra hash bộ phần cứng, BSP và ELF, reset/nạp board một lần, gửi dữ liệu UART và ghi bằng chứng vào `build/zc702/uart_runs/<UTC>/`. Nó dừng ở lỗi truyền, mismatch, DMA error hoặc timeout; kết quả từng lượt được lưu ngay. `hardware_match` nghĩa là phần cứng khớp tham chiếu, bao gồm discard đúng dự kiến; `model_outcome=SUCCESS` mới là sửa đúng khóa Alice. `ERRCNT` chỉ có nghĩa sau hội tụ, giá trị thanh ghi cũ khi discard được lưu riêng.

Sau khi chạy xong, đối chiếu log bằng lệnh với đường dẫn mới vừa in:

```powershell
python .\syn\zc702\report_uart_campaign.py .\build\zc702\uart_runs\20261026T114819Z
```

## Thay CSV hoặc tăng số mẫu QBER

Để chỉ chạy toàn bộ CSV gốc, thử cả bốn mã, không thêm baseline hay lỗi nhân tạo, dùng `--native-only`. Đã chạy đủ 100 dòng trong [lượt 20261026T115803Z](../../build/zc702/uart_runs/20261026T115803Z/REPORT.md). [Bảng đối chiếu từng dòng](../../reports/zc702_uart_20261026T115803Z/doi_chieu_tung_dong_csv.csv) kiểm tra đủ từng vị trí bit với từng mã. Từng dòng ngắn vẫn ghép với các dòng cùng nhóm thành block 2765 bit; bảng này không gán kết quả sửa riêng cho dòng khi chỉ một block chứa nó bị discard.

```powershell
python .\syn\zc702\generate_uart_campaign.py --native-only --out .\build\zc702\uart_csv_all_100_new
python .\syn\zc702\run_uart_campaign.py --port COM3 --campaign .\build\zc702\uart_csv_all_100_new\campaign.json
```

Không cần build lại ELF cho dữ liệu mới. Chọn thư mục output mới để không ghi đè bộ vector đã có bằng chứng. Ví dụ tăng từ 10 lên 30 mẫu mỗi mức QBER:

```powershell
python .\syn\zc702\generate_uart_campaign.py --csv .\Test\bb84_key_test_Sim_20260618_002028.csv --out .\build\zc702\uart_campaign_30 --repeats 30
python .\syn\zc702\run_uart_campaign.py --port COM3 --campaign .\build\zc702\uart_campaign_30\campaign.json
```

Generator dùng mô hình Python để tính syndrome, retry/reveal và khóa tham chiếu; đây là bước chuẩn bị trên PC. Nó kiểm tra bitstring, độ dài, mismatch và QBER của CSV. Dữ liệu gốc thử cả bốn mã; phần quét giữ khóa Alice từ CSV, tạo Bob bằng đảo bit và chọn mã theo `model/eval_csv.py`. Seed và QBER thực được ghi lại. CSV chỉ được đọc. Không chạy lại synthesis/Vivado implementation.

## Build firmware chung khi sửa chương trình

Chỉ cần bước này khi thay đổi firmware/protocol, hoặc chưa có ELF UART. Cần bộ bit/XSA và BSP đã build theo [hướng dẫn hệ thống](../../syn/zc702/README.md).

```powershell
python .\syn\zc702\build_uart.py
```

Kết quả nằm tại `build/zc702/uart_firmware/qkd_uart.elf`, kèm `build.log` và manifest hash. Build dùng GCC Cortex-A9 với `-Wall -Wextra -Werror`, BSP/linker script khớp XSA; giữ nguyên ELF smoke cũ. Script sinh `uart_main.c` từ các hàm DMA/test đã kiểm chứng trong `firmware/zc702/smoke_main.c`, thay main bằng `service.h`. Channel/syndrome/RX được sao chép vào buffer căn 64 byte, flush/invalidate cache như smoke test.

## Giao thức v1 và giới hạn

Header little-endian gồm 4 word: magic `0x51564431`, sequence, số word payload, CRC32 payload. Tối đa 4096 word. Firmware xác nhận header, nhận từng đoạn tối đa 128 byte rồi ACK offset; chỉ chạy QKD khi CRC và giới hạn cấu trúc hợp lệ. Payload chứa cfg/cfg2, pre-reveal, attempts, kích thước syndrome, ERRCNT tham chiếu, số reveal; tiếp theo là expected status, reveal counts, 192 word channel, syndrome, reveal và 48 word KEY 64 bit tham chiếu. Payload rỗng với CRC=0 kết thúc phiên. CRC32 chỉ phát hiện lỗi truyền, không phải xác thực bảo mật.

PA chạy một vector chuẩn 4096 → 1024 bit lúc khởi động; **chưa nối PA với khóa CSV vừa sửa**. Không suy ra khóa bí mật an toàn chỉ từ việc IR sửa đúng. Chưa kiểm thử nhiều context đồng thời, IRQ, thông lượng hay soak dài hạn. CSV nguồn là dữ liệu mô phỏng BB84.
