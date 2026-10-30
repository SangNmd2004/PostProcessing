# Báo cáo Mô hình Tích lũy Khóa Hữu Hạn PUB03 & Đối Chiếu ZC702

- **Thời gian:** 20261027T045657Z
- **Hạng mục:** `PUB03` (Finite-key accumulation model ell(N) and ABORT/split empirical validation)
- **Run kiểm chứng thực tế:** `build/zc702/key_stream_runs/20261026T153858Z/result.json`
- **Kết quả đối chiếu:** [pub_accumulation_validation.csv](../pub_accumulation_validation.csv)

## 1. Tóm Tắt Kết Quả Đối Chiếu Thực Nghiệm
- Tổng số quyết định máy trạng thái đánh giá: **18**
- Tỷ lệ khớp quyết định (`WAIT` / `EMIT` / `ABORT`): **18/18 (100.0%)**
- Khối phát cuối cùng (`EMIT`):
  - Số bit đầu vào tích lũy: **1,213,835 bit** (439 khối)
  - Độ dài khóa bí mật ell dự đoán: **104,768 bit**
  - Độ dài khóa bí mật ell thực đo trên board ZC702: **104,768 bit**
  - Chênh lệch Delta ell: **0 bit (Khớp chính xác tuyệt đối)**
  - Số lượt băm Hankel PA trên phần cứng PL: **103 passes** (1024-bit/pass)

## 2. Ý Nghĩa Khoa Học Cho Bài Báo
1. **Khắc phục giới hạn tiệm cận vô hạn:**
   Trong các bài báo QKD truyền thống, độ dài khóa thường tính theo công thức tiệm cận đơn giản. Khi đưa vào hệ số hữu hạn Lim (2014) với các số hạng suy hao căn(N), các khối đơn lẻ 1.2 Mbit ở kênh nhiễu trung bình (MODERATE) đều cho ell <= 0.
2. **Khôi phục khóa ở vùng MODERATE:**
   Bộ gom tự động tích lũy dữ liệu qua nhiều khối cho tới khi lượng thống kê vượt ngưỡng, trích xuất thành công khóa bí mật mà các hệ thống không tích lũy buộc phải hủy bỏ.
