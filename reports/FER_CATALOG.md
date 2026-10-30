# Danh mục FER được kiểm chứng trên ZC702

Mỗi dòng là một cohort đã complete và proof SHA khớp raw result. Không tự cộng pilot/qualification hoặc các cấu hình trên cùng input. Các khoảng Wilson95 là pointwise; đủ 10.000 mẫu không đồng nghĩa tự đạt FER mục tiêu. Tag/PA không chạy trong các phép đo decoder này.

| QBER % | Code | n | Success | Discard | Wrong | FER % | Wilson95 % | Vai trò | Báo cáo |
|---:|---|---:|---:|---:|---:|---:|---|---|---|
| 3 | r23 | 256 | 256 | 0 | 0 | 0.00000 | [0.00000, 1.47839] | bringup_or_resume_check | [20261026T155727Z](zc702_fer_20261026T155727Z/REPORT.md) |
| 3 | r23 | 8 | 8 | 0 | 0 | 0.00000 | [0.00000, 32.44076] | bringup_or_resume_check | [20261026T160301Z](zc702_fer_20261026T160301Z/REPORT.md) |
| 3 | r23 | 10000 | 9998 | 2 | 0 | 0.02000 | [0.00548, 0.07290] | qualification_sample_size | [20261026T160934Z](zc702_fer_20261026T160934Z/REPORT.md) |
| 1 | r34 | 1000 | 1000 | 0 | 0 | 0.00000 | [0.00000, 0.38268] | pilot | [20261027T030546Z](zc702_fer_20261027T030546Z/REPORT.md) |
| 2 | r34 | 1000 | 1000 | 0 | 0 | 0.00000 | [0.00000, 0.38268] | pilot | [20261027T030919Z](zc702_fer_20261027T030919Z/REPORT.md) |
| 5 | r12 | 1000 | 1000 | 0 | 0 | 0.00000 | [0.00000, 0.38268] | pilot | [20261027T031549Z](zc702_fer_20261027T031549Z/REPORT.md) |
| 7 | r12 | 1000 | 995 | 5 | 0 | 0.50000 | [0.21375, 1.16510] | pilot | [20261027T031934Z](zc702_fer_20261027T031934Z/REPORT.md) |
| 2 | r34 | 10000 | 9996 | 4 | 0 | 0.04000 | [0.01556, 0.10281] | qualification_sample_size | [20261027T032458Z](zc702_fer_20261027T032458Z/REPORT.md) |

Cohort complete/postverified: 8; cohort n≥10.000: 2; run incomplete hoặc chưa postverify: 0. Ranges seed trùng trong cùng stratum: [].

Một wrong codeword là hội tụ khác Alice theo ground truth. Nó không tự được gọi là lỗi tag đã bắt; ca verification thật trên wrong-key fixture có báo cáo riêng nếu đã chạy. Bring-up/resume cohorts nhỏ giữ để kiểm toán, không dùng để khẳng định FER≈10⁻³.
