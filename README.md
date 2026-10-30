# QKD PostProcessing trên Xilinx ZC702

Đích phần cứng: Zynq-7020 `xc7z020clg484-1`, ARM Cortex-A9 và PL 50 MHz. Datapath gồm IR LDPC, xác minh và privacy amplification. Bốn AXI DMA chạy Simple mode; firmware UART điều phối dữ liệu thử từ PC.

## Tài liệu cần đọc

- [Tiến độ và công việc còn lại](reports/TIEN_DO_TOAN_BO_DU_AN.md).
- [Báo cáo hiện hành](reports/RECONCILIATION_CURRENT.json) và [QAS2 bảo vệ IR/verify/PA](reports/zc702_secure_app_20261027/REPORT.md).
- [35 đầu việc](reports/zc702_work_items.csv), [claim và bằng chứng](reports/zc702_claim_evidence.csv), [catalog FER](reports/FER_CATALOG.md).
- [Build hệ thống, baseline và kiểm thử board](syn/zc702/README.md).
- [Tổng hợp IP riêng](HUONG_DAN_TONG_HOP_ZC702.md), [firmware và UART](firmware/zc702_uart/README.md), [giao thức QAS2](firmware/zc702_uart/AUTH_SESSION_PROTOCOL.md).
- [Kế hoạch nghiệm thu](KE_HOACH_HOAN_THANH_MUC_TIEU_ZC702.md).

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `rtl/` | Datapath LDPC/IR, PA, AXI và wrapper ZC702 |
| `firmware/` | Driver và dịch vụ ARM/UART |
| `model/`, `data/` | Mô hình tham chiếu, fixture và đầu vào nghiên cứu |
| `tb/`, `sim/` | Testbench và cấu hình mô phỏng |
| `syn/zc702/` | Build, runner và verifier ZC702 |
| `build/zc702/` | Bitstream/XSA/ELF/BSP, checkpoint và log gốc |
| `reports/`, `results/` | Tiến độ, bằng chứng và kết quả có phạm vi xác định |
| `artifacts/review_zc702_20261026/` | Script và kết quả tổng hợp riêng IP bằng Vivado |

Giữ nguyên baseline; mọi lượt thử firmware cần build và thư mục run riêng. Kiểm tra `RUNNING_JOBS.json` và `FOLLOWUP_JOBS.json` trước khi dùng COM3. Alice/decoy/seed hiện là fixture hoặc mô phỏng tùy phép thử; PASS chức năng không phải chứng nhận bảo mật QKD.

Repo Git chứa mã nguồn, fixture và báo cáo. Thư mục `build/` cùng đầu ra Vivado lớn được giữ tại máy và không đưa vào commit; các đường dẫn raw evidence trong báo cáo cần bản lưu cục bộ tương ứng. Trạng thái job và kết quả kiểm thử đã lưu là snapshot lịch sử, cần kiểm tra lại môi trường trước khi chạy board.
