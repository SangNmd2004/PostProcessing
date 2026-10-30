# Tự tổng hợp QKD PostProcessing cho ZC702

Đích: **XC7Z020-1CLG484C**, tên part trong Vivado: **xc7z020clg484-1**.
Top IP: **qkd_pp_axi**. Tham số hiện tại: ZC = 128, SH_W = 7, CTX_W = 2 (4 ngữ cảnh).

Đây là hướng dẫn kiểm tra riêng IP. Phần tích hợp ZC702 PS + DMA nằm tại [syn/zc702/README.md](syn/zc702/README.md); tổng hợp riêng IP thành công chưa chứng minh hệ thống chạy trên board.

## 1. Cách nhanh: chạy script đã chuẩn bị

Mở PowerShell, chạy đúng hai lệnh sau:

```powershell
Set-Location -LiteralPath 'C:\Users\Admin\Downloads\PostProcessing\PostProcessing\artifacts\review_zc702_20261026'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_synth_8gb.ps1
```

Script đã chỉnh cho máy RAM 8 GB: chạy Vivado batch với tối đa **2 luồng**, dùng directive **RuntimeOptimized**, đọc bảy file RTL gốc và tổng hợp out-of-context cho ZC702 ở mục tiêu 70 MHz. Chỉ ghi checkpoint và báo cáo tài nguyên tổng; báo cáo hierarchy/timing được chuyển sang một phiên Vivado riêng. Không cần cắm kit khi tổng hợp.

`RuntimeOptimized` giảm một số bước tối ưu RTL/timing để giảm thời gian xử lý. Đây không phải giới hạn cứng RAM: chưa đo mức RAM đỉnh của một lượt hoàn tất, và tài nguyên/timing FPGA có thể khác directive mặc định. Giữ nguyên ZC = 128, 4 ngữ cảnh và độ trễ RAM. Không ép toàn bộ RAM vào BRAM hoặc bỏ các tối ưu diện tích chỉ để giảm tải máy.

Ưu tiên lệnh batch ở trên; đóng Vivado GUI, trình mô phỏng và các ứng dụng nặng trước khi chạy. Mỗi lần chỉ chạy một tác vụ Vivado. Launcher chỉ thông báo RAM trống; nó không tự đóng ứng dụng hoặc sửa pagefile của Windows. Nếu Windows đang tắt pagefile, nên bật chế độ tự quản lý; pagefile không thay thế RAM và có thể làm build chậm.

Kết quả mặc định nằm trong **`artifacts/review_zc702_20261026/low_memory/`**. Launcher cũng đặt thư mục làm việc tại đó để gom file tạm/log. `ExecutionPolicy Bypass` chỉ áp dụng cho tiến trình PowerShell được gọi trong lệnh, không đổi chính sách hệ thống.

Chờ Vivado thoát và kiểm tra **cả mã thoát lẫn báo cáo**, không chỉ một dòng `done synthesizing module` ở giữa log:

```powershell
$LASTEXITCODE
Get-Content .\low_memory\vivado_synth.log -Tail 30
Select-String -Path .\low_memory\vivado_synth.log -Pattern '^ERROR:', 'ZC702_REVIEW_SYNTH_DONE'
```

Điều kiện lượt tổng hợp hoàn tất: mã thoát 0, không có lỗi, có `ZC702_REVIEW_SYNTH_DONE`, có checkpoint và báo cáo tài nguyên tổng mới. Script có thể ghi đè kết quả lần chạy trước; kiểm tra thời gian cập nhật của file để tránh đọc báo cáo cũ.

| File | Nội dung cần xem |
|---|---|
| `utilization_synth.rpt` | Tổng LUT, FF, RAMB18/RAMB36, DSP |
| `utilization_hier_synth.rpt` (tùy chọn) | Tài nguyên theo từng khối decoder, PA, RAM |
| `timing_synth.rpt` (tùy chọn) | Timing ước tính sau tổng hợp, các đường chưa ràng buộc |
| `qkd_pp_axi_synth.dcp` | Checkpoint để mở lại bằng Vivado |
| `vivado_synth.log` | Lỗi, cảnh báo, kết quả suy diễn RAM |

Sau khi synthesis hoàn tất và tiến trình Vivado đã thoát, tạo báo cáo chi tiết bằng một phiên riêng:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_synth_8gb.ps1 -ReportsOnly
```

Muốn đối chiếu với directive mặc định, chạy **sau khi lượt trước đã thoát**, vẫn giữ tối đa 2 luồng:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_synth_8gb.ps1 -Profile quality
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_synth_8gb.ps1 -Profile quality -ReportsOnly
```

