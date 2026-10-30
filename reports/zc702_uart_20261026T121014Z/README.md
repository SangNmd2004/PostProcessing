# Báo cáo CSV ZC702 UART

Nguồn: `C:\Users\Admin\Downloads\PostProcessing\PostProcessing\build\zc702\uart_runs\20261026T121014Z`. Hai CSV dùng UTF-8 BOM, dấu phẩy, có header để mở bằng Excel.

- `chi_tiet_block.csv`: mỗi dòng là một lượt block/mã, gồm QBER, outcome, retry, reveal, ERRCNT và hash packet.
- `tong_hop.csv`: chọn cột `scope` để xem overall, source, csv_group, csv_group_code hoặc qber_sweep. Các scope là các cách nhìn cùng dữ liệu; không cộng tất cả dòng tổng hợp với nhau.

`hardware_match=1` gồm cả DISCARD đúng dự kiến. `SUCCESS` mới là sửa đúng khóa Alice của CSV/quét QBER. Tỷ lệ sửa đúng dùng `correction_rate_denominator`, loại bộ baseline không có nhãn sửa đúng CSV. ERRCNT trống khi discard vì thanh ghi có thể giữ giá trị cũ. Lỗi còn lại trống khi không có KEY nhận về. QBER baseline không được ghi trong receipt nên để trống. `iterations_sum_checked` là tổng giá trị thanh ghi iterations đã đối chiếu theo từng attempt, không phải số chu kỳ hay thời gian đo.

Toàn bộ 49,505 vị trí bit của CSV được dùng; có chồng lặp khối cuối và thử lại bốn mã. Không xem các lượt này là mẫu độc lập. Phép quét chủ động (nếu có) tạo lỗi ở Bob; CSV nguồn là mô phỏng. Nếu có `doi_chieu_tung_dong_csv.csv`, file này đối chiếu từng test_id và chứng minh đủ vị trí bit được chạy với cả bốn mã. Các cột successful/discarded_containing_blocks là kết quả block ghép chứa dòng đó, không phải kết quả sửa lỗi riêng dòng. Đây là kiểm thử IR trên board; PA chỉ có vector chuẩn lúc khởi động, chưa ghép khóa CSV vào PA.
