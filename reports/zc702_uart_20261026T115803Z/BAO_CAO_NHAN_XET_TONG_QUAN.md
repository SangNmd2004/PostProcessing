# Báo cáo nhận xét tổng quan: thử nghiệm dữ liệu BB84 trên ZC702

**Ngày thực hiện:** 26/10/2026  
**Lượt chạy:** `20261026T115803Z`  
**Dữ liệu:** `bb84_key_test_Sim_20260618_002028.csv`

## 1. Đánh giá chung

Phần IR của dự án đã hoạt động trên kit ZC702 với toàn bộ dữ liệu BB84 mô phỏng trong file CSV. Hệ thống nhận dữ liệu qua UART, truyền dữ liệu giữa DDR và lõi xử lý bằng DMA, thực hiện giải mã/retry/reveal và trả kết quả đúng theo mô hình tham chiếu trong tất cả 84 lượt thử.

Kết quả xác nhận khả năng triển khai và tính đúng chức năng của hệ thống trong cấu hình kiểm thử. Khả năng sửa lỗi phụ thuộc rõ vào QBER và mã LDPC: dữ liệu nhiễu thấp được sửa tốt, dữ liệu nhiễu trung bình cần mã có nhiều bit kiểm tra hơn, còn hai nhóm nhiễu cao bị loại bỏ trong tập thử hiện tại.

## 2. Phạm vi và phương pháp

| Nội dung | Cấu hình / phạm vi |
|---|---|
| Phần cứng | ZC702, PS7 + lõi QKD + 4 AXI DMA |
| Clock xử lý PL | 50 MHz |
| Giao tiếp dữ liệu thử | UART COM3, 115200 baud |
| Khởi động hệ thống | JTAG nạp bitstream và ELF chung |
| Chế độ xử lý | Context 0, polling |
| Dữ liệu nguồn | 100 dòng, 49.505 vị trí bit Alice/Bob |
| Chuẩn bị block | 2.765 bit khóa + 307 vị trí puncture = 3.072 bit LDPC |
| Mã thử | r12 (1/2), r23 (2/3), r34 (3/4), r56 (5/6) |
| Số lượt | 21 block dữ liệu × 4 mã = 84 lượt |

Các khóa ngắn được ghép riêng theo nhóm nhiễu. Block cuối mỗi nhóm chồng lên block trước để sử dụng hết phần dư. Vì vậy, toàn bộ vị trí bit của 100 dòng đã được thử với từng mã, nhưng đây không phải 100 phép giải mã độc lập tương ứng từng dòng. Các block chồng lặp và các lượt thử lại cùng block với mã khác cũng không phải mẫu độc lập.

Lượt chạy này giữ nguyên cặp khóa Alice/Bob từ CSV, không tạo thêm lỗi ở Bob. Dữ liệu nguồn là mô phỏng BB84, chưa phải dữ liệu thu trực tiếp từ hệ thống quang học.

## 3. Kết quả tổng thể

| Chỉ tiêu | Kết quả |
|---|---:|
| Lượt phần cứng khớp tham chiếu | 84/84 — 100% |
| Lượt sửa đúng khóa Alice | 31/84 — 36,90% |
| Lượt discard | 53/84 — 63,10% |
| Hội tụ nhưng sai khóa trong tập thử | 0 |
| Số attempt trung bình trên toàn bộ lượt | 3,83 |
| Số attempt lớn nhất quan sát được | 5 |

**Tỷ lệ khớp tham chiếu và tỷ lệ sửa đúng có ý nghĩa khác nhau.** Khớp tham chiếu nghĩa là trạng thái, số vòng lặp từng attempt và kết quả xử lý phù hợp với mô hình; khi hội tụ, firmware còn đối chiếu toàn bộ word KEY và ERRCNT. Một lượt discard đúng dự kiến vẫn được tính là khớp tham chiếu, nhưng không được tính là tạo được khóa đã sửa.

Tỷ lệ 31/84 gộp cả việc cố ý thử các mã không phù hợp với mức nhiễu. Nó không đại diện cho tỷ lệ sửa lỗi của một hệ thống đã chọn mã thích nghi, cũng không phải tỷ lệ 31 dòng thành công trên 100 dòng CSV.

Gói dữ liệu sai CRC đã được firmware từ chối trước khi thực thi lõi QKD. CRC32 cung cấp kiểm tra lỗi truyền của phép thử; chưa phải cơ chế xác thực kênh trao đổi QKD.

## 4. Kết quả theo nhóm nhiễu và mã LDPC

Các ô kết quả là **số block sửa đúng / số block đã thử bằng mã đó**. QBER trong bảng được tính trên toàn bộ bit gốc của từng nhóm, không lấy trung bình không trọng số của cột QBER từng dòng.

| Nhóm | QBER gốc toàn nhóm | r12 | r23 | r34 | r56 |
|---|---:|---:|---:|---:|---:|
| WEAK | 0,31% | 4/4 | 4/4 | 4/4 | 4/4 |
| MILD | 3,65% | 5/5 | 5/5 | 1/5 | 0/5 |
| MODERATE | 8,37% | 4/4 | 0/4 | 0/4 | 0/4 |
| STRONG | 11,64% | 0/4 | 0/4 | 0/4 | 0/4 |
| SEVERE | 13,43% | 0/4 | 0/4 | 0/4 | 0/4 |

