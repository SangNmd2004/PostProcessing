# FER thành phần IR trên ZC702

QBER BSC=0.02, code=r34, NMS+GS, 10000 trial độc lập theo seed. PL 50 MHz.

SUCCESS=9996, DISCARD=4, WRONG_CODEWORD=0. FER=0.0004.
Khoảng Wilson hai phía 95%: (0.00015556283662307484, 0.0010281283353569795).

Mỗi vector được đánh giá trên board một lần, kiểm tra toàn bộ trạng thái và KEY theo golden. Không dùng vòng lặp một vector làm mẫu độc lập. Đây là FER của lõi IR với ground truth biết trước; không chạy tag/PA trong phép đo này và không gọi wrong codeword là lỗi đã bị tag bắt. Các lỗi tool/UART/hardware làm dừng và lưu run incomplete; không đưa batch chưa xác minh vào số liệu PASS.

Chưa thể khẳng định FER≈1e-3 nếu số mẫu/CI không đủ; không ép outcome theo mục tiêu bài báo.
