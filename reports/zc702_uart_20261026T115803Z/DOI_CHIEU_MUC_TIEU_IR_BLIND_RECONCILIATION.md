# Đối chiếu mục tiêu tài liệu lõi IR Blind Reconciliation

> Đây là đánh giá của lượt `20261026T115803Z`. Sau đó đã bổ sung các phép thử NMS+GS, bộ điều khiển ARM, IR→PA, IRQ và context. Trạng thái hiện tại cùng các mục chưa hoàn tất được ghi tại [kế hoạch nghiệm thu cập nhật](../../KE_HOACH_HOAN_THANH_MUC_TIEU_ZC702.md). Giữ bảng dưới đây để phản ánh đúng phạm vi của lượt chạy cũ.

**Ngày đánh giá:** 26/10/2026.  
**Tài liệu đối chiếu ban đầu:** bản đặc tả cũ đã được dọn theo yêu cầu ngày 30/10/2026. Xem [tổng quan ZC702 hiện hành](../../README.md).
**Bằng chứng chính:** lượt board `20261026T115803Z`; lượt hồi quy và quét QBER `20261026T114819Z` được nêu riêng khi cần.

## Kết luận

**Hệ thống đã đạt bước triển khai và kiểm chứng chức năng lõi IR trên ZC702, nhưng chưa chứng minh hoàn thành toàn bộ mục tiêu trong tài liệu.** Tài liệu mô tả một hệ thống Dynamic IR + Privacy Amplification rộng hơn bài test đang chạy: chọn chế độ theo hàng đợi, chọn mã và reveal thích nghi, GS puncturing, xác minh khóa, che RTT bằng bốn context, tích lũy PA và quyết định khóa hữu hạn.

Lượt toàn bộ CSV là bài kiểm thử giải mã blind cơ bản được chuẩn bị trước trên PC: dùng Offset Min-Sum, puncture ngẫu nhiên, r0 = 0 và các reveal đã tính từ mô hình. Firmware thực hiện các attempt và đối chiếu kết quả. Nó chưa vận hành đầy đủ bộ điều khiển giao thức Bob/Alice được mô tả trong tài liệu.

## Bảng đối chiếu

| Mục tiêu / chức năng trong tài liệu | Bằng chứng hiện có trên ZC702 | Đánh giá |
|---|---|---|
| QC-LDPC ZC=128, n=3072, bốn mother code | 21 block từ toàn bộ 100 dòng CSV, mỗi block chạy cả r12/r23/r34/r56 | Đã kiểm chứng chức năng với tập thử hiện tại |
| Blind reconciliation: puncture, giải mã, reveal, retry, discard | Đối chiếu trạng thái/vòng lặp từng attempt; khi hội tụ so sánh toàn bộ KEY và ERRCNT; 84/84 lượt khớp tham chiếu | Đã kiểm chứng vòng xử lý cơ bản bằng vector chuẩn bị trước |
| HOLD và pre-reveal r0 | HOLD dùng trong firmware; bộ hồi quy 9 vector có trường hợp pre-reveal. CSV dùng r0=0 | Có kiểm tra thao tác cơ bản; chưa chứng minh dynamic planner |
| NMS ×0,75 | Bộ hồi quy có vector NMS; 84 packet CSV có CFG2=12 trước khi firmware bật HOLD, nên NMS=0 | Chưa chạy toàn bộ CSV theo NMS như cấu hình trọng tâm của tài liệu |
| Grouping & sorting cho vị trí puncture | Generator CSV gọi `rng.choice(N, D, replace=False)` | CSV hiện dùng ngẫu nhiên, chưa kiểm chứng GS trên board cho bộ dữ liệu này |
| EFFICIENCY / THROUGHPUT tự chuyển theo hàng đợi | Host thử cả bốn mã; không chạy bộ điều khiển chọn profile theo hàng đợi trên ARM | Chưa kiểm chứng |
| Chọn code, f*, r0, Δ thích nghi; cập nhật PE từ ERRCNT | CFG và chuỗi reveal được mô hình tính trước rồi gửi UART | Chưa kiểm chứng bộ điều khiển trực tuyến |
| Loại sớm khi q_pe >11% | CSV vẫn được gửi giải với mọi mã, kể cả STRONG/SEVERE | Chưa kiểm chứng chính sách loại sớm của tài liệu |
| Early termination và post-processing | Trường trạng thái, pp_used và iterations được đối chiếu trong các vector; CSV đặt ET=12, PP=1 | Có kiểm tra chức năng theo vector; chưa đo độc lập mức cải thiện f/thời gian |
| Băm xác minh bắt codeword sai | Test dùng khóa tham chiếu đầy đủ để so sánh KEY; chưa chạy tag xác minh 64 bit giữa hai bên | Chưa kiểm chứng cơ chế verification_tag trong luồng giao thức |
| Bốn context xen kẽ, tuser gắn đúng buffer, che RTT | Board test chỉ context 0; Simple DMA không lưu KEY TUSER trong DDR | Chưa kiểm chứng trên board; cần hoàn thiện liên kết context với buffer nhận |
| Hankel PA | Vector chuẩn 4096 bit đầu vào →1024 bit đầu ra đã PASS trên board | PA độc lập đã kiểm chứng; chưa nối khóa CSV sau IR vào PA |
| Seed từ TRNG và chia sẻ với Alice | PA test dùng seed công khai cố định | Chưa kiểm chứng |
| Decoy finite-key, tích lũy block, EMIT/ABORT | Không chạy bộ gom và không có thống kê decoy cần thiết trong lượt CSV này | Chưa kiểm chứng trên board |
| DMA, kênh cổ điển, ngắt | DMA DDR hoạt động; UART vận chuyển vector từ PC; firmware polling | DMA đã kiểm chứng; chưa có Alice độc lập/kênh xác thực hoặc xác nhận IRQ |
| Clock 70 MHz và thông lượng khoảng 43,4 Mbit/s với bốn context | Hệ thống ZC702 chạy 50 MHz; chưa đo thông lượng IR theo điều kiện RTT của tài liệu | Chưa xác nhận các chỉ tiêu này trên ZC702 |

