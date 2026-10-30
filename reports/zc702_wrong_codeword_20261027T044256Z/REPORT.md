# Codeword sai tự nhiên bị tag Alice chặn trên ZC702

Fixture từ ablation trial=98, seed=1800098; decoder hội tụ nhưng còn 11 bit khác Alice. Đã đọc toàn bộ KEY thực qua DMA/UART và tính lại hash độc lập.

Tag gửi vào là hash đúng của Alice với seed đã truyền, không cố ý lật bit tag. Cả op20 và op60 từ chối codeword sai, không phát PA/append, tính đủ hai lượt vào ngân sách; reset buffer không hoàn lại lượt.

Đây là một fixture nguồn BSC công khai, thử hai entry point; không tính là hai mẫu lỗi độc lập hoặc FER campaign mới. Không thay đổi các nhãn NOT_TESTED tag/PA của các campaign FER khác. Seed vẫn là fixture kiểm thử, chưa có kênh xác thực/session persistence và không chứng nhận security thực.
