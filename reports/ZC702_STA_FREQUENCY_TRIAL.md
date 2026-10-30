# STA thử thay constraint trên route hiện tại

Vivado 2020.2, tối đa hai thread, mở `system_routed.dcp` của hệ thống 50 MHz và thay clock constraint trong bộ nhớ. Không place/route lại, không tạo/nạp bitstream hoặc thay PS clock.

| Constraint MHz | Setup WNS ns | Hold WHS ns |
|---:|---:|---:|
| 50 | +2,645 | +0,007 |
| 55 | +0,827 | +0,007 |
| 60 | −0,688 | +0,007 |
| 70 | −3,069 | +0,007 |

Kết luận: route này không đạt setup với constraint 60/70 MHz. 55 MHz có slack dương trong phép thử STA, nhưng chưa phải clock đã được lập cấu hình và kiểm thử trên board. Không báo Fmax thực từ bảng này. Hệ thống được nghiệm thu trên kit vẫn là **50 MHz**.

Muốn đạt 70 MHz cần build riêng với cấu hình PS/FCLK thực được kiểm tra, tối ưu PnR và chạy regression. Không ghi đè cặp bit/XSA đã PASS hoặc nới constraints để che lỗi. Source/receipt: [script](../syn/zc702/sta_frequency_trial.tcl), [CSV](../build/zc702/timing_trials/existing_route_frequency_sweep.csv), [Vivado log](../build/zc702/sta_frequency_trial.log).
