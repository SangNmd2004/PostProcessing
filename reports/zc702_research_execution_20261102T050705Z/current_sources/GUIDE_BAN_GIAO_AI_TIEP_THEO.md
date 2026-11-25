# Tiếp tục dự án ZC702

Người dùng đã cho phép sửa kế hoạch và triển khai tuần tự các task, kể cả test board, không cần hỏi lại từng chặng. Giữ nguyên 35 ID và REV gốc; không nâng trạng thái nếu thiếu bằng chứng.

1. Đọc `reports/RECONCILIATION_CURRENT.json`, kiểm tra hash/manifest checkpoint được trỏ tới, rồi đọc REPORT và MAPPING_CANONICAL tại đó.
2. Đọc `RUNNING_JOBS.json` live và xác minh PID/command line trước khi dùng COM3. `captured_trials` chỉ là số đã capture, không phải raw-verifier PASS. Không mở board khi tác vụ khác đang chạy hoặc còn chờ verify.
3. Kế hoạch hiện hành là `MO_HINH_TOAN_HOC_VA_KE_HOACH_THUC_NGHIEM.md` và `KE_HOACH_TONG_THE_VA_HUONG_PHAT_TRIEN.md`. Ưu tiên model/đo trên baseline50MHz; không ép số lịch sử thành target board.
4. Stage thực thi02/11 nằm trong đường dẫn ghi ở `build/zc702/research_active_stage.txt`. Đọc `paced_sequence/SEQUENCE_STATUS.json`, `prospective_finite/STATUS.json`, `fer_q05_followup/STATUS.json` trong stage để biết chuỗi tự động đã tới đâu. Không khởi chạy lại controller hoặc generator vào thư mục đã tồn tại/niêm phong.
5. ELF pacing là thử riêng. Firmware dùng một simple S2MM buffer; ghi REVEAL trong lúc decoder khác có thể xuất KEY tạo nguy cơ chờ vòng. Bản mới chuẩn bị load/reveal sau khi thu hết output của lượt active, rồi mới queue lượt tiếp. Không bỏ hàng rào này mà chưa có thiết kế output ownership và test tương ứng. Không sửa PL/baseline để làm test xanh.
6. Pacing hiện đo DDR IR, fixed f_adj và hai input paired được lặp. `IR_retained_proxy_bits` chỉ trừ IR leakage, chưa có tag/PE/PA; không gọi là secret-key throughput hoặc FER samples. Model arrival validation giữ input pool, chỉ lịch arrival là held-out.
7. Model finite-key đã chuyển sang ordered event replay và giữ split tail. Hai DECIDE cùng bit count vẫn là hai events. New-source prediction phải freeze trước board. Phân biệt virtual time, source optical simulation và wall time; age-jump có chủ đích không là dự đoán phân bố thời gian nguồn thực.
8. Các cohort FER dùng fixed sample size, seed disjoint và ground truth. Không chạy tag/PA thì báo NOT_TESTED; không gọi wrong codeword là tag đã bắt. Không dừng theo CI thuận lợi.
9. Sau test ELF: restore baseline trong finally, đối chiếu27hash, UART READY/MMIO receipt và đóng COM3. Helpers JTAG chỉ bỏ qua chính lỗi `Already stopped`, vẫn fail với lỗi khác. Giữ cả failed run và recovery evidence.
10. Sau từng chặng: raw logs/config/source/ELF/tool versions, verifier, báo cáo có giới hạn, guard cập nhật CSV, mapping canonical và current pointer, hash checkpoint trước/sau. Generator `prepare_research_tasks.py` không thay thế independent verifier; production trust/entropy/durable anti-rollback vẫn là gate riêng.

Không cập nhật memory ngoài workspace nếu người dùng chưa yêu cầu trực tiếp.
