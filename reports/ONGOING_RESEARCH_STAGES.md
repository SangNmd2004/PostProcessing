# Chuỗi nghiên cứu đang thực hiện, 27/10/2026

Trạng thái live: [RUNNING_JOBS.json](../RUNNING_JOBS.json), [FOLLOWUP_JOBS.json](../FOLLOWUP_JOBS.json). Không nạp board/UART song song với child đang giữ COM3. User đã cho phép reset/nạp/test; không cần hỏi lại cho các bước đã được giao. Máy 8 GB, Vivado tối đa hai thread; chuỗi hiện chỉ dùng ELF cũ khớp manifest và model worker tuần tự, không chạy PnR.

## Khôi phục checkpoint ngày 27/10/2026

Controller cũ dừng vì Windows trả WinError 5 khi thay `result.json.tmp` vào `result.json`. Leaf FER giữ 1.040 record đã lưu; resume giữ nguyên ID/seed. Đây là lỗi checkpoint của host, chưa phải lỗi FPGA.

Đã thêm `syn/zc702/checkpoint_io.py`: retry PermissionError tối đa 40 lần, cách nhau 50 ms; thay file nguyên tử, tên temp theo PID. Fault injection kiểm tra khóa tạm ba lần rồi phục hồi; khóa kéo dài vẫn báo lỗi và giữ checkpoint cũ. Controller lưu lịch sử lỗi cũ khi resume, tránh để trường error cũ chặn followup.

Phiên resume: controller PID 1540, child FER PID 4820, followup PID 4112. Kiểm tra live JSON và thời gian process trước khi dùng PID. Log mới: `build/zc702/research_stages_resume_stdout.log`, `research_stages_resume_stderr.log`; followup tương tự với tiền tố `research_followups_resume_`.

Monitor của đợt chạy cũ đã được dọn ngày 30/10/2026 sau khi hai chuỗi hoàn tất. Khi cần cập nhật báo cáo từ proof, dùng `python syn/zc702/refresh_research_status.py`. [Tiến độ toàn dự án](TIEN_DO_TOAN_BO_DU_AN.md).

Generator hiện quét raw/proof khớp hash để pilot mới không che mất qualification cũ. Tổng vẫn 13 đạt chức năng, 13 một phần, 9 chưa làm; không quy đổi thành tỷ lệ công sức. [Mô hình lập lịch và ranh giới kiểm chứng](publication_plan_20261026/RESOURCE_MODEL_DERIVATION.md).

Audit bàn giao phát hiện session FER bị terminate chưa flush `tx_manifest.json`. Đã phục hồi metadata của session cũ `fer_runs/20261027T032458Z/sessions/20261027T032458Z`: 1.300 packet/1.040 trial có ACCEPT, ACK cuối, reply và payload hash khớp record; không thay packet/log/result. `MANIFEST_RECOVERY.json` ghi provenance, SHA và giới hạn CRC tái tính. Session đang chạy chưa có manifest trước khi đóng là bình thường. Sau khi campaign complete vẫn cần raw verifier toàn bộ.

## Chuỗi chính đã chốt trước đo

Controller PID ban đầu 5748; kế hoạch và checkpoint tại `build/zc702/research_stages/20261027T024200Z/`. PID có thể bị tái sử dụng; dùng cả thời gian khởi động và trạng thái process trước khi thao tác.

1. Ablation 1.000 input pairs ×4 cấu hình, BSC 3%, r23, seed1800000 — đã raw-verify. [Báo cáo](zc702_board_ablation_20261027T024201Z/REPORT.md).
2. FER pilot 1.000, q=1%, r34, seed2100000 — đã raw-verify.
3. FER pilot 1.000, q=2%, r34, seed2200000 — đã raw-verify.
4. FER pilot 1.000, q=5%, r12, seed2500000 — đã raw-verify.
5. FER pilot 1.000, q=7%, r12, seed2700000 — đã raw-verify; 995 success, 5 discard. Điểm này chưa đạt mức FER 10⁻³.
6. FER qualification fixed n=10.000, q=2%, r34, seed3200000 — đang chạy tại thời điểm ghi chú. Không dừng sớm theo CI; lỗi hardware/transport làm dừng chuỗi và giữ evidence.