Kết quả này nằm trong `quality/`, không ghi đè `low_memory/`. Chỉ chạy nếu còn đủ RAM. Hai chế độ đều chưa place-and-route. Nếu build vẫn thiếu RAM, cần xem bước dừng và peak memory trong log trước khi quyết định tách tổng hợp theo module; không hạ ZC/CTX tùy ý vì model, ROM, vector và firmware phải khớp nhau.

Mở checkpoint trong Vivado GUI bằng **File → Checkpoint → Open**, hoặc tại Tcl Console của một phiên Vivado chưa mở project:

```tcl
open_checkpoint {C:/Users/Admin/Downloads/PostProcessing/PostProcessing/artifacts/review_zc702_20261026/low_memory/qkd_pp_axi_synth.dcp}
report_utilization
report_timing_summary
```

Nếu chạy script ngay trong GUI, dùng một phiên Vivado chưa mở project và nhập (máy 8 GB nên ưu tiên batch):

```tcl
source {C:/Users/Admin/Downloads/PostProcessing/PostProcessing/artifacts/review_zc702_20261026/synth_zc702.tcl}
```

Không chạy hai lượt vào cùng thư mục kết quả đồng thời.

## 2. Tự tạo project bằng GUI

1. **Create Project → RTL Project**. Chọn một thư mục project mới, ví dụ `vivado_zc702`, bên trong workspace.
2. Add Sources: thêm đúng bảy file sau. Không thêm testbench, firmware C, netlist của nền tảng khác hay wrapper đánh giá PnR.

```text
rtl/ldpc/ldpc_sdp_ram.v
rtl/ldpc/qc_cyclic_shifter.v
rtl/ldpc/ldpc_code_rom.v
rtl/ldpc/ldpc_ir_decoder.v
rtl/top/qkd_ir_core.v
rtl/pa/pa_hankel_hash.v
rtl/top/qkd_pp_axi.v
```

3. Add Constraints: thêm `artifacts/review_zc702_20261026/qkd_zc702.xdc`. Chỉ dùng constraint của ZC702.
4. Default Part: chọn **Parts**, tìm **xc7z020clg484-1**. Không bắt buộc phải cài board file ZC702 nếu chọn đúng part trực tiếp.
5. Trong Sources, nhấp phải **qkd_pp_axi → Set as Top**. Giữ nguyên các tham số mặc định.
6. Trong Tcl Console nhập `set_param general.maxThreads 2` và `set_property STEPS.SYNTH_DESIGN.ARGS.DIRECTIVE RuntimeOptimized [get_runs synth_1]`. Khi launch chỉ chạy **1 job** (một tác vụ, tối đa hai luồng). **Run Synthesis**, chờ hoàn tất, rồi mở báo cáo khi đủ RAM. GUI không tự áp dụng cấu hình từ script nếu bạn chỉ bấm Run Synthesis.

Lưu ý: luồng GUI thông thường tổng hợp top như một module có các cổng ngoài; kết quả có thể khác lượt out-of-context của script. Với đánh giá riêng IP, ưu tiên script. Chưa chạy Generate Bitstream trực tiếp cho top AXI này: các bus AXI phải nối bên trong hệ thống, không đưa tất cả thành chân I/O của kit.

## 3. Đọc báo cáo và quyết định bước tiếp

XC7Z020 có 53.200 LUT, 106.400 FF, 140 block RAM 36 Kb tương đương 280 block RAM 18 Kb, và 220 DSP. Hai loại RAM chia sẻ cùng tài nguyên vật lý: không cộng chúng như hai ngân sách độc lập.

- **LUT/FF/RAM vượt giới hạn:** cấu hình đó chưa vừa. Cần xác định khối chiếm nhiều tài nguyên trước khi thay đổi kiến trúc.
- **LUT/FF/RAM còn chỗ:** mới cho thấy khả năng chứa IP sau tổng hợp. Cần chừa tài nguyên cho DMA, interconnect, FIFO và IRQ của hệ thống.
- **WNS âm sau synthesis:** timing ước tính chưa đạt 70 MHz, cần kiểm tra đường găng. Đây chưa phải kết quả sau route.
- **WNS dương sau synthesis:** vẫn cần place-and-route toàn hệ thống và kiểm tra setup/hold, clock, đường chưa ràng buộc.

