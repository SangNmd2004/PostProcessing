# Feasibility: thêm code gần rate 0,95

Trạng thái: phân tích cấu trúc và các thay đổi cần thiết; chưa có ma trận/code mới, chưa có số FER/f hay kết quả synthesis cho phương án này.

Với một circulant hoặc zero trên mỗi ô ma trận cơ sở, ZC=128, `n = nc*128`, `m = mb*128`, nominal `R0 = 1 - mb/nc`. Rate thực còn phụ thuộc rank. Mã nguồn hiện dùng NCOL=24 và bốn mã, trường chọn mã hai bit.

| nc | mb | n | m | R0 danh định | Nhận xét |
|---:|---:|---:|---:|---:|---|
| 24 | 4 | 3072 | 512 | 0,83333 | Đây là r56 hiện tại, không phải 0,95 |
| 24 | 2 | 3072 | 256 | 0,91667 | m=256 không cho rate 0,95 |
| 24 | 1 | 3072 | 128 | 0,95833 | Variable degree tối đa 1 với dạng base hiện tại; chất lượng giải mã rất hạn chế |
| 40 | 2 | 5120 | 256 | 0,95000 | Đúng rate danh định, nhưng variable degree tối đa 2; phải kiểm tra graph/FER |
| 80 | 4 | 10240 | 512 | 0,95000 | Có dư địa variable degree tới 4; cần thiết kế ma trận, mở cột/địa chỉ và buffer |

Không thể chỉ đổi tên code hay thêm một hàng ROM. Cần đánh giá đồng thời:

1. Chọn ma trận có rank, degree distribution và cấu trúc vòng phù hợp; PEG/ACE/density-evolution là hướng thiết kế, chưa phải kết quả đã có.
2. Xét lại d/δ, r0 và cửa sổ rate. Nếu giữ nc=24, mb=1, d=307 thì m−d âm và công thức rate bắt đầu vượt 1; không dùng nguyên công thức leakage/control hiện tại cho trường hợp đó mà không điều chỉnh. Chọn d riêng cho code hoặc yêu cầu pre-reveal thích hợp rồi kiểm chứng giao thức.
3. Rate cao không phủ mọi QBER <1%. Ví dụ h(0,5%)≈0,0454 nên capacity BSC khoảng 0,9546; code danh định 0,9583 còn cao hơn mức đó trước tính finite-length overhead. Phải xét cửa sổ puncture/shortening, không chỉ nhìn nominal rate.
4. Bốn ID hai bit hiện đã dùng hết. Thêm mã cần version hóa register/protocol/driver, hoặc thay thế một mã trong build thí nghiệm tách riêng; không phá artifact ABI đang được kiểm thử.
5. Mở các hằng NCOL, ROM/layer schedule, column address width, CH/SYN/KEY DMA length, GS table, buffer và model. Giữ 128 lane không có nghĩa các thay đổi đều miễn phí tài nguyên hay timing.
6. Chạy model FER/f trên cùng key/noise của baseline; chỉ chuyển sang RTL/PNR khi phương án đủ tốt. Đối chiếu bit-exact và số đo tài nguyên/timing mới sau đó.

Các tham chiếu mã hiện tại: `model/ir_model.py` (NCOL=24), `firmware/qkd_pp_regs.h` (CFG và QKD_N), `rtl/ldpc/ldpc_code_rom.v`, `rtl/ldpc/ldpc_ir_decoder.v`, `model/gen_rom.py`.

Phép tính capacity chỉ là kiểm tra khả thi lý tưởng cho BSC, không dự đoán FER của QC-LDPC thực hoặc chứng minh đạt f≤1,3. Các claim cải thiện phải chờ bộ code thực và sweep có kiểm soát.

## Nhánh rate khoảng 0,40

Với 24 cột, mb=14 cho nominal rate 0,4167; mb=15 cho 0,375. Để đúng 0,40 có thể xét nc=40, mb=24, nhưng đây là thay đổi lớn hơn về số layer, ROM, counter và bộ nhớ. Cần đánh giá graph/rank thay vì chọn chỉ bằng tỷ số.

Ngay cả phương án giữ 24 cột cũng cần mở giới hạn layer/syndrome và các buffer đang đặt tối đa 48 word syndrome cho mb=12; mb=14 cần 56 word, mb=15 cần 60 word. Phải cập nhật trường code/ABI, bảng mb và mọi bộ đếm/buffer liên quan. Không được chỉ đổi JSON/ROM và giữ header/firmware cũ.

Sửa được BER cao hơn không đồng nghĩa tạo được khóa bí mật ở QBER đó. Các gate loại sớm và finite-key phải được xét theo giả định giao thức; không bỏ ngưỡng để biến khả năng giải mã thành claim bảo mật.