“Chưa kiểm chứng” không có nghĩa mã nguồn không có chức năng đó. Nó nghĩa là bằng chứng chạy board hiện tại chưa đủ để xác nhận chức năng trong đúng cấu hình/giao thức được mô tả.

## Vì sao không đối chiếu trực tiếp các tỷ lệ thành công?

Tài liệu ghi bộ BB84 gồm 16 block và chọn code theo bộ điều khiển, có loại sớm block nhiễu cao. Lượt board mới dùng 21 block để bao phủ cả phần dư, có block cuối chồng lặp, đồng thời thử đủ bốn mã kể cả mã không phù hợp. Do đó, 31/84 không thể so trực tiếp với 10/16 trong tài liệu để kết luận thuật toán tốt hơn hoặc kém hơn.

Tương tự, các số 70 MHz, tài nguyên Gowin và thông lượng bốn context trong tài liệu thuộc nền tảng/phép đo khác. Không chuyển chúng thành kết quả đo ZC702. Bản tài liệu còn ghi “chưa chạy trên mạch thật”; hiện đã có bằng chứng board cho phạm vi IR cơ bản và PA vector độc lập, nên phát biểu này cần được đọc theo thời điểm của tài liệu.

## Điều kiện để kết luận hoàn thành rộng hơn

1. Chạy lại cùng bộ dữ liệu với NMS và GS; ghi rõ cấu hình, so sánh với bộ hiện tại.
2. Đưa bộ điều khiển EFFICIENCY/THROUGHPUT, lựa chọn code/reveal và loại sớm lên luồng thực thi; kiểm thử quyết định của bộ điều khiển.
3. Kiểm tra verification tag, nối IR thành công → bỏ vị trí D → tích lũy → PA; chỉ xuất khóa sau xác minh và tính độ dài phù hợp.
4. Hoàn thiện ánh xạ context/buffer, chạy bốn context trên board; đo thời gian và thông lượng với RTT xác định.
5. Kiểm chứng nguồn seed, thống kê decoy/finite-key và EMIT/ABORT. Khi có các thành phần này mới đánh giá được mục tiêu tạo khóa bí mật của cả chuỗi.

Các bước trên là phần còn cần làm, không phải kết quả đã hoàn thành trong phiên kiểm thử hiện tại.

## File CSV gộp

[bao_cao_gop.csv](bao_cao_gop.csv) chứa **211 dòng dữ liệu**, gộp ba báo cáo của lượt toàn bộ CSV mà không sửa các file gốc:

| `record_type` | Số dòng | Ý nghĩa |
|---|---:|---|
| `block` | 84 | Chi tiết từng lượt block/mã |
| `summary` | 27 | Các cách tổng hợp cùng kết quả |
| `source_row_coverage` | 100 | Đối chiếu từng dòng CSV gốc và phạm vi bit đã chạy |

Lọc `record_type` trước khi xem/tính toán. Các loại bản ghi là các cách nhìn cùng dữ liệu, không cộng 211 dòng thành số phép thử. Ô trống là trường không áp dụng; cột `source_csv` cho biết file nguồn. File dùng UTF-8 BOM để mở bằng Excel. Việc gộp đã được kiểm tra bằng cách tách ngược từng loại bản ghi và so sánh mọi trường với CSV gốc; hash được lưu trong [manifest gộp](bao_cao_gop_manifest.json).

## Bằng chứng

- [Kết quả board](../../build/zc702/uart_runs/20261026T115803Z/result.json)
- [Log UART](../../build/zc702/uart_runs/20261026T115803Z/uart.log)
- [Báo cáo nhận xét tổng quan](BAO_CAO_NHAN_XET_TONG_QUAN.md)
- [Generator cho CSV và cấu hình decoder](../../syn/zc702/generate_uart_campaign.py)
- [Mô hình blind cơ bản dùng bởi lượt CSV](../../model/eval_csv.py)
- [Firmware nhận UART và thực thi vector](../../firmware/zc702_uart/service.h)