Giữ nguyên độ trễ RAM của baseline: APP/C2V 2 chu kỳ, các RAM còn lại 1 chu kỳ. Khi thử thay đổi suy diễn BRAM, dùng build riêng và đối chiếu RAMB/LUTRAM, timing cùng vector RTL trước khi tích hợp.


## 4. Tích hợp hệ thống và chạy kit

**Trạng thái mới nhất:** đã chạy NMS+GS trên toàn bộ CSV và bổ sung bộ điều khiển ARM, IR→xác minh→PA, IRQ QKD, quyết định accumulator mô phỏng và phép thử bốn context. Xem [kế hoạch nghiệm thu toàn bộ mục tiêu](KE_HOACH_HOAN_THANH_MUC_TIEU_ZC702.md) và [báo cáo chức năng mới](reports/zc702_functional_20261026T123225Z/REPORT.md). Các kết quả CSV bên dưới là lịch sử các lượt trước.

Lượt chạy lại **toàn bộ dữ liệu BB84 gốc**: 100/100 dòng, đủ 49.505 vị trí bit Alice/Bob với cả bốn mã, không thêm lỗi nhân tạo. Ghép thành 21 block, chạy 84 lượt qua UART: 84 khớp tham chiếu, 31 sửa đúng và 53 discard. [Đối chiếu 100 dòng CSV](reports/zc702_uart_20261026T115803Z/doi_chieu_tung_dong_csv.csv), [chi tiết block](reports/zc702_uart_20261026T115803Z/chi_tiet_block.csv), [thống kê tổng hợp](reports/zc702_uart_20261026T115803Z/tong_hop.csv). Kết quả sửa lỗi là của block ghép, không phải kiểm thử độc lập từng dòng ngắn.

**Đã bổ sung truyền dữ liệu qua UART:** firmware chung nhận bộ vector mới mà không build lại ELF theo dữ liệu. Lượt test CSV/QBER trên kit đạt **243/243 kết quả khớp tham chiếu** (có các trường hợp discard đúng dự kiến). Xem [hướng dẫn UART](firmware/zc702_uart/README.md) và [báo cáo CSV/QBER](build/zc702/uart_runs/20261026T114819Z/REPORT.md).

**Đã hoàn tất và chạy PASS trên ZC702 thật ngày 2026-10-26:** PS7 + QKD + 4 AXI DMA ở 50 MHz, nạp qua JTAG, thu UART COM3/115200. Chín khối IR (gồm retry/discard theo vector) và một lượt PA 4096 bit đầu vào → 1024 bit đầu ra đều đạt kiểm tra vector chuẩn. Firmware kiểm tra từng word KEY/PA, trạng thái, số vòng lặp, ERRCNT và lỗi DMA. Phạm vi board test là context 0, polling; chưa xác nhận chạy đồng thời bốn context, IRQ, thông lượng hay độ bền dài hạn.

Kết quả sau route của bản đã sửa reset: **38.059 LUT (71,54%), 29.577 FF (27,80%), 42 BRAM tile (30%), 0 DSP**; setup WNS **+2,645 ns**, hold WHS **+0,007 ns**. Cả hai đều không có tổng slack âm. Lỗi auxiliary reset giữ PL trong reset đã được sửa; bản lỗi được lưu riêng với tên `INVALID_AUX_RESET`, không dùng để nạp.

Bằng chứng: [UART board thật](build/zc702/board_runs/20261026T113309Z/uart.log), [kết quả JSON](build/zc702/board_runs/20261026T113309Z/result.json), [manifest và SHA256 bit/XSA/ELF](build/zc702/bundle_manifest.json). Hướng dẫn build toàn hệ thống tại [syn/zc702/README.md](syn/zc702/README.md).

Để chạy lại từ thư mục gốc dự án, bật kit, giữ kết nối JTAG/UART và đóng phần mềm khác đang mở COM3. Lệnh sau **reset và nạp lại board**, sau đó lưu log mới:

```powershell
python .\syn\zc702\run_board_test.py --port COM3
python .\syn\zc702\verify_bundle.py
```

Các lưu ý kiến trúc bên dưới giải thích cách tích hợp đã thực hiện và giới hạn của driver tham chiếu gốc.

