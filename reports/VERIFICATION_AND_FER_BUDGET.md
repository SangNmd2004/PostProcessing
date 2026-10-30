# Verification budget và định nghĩa thống kê

Đây là phép tính theo giả định hash/seed và mẫu độc lập đã nêu; không phải chứng nhận an toàn hệ QKD.

Tag 64 bit, ngân sách riêng 1e-15: tối đa 18.446 lần kiểm tra. Nếu chỉ cấp 5e-16: tối đa 9.223. Tính cả lần kiểm tra tag bị từ chối trong phạm vi phiên; reset buffer không tự reset ngân sách composable.

16 triệu / 2765 = 5.786 block trọn; đây không phải số lần verification được bảo đảm. Cần xử lý retransmission, split, PE và phiên ghép.

Không quan sát sự kiện lỗi trên 3.000 mẫu độc lập: cận trên nhị thức chính xác một phía 95% 0.000998079011997. Với 10.000 mẫu: 0.000299528359777. Không gọi hai con số này là cận Wilson hai phía.

FER phải có định nghĩa/mẫu số trước thí nghiệm. Báo cáo riêng decoder discard, wrong codeword, verification reject, transport failure và hardware failure; không loại lặng lẽ run lỗi khỏi số liệu.

[Nguồn finite-key tham khảo: Lim et al.](https://arxiv.org/abs/1311.7129). Việc dùng công thức trong model chưa xác nhận adaptive postselection/PA split tuân thủ đầy đủ giả định của phân tích.
