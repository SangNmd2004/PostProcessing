# Dọn dự án PostProcessing ngày 30/10/2026

Đã dọn ba lượt theo yêu cầu: cache/build trung gian, tài liệu AI/nền tảng cũ, sau đó script và báo cáo dư thừa. Đọc [README ZC702](../../README.md) để tiếp tục dự án.

## Lượt rà script Python và báo cáo

- Bỏ hai utility của đợt chạy đã kết thúc: `monitor_research_reports.py` và `recover_closed_fer_manifest.py`. Giữ công cụ refresh, runner, verifier, golden model và các kiểm thử còn dùng.
- Bỏ hai bộ audit bàn giao không còn được tham chiếu; giữ bộ audit trong `zc702_reconciliation_20261027/handoff_audit` và các manifest/bằng chứng gốc.
- Bỏ báo cáo so sánh với bản tổng hợp đã xóa, cùng bảng `FER_INCOMPLETE_RUNS.csv` ghi 3.112 mẫu cũ: raw result hiện complete 10.000 mẫu, SHA khớp proof, FER catalog ghi 0 cohort chưa hoàn tất.
- Gộp hai JSON audit dọn dẹp vào một [AUDIT.json](AUDIT.json), bỏ JSON snapshot dư thừa. `removed_files.csv` là danh sách của lượt dọn đầu.
- Giữ báo cáo của từng cohort/phiên board khác nhau. Các bảng giống nhau không được coi là rác nếu thuộc các phiên kiểm thử khác nhau; giữ snapshot source gắn với manifest.

## Báo cáo cần đọc

[Tiến độ](../TIEN_DO_TOAN_BO_DU_AN.md), [mapping hiện hành](../RECONCILIATION_CURRENT.json), [35 đầu việc](../zc702_work_items.csv), [claim/bằng chứng](../zc702_claim_evidence.csv), [catalog FER](../FER_CATALOG.md), [báo cáo QAS2–IR/PA](../zc702_secure_app_20261027/REPORT.md).

Các file dọn được đưa vào Thùng rác; không tạo ZIP hay bản bàn giao mới. Dung lượng ổ đĩa chỉ được thu hồi khi người dùng xóa Thùng rác. Không chạy lại hoặc nạp board trong các lượt dọn này.
