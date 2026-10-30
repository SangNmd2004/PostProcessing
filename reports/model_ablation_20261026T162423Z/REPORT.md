# Ablation ghép cặp trên mô hình

1000 trial BSC QBER=0.03, code=r23. Mỗi trial có cùng Alice/Bob và RNG bit D; chỉ đổi vị trí puncture và quy tắc check node. Không có thí nghiệm board trong báo cáo này.

| Cấu hình | Thành công | Discard | Sai codeword | Attempts TB | f IR TB trên success |
|---|---:|---:|---:|---:|---:|
| OMS_random | 999 | 1 | 0 | 1.809 | 1.4571458924330047 |
| OMS_GS | 998 | 2 | 0 | 1.222 | 1.3754215706190744 |
| NMS_GS | 1000 | 0 | 0 | 1.156 | 1.367246568676321 |

f IR không gồm tag; cột f_with_64bit_tag có riêng trong trials.csv. FER dùng discard hoặc codeword sai theo ground truth; không gọi sai codeword là verification đã bắt vì phép thử không chạy tag. Đây mới là ba tầng ablation; dynamic, switching và đa context phải thêm phép thử riêng. Không chuyển thời gian chạy Python thành thông lượng FPGA hoặc khóa bí mật.
