# Gate còn thiếu cho persistence toàn phiên

P05 là timing; công việc persistence thuộc PUB04 và liên quan P04. Code descriptor hiện chỉ phục hồi CRC và so với RAM đang còn sống. Snapshot CRC hợp lệ từ trước vẫn được chấp nhận sau khi mất RAM tin cậy; chưa thể đóng gate này.

Thiết kế tiếp theo cần chọn storage thật và trusted monotonic anchor trước khi gọi đây là anti-rollback. CRC không xác thực trạng thái. UUID và epoch trong chính blob có thể bị replay không phải anchor độc lập. Địa chỉ OCM hoặc định nghĩa BBRAM trong header không phải storage driver hay chứng cứ tồn tại qua reset.

Hợp đồng an toàn dự kiến:

1. Nếu không có anchor được xác thực hoặc trạng thái durable hợp lệ: không resume phiên cũ; lockout và yêu cầu thiết lập phiên/khóa mới theo kênh xác thực.
2. Trước khi xác minh tag, reserve budget và commit trạng thái bền vững; chỉ sau commit thành công mới sử dụng quyền kiểm tra. Lỗi không được hoàn lại lượt đã reserve.
3. Blob lưu version/layout, session UUID, epoch, budget-used/limit và authenticator bằng khóa riêng; kiểm tra đối chiếu anchor. Không dùng khóa PA hoặc public seed để xác thực blob.
4. Commit hai slot/transaction phải chống mất điện tại mọi điểm; cả hai bản CRC đúng nhưng counter thấp hơn anchor đều bị từ chối.
5. Trên cold restore, không đọc destination RAM chưa khởi tạo. Trạng thái tin cậy phải là input có hợp đồng rõ ràng, không suy đoán từ bytes stack.

Phép thử nghiệm thu cần chạy C/storage driver thật và sau đó board riêng: warm reset, cold restart, snapshot cũ, sai UUID/version/auth tag, lỗi ghi/readback, cắt commit từng bước, exhausted budget, retransmission và khởi tạo phiên mới. Cho tới khi hoàn tất, giữ chứng cứ board cũ ở phạm vi boot-lifetime và PUB04 PARTIAL. Một test RAM-only phát hiện epoch giảm không thay các phép thử này.
