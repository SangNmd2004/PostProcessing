# Ablation ghép cặp bốn tầng trên ZC702

1000 input Alice/Bob độc lập theo BSC q=0.03, code=r23; cùng input và RNG bit D ở cả bốn cấu hình. Độ dài 3072, D=307, r0=0, reveal step77, 50 iterations. K=1, batch4, RTT=0, PL 50MHz. Thứ tự cấu hình random theo seed trước khi chạy.

| Cấu hình | Success | Discard | Wrong | Attempts TB | f IR trên success | DDR IR Mbit/s |
|---|---:|---:|---:|---:|---:|---:|
| OMS_random | 998 | 2 | 0 | 1.727 | 1.4434152677496834 | 8.631 |
| OMS_GS | 999 | 0 | 1 | 1.203 | 1.3713895038508743 | 18.347 |
| NMS_GS | 999 | 0 | 1 | 1.146 | 1.3637564636364359 | 24.176 |
| NMS_GS_ET_PP | 999 | 0 | 1 | 1.155 | 1.3649524207962587 | 27.477 |

Ba tầng đầu tắt ET và PP; tầng thứ tư bật ET=12/PP=(1,2,16). Điều này khác ablation model-only trước đó giữ ET/PP bật ở cả ba cấu hình. Không gộp hai tập thành một ablation. Dynamic profile, switching và đa context vẫn cần các tầng riêng trên dữ liệu ghép cặp.

Firmware so toàn bộ status/iters/USC/PP và KEY với golden trong vòng đo. Verifier độc lập đối chiếu packet CRC/SHA, input pairs/CH/syndrome/reveal, ground truth của golden và raw batch receipt; raw log không in lại KEY DMA của từng trial. f IR không gồm tag; FER gồm decoder discard hoặc converged wrong codeword. Không chạy tag hoặc PA trong phép thử này.

Thông lượng DDR gồm PS/DMA và kiểm tra golden, loại UART và PA; không phải secret-key throughput. Không tính ba/bốn cấu hình trên cùng input thành mẫu FER độc lập gộp. Wilson95 là pointwise theo cấu hình; paired_contrasts.csv có chênh lệch attempts và f trên common-success, tránh so các tập success khác nhau. CI attempts dùng xấp xỉ chuẩn, McNemar dùng kiểm định nhị thức chính xác; không ép kết luận FER từ ít sự kiện lỗi.

[Paired ablation figure](four_stage_ablation.png) | [SVG](four_stage_ablation.svg).