[FER catalog](FER_CATALOG.md) được tạo bằng `python syn/zc702/export_fer_catalog.py`; mỗi cohort giữ riêng, không tự gộp pilot/qualification hay các configuration trên cùng input.

## Chuỗi nối sau

Controller followup PID ban đầu 25180; checkpoint tại `build/zc702/research_followups/20261027T032212Z/`. Nó chờ chuỗi chính complete, không giữ COM3 trong lúc chờ, rồi tự chạy:

1. `run_wrong_codeword_test.py`: trial98/seed1800098 trong ablation hội tụ còn 11 bit khác Alice ở ba cấu hình GS. Dùng tag thực của Alice, không cố ý lật tag; kiểm tra cả op20 và op60 chặn actual wrong KEY, không xuất/append và vẫn tính lượt budget. Hiện đây là kế hoạch, chưa được gọi là tag đã bắt cho tới khi có proof.
2. `run_schedule_validation.py`: lấy NMS_GS/ET=PP=0 từ ablation; training/held-out input hash không giao nhau. Calibrate L/R ở K1, freeze model trước đo, rồi 54 điểm K/RTT với ba lần lặp. Ngưỡng latency engineering đã chốt trong code: mean absolute error≤10%, max≤20%. Có raw replay PASS chưa đồng nghĩa model đạt ngưỡng; phải đọc cờ latency_model_accepted.

Module `model/zc702_resource_model.py` đã qua self-check logic/causality và các ví dụ cycle, chưa được ghi board-validated trước khi followup chạy. `model/efficiency_throughput_crossover.py` là công thức fluid có điều kiện, chưa có điểm crossover đo thật. [Đặc tả crossover](publication_plan_20261026/CROSSOVER_MODEL_SPEC.md).

## Tiếp tục sau gián đoạn

Giữ nguyên firmware/model/runner của các cohort còn chạy. Không thay seed hoặc tham số để làm đẹp FER. Khi controller thực sự đã dừng, đọc stderr và leaf result trước khi resume:

```powershell
python .\syn\zc702\run_research_stages.py --resume .\build\zc702\research_stages\20261027T024200Z
python .\syn\zc702\run_research_followups.py --research-plan .\build\zc702\research_stages\20261027T024200Z --ablation .\build\zc702\board_ablation_runs\20261027T024201Z --resume .\build\zc702\research_followups\20261027T032212Z
```

Không chạy các lệnh này khi controller tương ứng vẫn còn sống. Chặng đã complete/postverified được bỏ qua, chặng partial có journal và seed guard. Followup không tự resume một leaf bị lỗi; phải đọc lỗi, phân tích và re-verify raw hoặc chạy cohort mới có ghi rõ phạm vi.

## Cần làm khi cả hai chuỗi kết thúc

- Kiểm tra proof SHA của từng cohort, cờ model acceptance và ca wrong-key; sửa lỗi thật nếu có, không đổi tiêu chí held-out sau khi xem kết quả.
- Export lại FER catalog, cập nhật `zc702_work_items.csv`, `zc702_acceptance_status.csv` và claim/evidence; PUB06 chỉ mới bốn tầng, PUB02 chỉ mới model có điều kiện, security gates vẫn mở.
- Tạo báo cáo tổng hợp và gói update có SHA với parent bất biến. Chỉ đóng gói run complete/postverified; không freeze một run đang ghi.
- Không nhầm số samples với tiến độ project: bảng có 35 mục, hiện 13 PASS và các mục PARTIAL/TODO phải giữ phạm vi cụ thể.