Sau khi IP vừa tài nguyên, tạo Block Design gồm Zynq PS7 dùng cấu hình board ZC702; nối M_AXI_GP0 tới AXI-Lite của IP và thanh ghi DMA; nối các master đọc/ghi DDR của DMA tới S_AXI_HP; nối clock, reset và IRQ phù hợp. IP có **bốn luồng vào, hai luồng ra**: CH, SYN, PA_X, PA_SEED; KEY, PA_Y. Một AXI DMA thông thường chỉ cung cấp một kênh MM2S và một kênh S2MM, nên cần nhiều kênh/DMA hoặc mạch ghép luồng có điều khiển phù hợp.

Các luồng CH/SYN/PA_X/PA_SEED đếm độ dài cố định và không có cổng TLAST đầu vào. KEY/PA_Y có TLAST đầu ra; cần cấu hình DMA và TKEEP/độ rộng tương ứng. Hai nguồn PA_X và PA_SEED phải được phục vụ đồng thời khi PA chạy.

Firmware hiện là mã tham chiếu, còn nhiều hàm DMA/kênh Alice/TRNG khai báo `extern`. Đặc biệt, driver một khối đang chờ SUCCESS rồi mới gọi nhận KEY, trong khi RTL chỉ phát SUCCESS **sau khi đã chuyển hết KEY**. Khi tích hợp phải chuẩn bị DMA nhận KEY trước khi giải mã/RETRY, nếu không có thể chờ nhau vô hạn. Driver nhiều ngữ cảnh cũng cần kiểm tra việc gắn đúng context với buffer KEY hoàn tất.

Luồng tích hợp đã hoàn tất implementation, kiểm tra timing/DRC, tạo bitstream và XSA, build ứng dụng ARM với BSP khớp XSA, rồi so sánh KEY/PA trên board với vector chuẩn. Firmware test riêng nằm tại `firmware/zc702/smoke_main.c`; kết quả PASS ở trên dùng dữ liệu tổng hợp và seed PA công khai, chưa chứng minh phiên QKD thực hay chất lượng nguồn ngẫu nhiên.

## Trạng thái kiểm tra ngày 2026-10-26

Đã đọc cấu trúc RTL, AXI, RAM, driver và luồng tổng hợp IP; đã biên dịch kiểm tra cú pháp driver bằng compiler ARM Cortex-A9 của Vitis 2020.2 với `-Wall -Wextra -Werror`, không có lỗi cú pháp. Kiểm tra này không link BSP và không chạy firmware.

Lượt tổng hợp Vivado/XSim đầu tiên được khởi động trong quá trình review trước khi chuyển sang hướng dẫn tự chạy chưa hoàn tất; các log dở có thể còn trong thư mục artifacts. Sau đó người dùng đã hoàn tất lượt IP với 2 luồng: 33.567 LUT (63,10%), 21.905 FF (20,59%), 33 BRAM tile (23,57%); WNS sau synthesis +6,992 ns ở mục tiêu 70 MHz, peak memory theo log 2.016,203 MB khi lưu checkpoint. Đây là kết quả riêng IP, chưa phải timing sau route hoặc board PASS. Báo cáo hiện tại nằm trong `artifacts/review_zc702_20261026/low_memory/`.

Tài liệu đối chiếu: [AMD ZC702 UG925](https://docs.amd.com/api/khub/documents/K98SWD9m_vdVh4yryJI46w/content), [Vivado RAM inference UG901](https://docs.amd.com/r/2022.2-English/ug901-vivado-synthesis/Simple-Dual-Port-Block-RAM-Examples).

Tham khảo cấu hình giảm tải: [AMD UG901 về số luồng synthesis](https://docs.amd.com/r/2024.1-English/ug901-vivado-synthesis/Multi-Threading-in-RTL-Synthesis), [ý nghĩa RuntimeOptimized](https://docs.amd.com/r/2023.2-English/ug901-vivado-synthesis/Using-Synthesis-Settings).

Kiểm tra ban đầu của cấu hình RAM 8 GB dùng 1 luồng được lưu tại `artifacts/review_zc702_20261026/config_check.log`. Sau đó đã tăng lên **2 luồng** theo yêu cầu và hoàn tất synthesis IP, implementation toàn hệ thống và board test như ghi ở trên. Script `check_synth_config.tcl` cũng đã cập nhật để kiểm tra giới hạn 2 luồng. Mức peak memory 2.016,203 MB được nêu ở trên chỉ thuộc lượt synthesis IP, không phải mức RAM tối đa của toàn bộ luồng implementation.
