# Kiểm tra thống kê ablation mô hình

1000 bộ Alice/Bob ghép cặp đúng input hash; 3000 lần đánh giá cấu hình. Không phải số đo board.
f được so thêm trên cùng 997 trial mà cả ba cấu hình đều sửa đúng, tránh dùng các tập success khác nhau.

CI của chênh lệch attempts là xấp xỉ chuẩn cho trung bình ghép cặp. McNemar dùng kiểm định nhị thức chính xác trên các cặp discordant. Số fail rất ít nên chênh lệch FER quan sát được không đủ để kết luận cải thiện FER có ý nghĩa chỉ từ các số đếm này. Không coi f/attempts mô hình là throughput hoặc số đo FPGA.