QBER thực tế của các block ghép khác QBER toàn nhóm: WEAK khoảng 0,29–0,33%; MILD 3,33–3,94%; MODERATE 7,59–8,93%; STRONG 11,07–12,33%; SEVERE 12,59–14,29%. Khi đối chiếu giới hạn giải mã, cần dùng QBER của block đang xử lý.

### Nhóm WEAK

Cả bốn mã đều sửa đúng toàn bộ block. r12, r23 và r34 đều hoàn thành sau một attempt; r56 cần trung bình 1,75 attempt. Kết quả cho thấy có thể cân nhắc mã tỷ lệ cao ở vùng nhiễu thấp, nhưng cần tính cả chi phí reveal/retry và lượng thông tin rò rỉ trước khi kết luận mã nào cho hiệu quả khóa bí mật tốt nhất.

### Nhóm MILD

r12 và r23 sửa đúng 5/5 block; r34 chỉ đạt 1/5 và r56 không sửa được block nào. r12 hoàn thành sau một attempt, trong khi r23 cần trung bình ba attempt. Trong tập dữ liệu này, lựa chọn mã tạo ra sự đánh đổi giữa số bit kiểm tra và số lượt trao đổi bổ sung; chưa có phép đo thời gian hoặc thông lượng để xếp hạng hiệu năng tổng thể.

### Nhóm MODERATE

Chỉ r12 sửa đúng 4/4 block, với trung bình 3,25 attempt. Ba mã còn lại đều discard. Đây là bằng chứng thực nghiệm cho thấy cấu hình mã yếu hơn không đáp ứng được các block nhiễu khoảng 7,59–8,93% đã thử, trong khi r12 vẫn sửa được với các lần reveal bổ sung.

### Nhóm STRONG và SEVERE

Cả bốn mã đều discard tất cả block sau năm attempt. Phần cứng thực hiện đúng kết quả dự kiến của mô hình, nhưng khả năng sửa lỗi của cấu hình hiện tại chưa đáp ứng được hai nhóm này. Không nên gán các lượt discard thành lỗi triển khai FPGA, cũng không nên coi đây là ngưỡng QBER tuyệt đối của thuật toán từ số mẫu hiện có.

## 5. Mức độ hoàn thành mục tiêu dự án

**Đã có bằng chứng trên phần cứng thật:** triển khai PS7/DMA/lõi IR, nhận bộ dữ liệu mới qua UART mà không biên dịch lại ELF theo dữ liệu, xử lý toàn bộ CSV, kiểm tra retry/reveal/discard và đối chiếu khóa đầu ra với tham chiếu khi hội tụ. Bảng đối chiếu từng dòng xác nhận không bỏ sót vị trí bit nguồn với cả bốn mã.

**Chưa hoàn tất kiểm chứng toàn bộ chuỗi hậu xử lý QKD:** PA ở lượt này chỉ chạy vector chuẩn 4.096 → 1.024 bit lúc khởi động; chưa nhận trực tiếp khóa CSV vừa qua IR. Chưa đánh giá độ dài khóa bí mật sau rò rỉ syndrome/reveal, xác thực và phân tích finite-key. Chưa xác nhận đa context đồng thời, IRQ, thông lượng hoặc hoạt động dài hạn.

Do đó, có thể kết luận **đã triển khai và kiểm chứng chức năng IR trên ZC702 bằng toàn bộ bộ dữ liệu BB84 mô phỏng hiện có**. Bằng chứng hiện tại chưa đủ để tuyên bố hệ thống QKD hoàn chỉnh tạo khóa bí mật an toàn trong điều kiện thực tế.

## 6. Hướng hoàn thiện dựa trên kết quả

1. Nối khóa đã sửa qua IR vào PA, kiểm tra đầu ra PA cho từng phiên dữ liệu CSV; không sử dụng kết quả của block bị discard.
2. Đánh giá chính sách chọn mã theo QBER và điều chỉnh sau retry. Đối chiếu số bit syndrome/reveal và thời gian thực đo, thay vì chỉ chọn theo tỷ lệ sửa đúng.
3. Tăng số mẫu độc lập, đặc biệt quanh vùng chuyển tiếp giải mã, để đánh giá xác suất thành công. Bộ CSV hiện tại nhỏ và có block chồng lặp.
4. Đo thời gian xử lý IR, thời gian UART/DMA và thông lượng riêng; sau đó kiểm thử nhiều context và chạy dài hạn khi phần quản lý buffer/context đã hoàn chỉnh.

## 7. Dữ liệu và bằng chứng kèm theo

- [Chi tiết 84 lượt block/mã](chi_tiet_block.csv)
- [Thống kê tổng hợp theo nhóm và mã](tong_hop.csv)
- [Đối chiếu 100 dòng dữ liệu nguồn](doi_chieu_tung_dong_csv.csv)
- [Log UART trên kit](../../build/zc702/uart_runs/20261026T115803Z/uart.log)
- [Receipt kết quả máy đọc được](../../build/zc702/uart_runs/20261026T115803Z/result.json)
- [Biên bản đối chiếu log thô và hash bằng chứng](../../build/zc702/uart_runs/20261026T115803Z/verified_evidence.json)

Báo cáo này dùng lượt chạy dữ liệu gốc `20261026T115803Z`; không trộn các mẫu QBER tạo thêm của lượt `20261026T114819Z` vào thống kê.
