# Kiểm chứng giới hạn xác minh tag trên ZC702

PASS 42 kiểm tra; replay 74 packet TX và UART thô. Fixture khóa công khai mô phỏng, kiểm tra toàn bộ KEY và PA1024 với tham chiếu.

- Hai entry point op20/op60 dùng chung bộ đếm; 2 tag đúng + 4 tag sai = 6 lượt.
- Hết cap=6: cả hai đường bị chặn, không append/output mới và input staging mất hiệu lực.
- Reset controller/accumulator/buffer không hoàn lại ngân sách; host chỉ được giảm cap và không thể giảm dưới used.
- Packet bị từ chối trước xác minh và yêu cầu PA thiếu seed không tiêu hao lượt.
- Mặc định mỗi lần khởi động firmware: 18.446 lượt, tương ứng union bound 18.446/2^64 dưới 1e-15 theo giả định hash/seed phù hợp; phép thử hạ cap xuống 6 để kiểm tra biên nhanh.

**Giới hạn:** bộ đếm chưa bền vững qua reset CPU/nạp ELF/mất nguồn; chưa gắn session ID xác thực và chưa giải quyết toàn bộ phân bổ composable epsilon, adaptive selection hoặc nguồn entropy. Không gọi đây là chứng nhận bảo mật QKD. Không tiêm lỗi DMA trong phép thử này.

Raw run: `build/zc702/verification_budget_runs/20261027T021157Z/`. Xem `checks.csv` và `verified_evidence.json`.
