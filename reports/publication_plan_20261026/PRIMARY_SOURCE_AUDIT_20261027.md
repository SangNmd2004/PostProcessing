# Rà soát nguồn sơ cấp trước khi dùng bảng so sánh bài báo

Kiểm tra ngày 27/10/2026. Chỉ dùng trang nhà xuất bản và bản tác giả trên arXiv cho các nhận định dưới đây. Các nhãn A/B/C/D trong MD gốc chưa đủ làm citation; không coi bảng so sánh cũ là dữ liệu đã được kiểm toán đầy đủ.

## IR: xác định được bài phù hợp nhãn B

Zhu et al., *A Code Rate-Compatible High-Throughput Hardware Implementation Scheme for QKD Information Reconciliation*, JLT 40(12), 3786–3793 (2022). Abstract chính thức xác nhận ZCU102, QC-LDPC/NMS/HLS, throughput tối đa 136 Mbps, efficiency factor dưới 1,32 ở error-rate 1,7–10,6%, và mức FER được báo là 10⁻³. [Nguồn nhà xuất bản](https://opg.optica.org/jlt/abstract.cfm?uri=jlt-40-12-3786).

Ở lượt rà soát này chỉ đọc được abstract/metadata, chưa có full text. Vì vậy chưa xác nhận clock 250 MHz, số LUT/FF/BRAM, code length hoặc cách tính throughput/FER trong bảng cũ. Chưa lấy các số đó làm căn cứ tính tỷ số hơn/kém. Việc bài có số liệu IR không tự chứng minh bài bỏ qua finite-key hoặc PA.

## PA: cần sửa cách nhận dạng nhãn D và phiên bản

Yan et al., *Large-Scale and High-Speed FPGA-Based Privacy Amplification for Quantum Key Distribution*, JLT 41(1), 169–175 (2023). Abstract nhà xuất bản mô tả MMH-MH/NTT, throughput trên 1,5 Gbps với input gần 10⁸ bit. [Nguồn nhà xuất bản](https://opg.optica.org/jlt/abstract.cfm?uri=jlt-41-1-169).

Bản arXiv 2021 có tiêu đề gần giống, ba tác giả và báo 1 Gbps ở input 10⁸ bit. Không trộn số của hai phiên bản. [Bản tác giả arXiv:2107.01013](https://arxiv.org/abs/2107.01013). Nhận định “MMH-MH 1,5 Gbps, khối ≤768 kbit” trong ghi chú cũ chưa được xác nhận từ các nguồn này; cần đối chiếu tài liệu gốc đã dùng để biết có nhầm hai công trình hoặc hai cách chia block hay không. Chưa xác nhận board/clock và mẫu số throughput từ full text.

## Finite-key

Nguồn nền tảng đã định danh: Lim et al., *Concise Security Bounds for Practical Decoy-State Quantum Key Distribution*, PRA 89, 022307 (2014), [arXiv:1311.7129](https://arxiv.org/abs/1311.7129), [DOI](https://doi.org/10.1103/PhysRevA.89.022307). Đây là nguồn cho bounds finite-key; việc port công thức vào C/Python chưa tự chứng minh transcript, adaptive block selection hoặc epsilon allocation của hệ hiện tại thỏa giả định giao thức.

## Các phép so sánh được phép làm hiện tại

1. Với hệ hiện tại, dùng tài nguyên Vivado và latency/throughput board có scope rõ; không quy đổi LUT4 sang LUT6 hoặc gán tài nguyên whole SoC thành tài nguyên IR riêng.
2. f phải ghi có/không gồm tag/PE, code/r0/reveal và chỉ xét retained correct blocks khi so efficiency. FER phải ghi số mẫu, discard/wrong và CI; không so một lần decode với blind nhiều attempt mà bỏ điều kiện đó.
3. Throughput phải phân biệt input-original, input được replay nhiều pass, output hash và khóa bí mật sau toàn pipeline. Tỷ số của các đại lượng khác mẫu số không có ý nghĩa.
4. Kết quả PA hiện tại 103 pass có latency PS-observed gồm DMA/cache. Không lấy băng thông nội bộ một pass để so trực tiếp với tốc độ input/output của một thuật toán NTT khác.
5. Chưa tuyên bố novelty từ việc một abstract không nhắc đến feature của hệ này. Nhãn A/C và các chi tiết full text còn thiếu được giữ unresolved; chưa điền bằng phỏng đoán.

Đây là audit nguồn tham khảo, không phải cam kết phù hợp venue hoặc kết luận hệ hiện tại tốt hơn các công bố trên.
