> Cập nhật 26/10/2026: đã có kiểm thử chức năng trên ZC702 với Alice mô phỏng PC, gồm NMS+GS, điều khiển ARM, IR→xác minh→PA, IRQ QKD và bốn context. Xem [trạng thái nghiệm thu và các mục còn thiếu](KE_HOACH_HOAN_THANH_MUC_TIEU_ZC702.md). Các số Gowin/70 MHz/mô hình bên dưới được giữ theo bối cảnh tài liệu gốc, không phải số đo ZC702.

Tang Mega 138K · GW5AST-138 · D:\\Tai_lieu\\LAB\\PostProcessing

# Lõi hậu xử lý QKD: Dynamic IR + Privacy Amplification

Sơ đồ luồng, ý nghĩa từng tham số và kết quả đo của IP `qkd_pp_axi`. IP gồm khối reconciliation LDPC (ZC = 128, n = 3072 bit, layered Normalized Min-Sum ×0.75, vị trí đục lỗ theo grouping & sorting, hai chế độ điều khiển, 4 khối xen kẽ trên một decoder) và khối privacy amplification dạng hash Hankel với độ dài khóa hữu hạn decoy. Cập nhật 2026-10-24: xung nhịp chốt 70 MHz, PnR đạt timing.

RTL ↔ golden: PASS 9 khối + PA; 30 khối / 4 ngữ cảnh, bit-exact PnR: 70 MHz đạt timing (TNS 0) 4 ngữ cảnh: IR ×3.48, ≈ 43.4 Mbit/s ở 70 MHz Khóa hữu hạn decoy (Lim 2014) + gom khối PA Logic 36% · FF 23 840 · BSRAM 135/340 Biên timing chỉ +0.03 ns Chưa chạy trên mạch thật

## 1. Ai nói chuyện với ai

FPGA làm phần tính toán nặng: giải mã LDPC và hash PA. CPU phía Bob giữ giao thức: ước lượng QBER, chọn code, hỏi Alice qua kênh cổ điển, cấp seed TRNG cho PA. CPU nạp dữ liệu bằng DMA, điều khiển bằng thanh ghi và nhận ngắt.

Mũi tên cam là vòng lặp của blind reconciliation: khi lõi báo FAIL, CPU xin Alice công bố thêm Δ bit trong D. Ở chế độ dynamic, tin nhắn đầu tiên của Alice đã mang sẵn r0 bit công bố cùng syndrome. Alice chạy cùng bộ điều khiển tất định nên biết trước code và r0.

## 2. Một khối đi qua hệ thống

Trước mỗi khối, firmware nhìn hàng đợi khóa thô. Nếu IR đang theo kịp (≤ 1 khối chờ), nó dùng chế độ EFFICIENCY để giữ f thấp. Nếu khóa thô dồn lại (≥ 4 khối chờ), nó chuyển sang THROUGHPUT để mỗi khối chỉ cần khoảng 1 lần thử. Vòng trái (post-processing) chạy ngay trong FPGA. Vòng phải (công bố thêm bit) phải hỏi qua mạng nên tốn thời gian nhất.

EFFICIENCY là blind cơ bản: r0 = 0 (đục lỗ hết D), code lấy từ bảng QBER, mỗi lần sai công bố 77 bit. THROUGHPUT là dynamic: chọn code sao cho còn chỗ cứu tới f = 1.7, công bố sẵn r0 bit cùng syndrome. Băm xác minh bắt các khối decoder hội tụ về codeword sai. Dừng sớm (ET) cắt một lần giải khi số check chưa thỏa không giảm trong 12 vòng liên tiếp.

| Ô trong hình | Ở đâu | File |
| --- | --- | --- |
| Chọn chế độ | firmware: `qkd_select_profile`; mô hình: `PROFILES`, `simulate_queue` | `model/dyn_ir.py`, `firmware/qkd_pp_driver.c` |
| Ước lượng QBER, lập kế hoạch, Δ, f\* | firmware: `Controller.plan / next_reveal / update` | `model/dyn_ir.py`, `firmware/qkd_pp_driver.c` |
| Vị trí D (GS) | `gs_select`, bảng `qkd_punct_pos` | `model/puncture.py`, `firmware/qkd_punct_tables.h` |
| Băm xác minh | `verification_tag` qua lõi PA | `firmware/qkd_pp_driver.c` |
| Nạp khối (HOLD) | ngữ cảnh `FREE → HOLD` khi CFG2\[4\] = 1; bộ ghi bit công bố R_RD → R_CAP → R_WR | `rtl/top/qkd_ir_core.v` |
| Giải mã, dừng sớm | `S_LOAD → (S_RD → S_WR) chồng layer → [S_CHK] → S_LEND` | `rtl/ldpc/ldpc_ir_decoder.v` |
| n_usc, post-processing | `S_USC → S_UEND → S_UP1/2 → S_UFIN → S_CNT → S_CFLIP` | `rtl/ldpc/ldpc_ir_decoder.v` |
| Key + ERRCNT | ngữ cảnh `OUT`, gearbox ZC → 64 bit, `tuser` = số ngữ cảnh, bộ đếm lỗi 2 tầng | `rtl/top/qkd_ir_core.v` |
| Gom khối PA, EMIT / ABORT | `PAAccumulator`; firmware `pa_accum_add / decide / emitted` | `model/pa_accum.py`, `firmware/qkd_pp_driver.c` |

## 3. Bên trong một layer của decoder

Mỗi layer có hai pha; mỗi pha xử lý một cạnh (circulant khác 0) mỗi chu kỳ trên cả 128 lane. Pha đọc tìm hai giá trị nhỏ nhất. Pha ghi tính lại APP bằng cách cộng phần chênh lệch C2V, nên giữa hai pha chỉ phải giữ 1 bit dấu.

Các layer chồng lên nhau (từ 2026-10-22): layer sau bắt đầu đọc trong lúc các lần ghi của layer trước vẫn đang đi qua pipeline. Từ 2026-10-24, RAM APP và C2V có thanh ghi đầu ra BSRAM (đọc trễ 2 chu kỳ) để cắt dây dài khoảng 8 ns từ RAM sang shifter. Vì vậy lần ghi đầu bắt đầu 6 chu kỳ sau lần đọc cuối. Khoảng cách từ lần ghi cuối tới lần đọc đầu của layer sau lấy từ ROM theo từng layer (≥ 2; r12 cần 4 vì các layer liền nhau dùng chung cột cuối). `layer_sched.py` tính khoảng này để không cột nào bị đọc khi lần ghi của nó chưa xong; `gen_rom.py` kiểm tra, mô phỏng có assertion, và không cần logic dừng.

đọc a → r0 (thanh ghi BSRAM) → r1 (shifter nửa 1) → r1x (nửa 2) → r1b (v2c) → r2 (CNU, ghi SGN) ghi a → w0 (c2v mới) → w1 (Δ) → w2 (ghi C2V, shifter nửa 1) → w2b (nửa 2) → w2c (cộng) → w2d (bão hòa) → ghi APP

app cũ + Δ đúng bằng v2c + c2v mới như trong mô hình Python, nên kết quả bit-exact. Shifter dùng chung cho cả hai pha, chia 2 tầng có thanh ghi; phép cộng (w2c) và bão hòa (w2d) mỗi phép một tầng. Chỉ số cạnh ở tầng r2 và w0 được nhân bản theo 16 nhóm lane để giảm fanout. XOR dấu ở pha đọc cho cả cờ parity của layer lẫn số check chưa thỏa dùng cho dừng sớm.

## 4. Bốn khối trên một decoder

Ở RTT 100 µs, phần lớn thời gian của một khối là chờ Alice gửi syndrome hoặc bit công bố. Từ 2026-10-23, lõi giữ tới 4 khối cùng lúc (`CTX_W = 2`). Khi một khối chờ Alice, decoder giải khối khác. Mỗi lần thử đều nạp lại APP từ CH RAM, nên chỉ CH RAM và SYN RAM cần một bank riêng cho mỗi khối; APP, C2V và SGN dùng chung. Các bank làm RAM sâu hơn chứ không rộng hơn, nên số BSRAM không đổi.

Bộ nạp chỉ ghi vào ngữ cảnh FREE. Bộ ghi bit công bố chỉ ghi vào ngữ cảnh HOLD hoặc WAIT. Vì vậy không có hai bên cùng ghi một bank. Lõi dùng cổng CH RAM khi decoder không ở `S_LOAD`, `S_CNT` hay `S_CFLIP` (`ch_grant`). RETRY không bao giờ vượt lên trước các bit công bố đã ghi trước nó. Ngữ cảnh 0 hoạt động như lõi một khối cũ.

| RTT 100 µs, 30 khối (data/sessions_tb) | 1 ngữ cảnh | 4 ngữ cảnh |
| --- | --- | --- |
| Mô hình `model/exp_ctx.py` | 11–18 Mbit/s | 34–64 Mbit/s (×3.0–3.5) |
| RTL `tb_qkd_ir_ctx.v`, tính ở 100 MHz | 18.3 Mbit/s | **63.6 Mbit/s (×3.48)** |
| RTL ở xung nhịp chốt 70 MHz (133 728 chu kỳ) | ≈ 12.5 Mbit/s | **≈ 43.4 Mbit/s** |

Đây là năng lực IR, tính bằng bit khóa đã sửa lỗi. Các kênh mô phỏng hiện chỉ cho 1–32 kbit/s khóa thô, nên ngữ cảnh chưa làm tăng khóa bí mật. Thay đổi này chuẩn bị cho hệ quang nhanh hơn hoặc nhiều đường truyền. Với RTT 1 ms, 4 ngữ cảnh cho khoảng ×4.

## 5. Cửa sổ rate của 4 mother code

Mỗi mother code cho một cửa sổ rate. Chấm tròn là rate khi mọi bit D còn punctured; mỗi bit được công bố đẩy rate sang trái. Ở chế độ dynamic, firmware nhắm thẳng R\* trong cửa sổ bằng r0 bit công bố sẵn. Đường cam là giới hạn Shannon 1 − h(Q): code chỉ giải được khi rate đang dùng nằm bên trái đường của QBER thật.

Chấm tròn: R₀/(1 − δ). Đầu mũi tên: (R₀ − δ)/(1 − δ), khi đã công bố hết D. Ở QBER dưới 1% (đường 1% nằm sát mép phải), code cao nhất r56 dừng ở 0.926 nên f ≥ 1.9; muốn tốt hơn cần thêm một code rate khoảng 0.95.

| Code | Layer mb | Syndrome m (bit) | R₀ | Rate đầu → cuối | Cạnh E | Bậc hàng max | Chu kỳ / vòng lặp |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `0 · r12` | 12 | 1536 | 0.500 | 0.556 → 0.444 | 73 | 7 | 248 (10-23: 213, 10-10: 290) |
| `1 · r23` | 8 | 1024 | 0.667 | 0.741 → 0.630 | 77 | 10 | 211 (10-23: 201, 10-10: 250) |
| `2 · r34` | 6 | 768 | 0.750 | 0.833 → 0.722 | 77 | 13 | 199 (10-23: 191, 10-10: 226) |
| `3 · r56` | 4 | 512 | 0.833 | 0.926 → 0.815 | 73 | 19 | 179 (10-23: 173, 10-10: 194) |

### Chọn 307 vị trí D: ngẫu nhiên hay grouping & sorting

Các vị trí D bắt đầu ở trạng thái punctured (LLR = 0). Một check có từ 2 nút punctured trở lên không giúp khôi phục nút nào. Thuật toán GS chọn từng nút có nhiều check "sạch" nhất, rồi công bố theo thứ tự ngược lại: nút khó khôi phục nhất được công bố trước. RTL không đổi vì vị trí đi qua luồng DMA.

| Code @ QBER | f ngẫu nhiên | f GS | Lần thử ngẫu nhiên | Lần thử GS |
| --- | --- | --- | --- | --- |
| `r56` @ 0.5% | 2.18 | 1.76 | 5.28 | 2.00 |
| `r34` @ 1.5% | 1.61 | 1.49 | 3.44 | 1.16 |
| `r34` @ 2% | 1.48 | 1.32 | 8.46 | 4.36 |
| `r23` @ 3% | 1.40 | 1.35 | 3.12 | 1.58 |
| `r12` @ 7% | 1.25 | 1.23 | 3.43 | 1.93 |

200 khối mỗi điểm, bước công bố 16 bit, Offset Min-Sum (`results/exp_punct.txt`). Biến thể "compact" (tối đa số nút khôi phục được sau 1 bước) cho kết quả tệ hơn cả ngẫu nhiên, nên số nút 1 bước không phải là chỉ số đúng.

## 6. Privacy amplification

Khóa đã reconcile (bỏ vị trí D, gom nhiều khối) được nén bằng hash Hankel: y\[j\] = ⊕ᵢ x\[i\]·s\[i+j\]. Mỗi chu kỳ đẩy vào 8 bit khóa và 8 bit seed. Seed lấy từ TRNG và chia sẻ với Alice, thay cho LFSR 64 bit của bản cũ vốn không đủ để chứng minh an toàn.

Mỗi lượt cần (n_words + 33) word seed và cho 1024 bit ra. Muốn khóa dài hơn: chạy lượt thứ c với seed bắt đầu từ bit c·1024. Chạy với seed riêng và chỉ giữ 64 bit đầu thì được verification hash. Mô phỏng: 4096 bit trong 581 chu kỳ, bit-exact với `pa_model.py`.

### Độ dài khóa hữu hạn với decoy và bộ gom khối PA

Từ 2026-10-22, firmware tính ℓ theo công thức decoy hữu hạn của Lim et al. (2014), với εsec = 10⁻⁹ và εcor = 10⁻¹⁵. Phần chân không s₀ và đơn photon s₁ lấy từ thống kê decoy; lỗi pha lấy từ cơ sở X cộng số hạng γ của kích thước hữu hạn; leakEC gồm cả tag xác minh 64 bit của mỗi khối IR.

ℓ = s₀ + s₁·(1 − h(φ₁ + γ)) − leak_EC − 6·log₂(21/ε_sec) − log₂(2/ε_cor)

Quy tắc "QBER > 11% thì hủy" chỉ đúng khi có nguồn đơn photon, f = 1 và dữ liệu vô hạn. Vì vậy bộ gom (`pa_accum.py`, `pa_accum_*` trong firmware) gom các khối IR thành công rồi quyết định sau mỗi khối:

| Quyết định | Điều kiện (trên toàn bộ thống kê đã gom) |
| --- | --- |
| **EMIT** | ℓ > 0 và một trong các điều kiện: gấp đôi khối chỉ tăng tỉ lệ \< 10%; tỉ lệ ≥ 85% mức tiệm cận; khối đạt 16 Mbit; khối đã gom ≥ 1 giờ |
| **EMIT, tách** | ℓ tốt nhất ≥ 100 kbit và ℓ hiện tại \< 95% mức đó (kênh xấu đi): phát tại điểm tốt nhất, phần sau sang khối mới |
| **ABORT** | Tỉ lệ tiệm cận ≤ 0 (đã có ≥ 200k bit), hoặc khối 16 Mbit mà ℓ ≤ 0 |
| WAIT | Còn lại |

Alice chạy cùng quy tắc trên cùng thống kê công khai, nên hai bên phát hoặc hủy cùng lúc. Mỗi khối IR có QBER cơ sở X > 11% vẫn bị loại trước khi giải mã. Kết quả: MODERATE 1 giờ từ 0 lên 470 kbit; chuỗi MIXED 2 giờ 20 từ 1.48 lên 1.94 Mbit đã phát, khóa đầu sau 3 phút (`results/exp_accum.md`).

Hash Hankel xử lý khối 1–5 Mbit trong ≤ khoảng 2 s, nhanh hơn nhiều so với thời gian thu thập (38–1 400 s mỗi phiên). Khối ≥ 10 Mbit nên chuyển sang MMH-MH trên NTT vì thời gian Hankel tỉ lệ n·ℓ.

## 7. Các tham số, nhóm theo nơi đặt

### a. Thanh ghi CFG (0x08): áp dụng cho mỗi lần thử

| Tham số | Bit | Mặc định | Ý nghĩa | Tăng lên thì… | Khuyến nghị |
| --- | --- | --- | --- | --- | --- |
| `code` | `[1:0]` | 2 (r34) | Chọn mother code | Rate cao hơn, ít leakage, dễ thất bại hơn | Do bộ điều khiển chọn |
| `lq` | `[6:2]` | 8 | \|LLR\| kênh của bit key | Quá 9 thì C2V/APP bão hòa, FER tăng mạnh | 7–9 |
| `iter_max` | `[15:8]` | 50 | Số vòng lặp tối đa mỗi lần giải | Mỗi lần giải thất bại tốn tới chừng ấy vòng (ET cắt bớt) | 50 khi bật ET |
| `pp_rounds` | `[17:16]` | 1 | Số lần post-processing tối đa mỗi lần thử | Mỗi lần là thêm một lần giải đầy đủ | 1 |
| `pp_min_usc` | `[19:18]` | 2 | Đảo dấu bit key chạm ≥ bấy nhiêu check chưa thỏa | Đảo ít bit hơn | 2 |
| `pp_max_usc` | `[31:20]` | 16 | Chỉ chạy post-processing khi n_usc ≤ giá trị này | Chạy cả với lỗi waterfall, tốn thời gian vô ích | 16 |

### b. CFG2 (0x20) và ERRCNT (0x24)

| Tham số | Bit | Mặc định | Ý nghĩa | Ảnh hưởng đo được |
| --- | --- | --- | --- | --- |
| `et_patience` | `CFG2[3:0]` | 12 | Dừng một lần giải nếu số check chưa thỏa (đo ở pha đọc) không giảm trong bấy nhiêu vòng; 0 = tắt | r34, Q 2%: 121 → 92 vòng/khối, f 1.55 → 1.57. Giá trị 8: còn 76 vòng nhưng f 1.60 |
| `HOLD` | `CFG2[4]` | 0 | Khối nạp xong thì chờ REVEAL + RETRY, để công bố r0 bit trước lần thử đầu | Firmware bật cho cả hai chế độ (EFFICIENCY dùng r0 = 0) |
| `NMS` | `CFG2[5]` | 1 | 1: \|c2v\| = min − (min >> 2) (α = 0.75); 0: offset min-sum 3/2/1 | NMS ít hơn 25–45% vòng lặp, f bằng hoặc thấp hơn ở cả 4 code |
| `ERRCNT` | `0x24 [11:0]` | — | Số lỗi kênh đã sửa ở khối thành công gần nhất; QBER = ERRCNT / 2765 | Dùng để theo dõi và hiệu chỉnh PE |

### c. Thanh ghi ngữ cảnh (từ 2026-10-23)

| Thanh ghi | Địa chỉ / bit | Ý nghĩa |
| --- | --- | --- |
| `CTRL.ctx` · `REVEAL.ctx` | `CTRL[9:8]` · `REVEAL[21:20]` | Ngữ cảnh mà lệnh RETRY / DISCARD hoặc bit công bố nhắm tới |
| `LOAD_CTX` | `0x28` | Ngữ cảnh FREE nhận khối nạp tiếp theo |
| `CTX_SUM` | `0x2C` | \[7:0\] FREE · \[15:8\] đang chờ · \[23:16\] SUCCESS · \[31:24\] FAIL; ghi 1 vào \[31:16\] để xóa |
| `CTX_CFG` | `0x30` | Chỉ đọc: \[3:0\] = CTX_W |
| `CTX_A` · `CTX_B` | `0x80 + 8c` · `0x84 + 8c` | {lần thử, n_usc, vòng lặp} · {trạng thái, pp_used, ERRCNT} của ngữ cảnh c |
| `CTX_CYC` | `0xC0 + 4c` | Số chu kỳ decoder đã dùng cho ngữ cảnh c |

Firmware: API không chặn `qkd_mc_start_block / qkd_mc_on_syndrome / qkd_mc_on_reveals / qkd_mc_poll`. Key ra trên AXI-Stream mang số ngữ cảnh ở `m_axis_key_tuser`.

### d. Bộ điều khiển (firmware): hai chế độ

| Tham số | EFFICIENCY | THROUGHPUT | Ý nghĩa |
| --- | --- | --- | --- |
| Khi nào dùng | hàng đợi ≤ 1 | hàng đợi ≥ 4 | Số khối khóa thô đang chờ khi bắt đầu một khối; giữa hai ngưỡng giữ chế độ cũ |
| Chọn code | bảng q_pe | R\* = 1 − f\*·h(q) | Bảng: r56 ≤ 0.8% \< r34 ≤ 2.2% \< r23 ≤ 4.5% \< r12 |
| Cận trên PE · z | 0 | 1.5 | q = q_pe + z·σ, mẫu PE 256 bit |
| f\* ban đầu | — | 1.30 | Tự chỉnh trong \[1.05, 1.8\]: ×0.98 khi thành công ngay, ×1.04 mỗi lần thử thất bại |
| f_safe | — | 1.7 | Chỉ dùng code mà công bố hết D vẫn đạt f = 1.7 |
| r0 · Δ | 0 · 77 | tính · n_usc | Bit công bố cùng syndrome · bit công bố sau mỗi lần sai (Δ ≥ 16) |
| Loại sớm | 11% | 11% | q_pe vượt ngưỡng thì bỏ khối, không giải |
| δ · d | 10% · 307 | Vị trí đệm có thể chuyển từ punctured sang shortened |  |

Đã thử và không dùng: gộp ước lượng PE với lịch sử ERRCNT (làm hỏng 3–7/54 khối); chọn code ở EFFICIENCY theo cận trên PE (η giảm 0.481 → 0.432).

leak = m − d + r (r = tổng số bit D đã công bố, kể cả r0) R = 1 − leak / (n − d) f = leak / ((n − d) · h(QBER)) → f = 1 là giới hạn Shannon

### e. Cố định lúc tổng hợp

| Tham số | Giá trị | Ảnh hưởng |
| --- | --- | --- |
| `ZC` / `SH_W` | 128 / 7 | Số lane và kích thước khối n = 24·ZC. ZC = 256 không route được (CLS 71%, 5492 net) |
| `APP_W · C2V_W · V2C_W` | 7 · 6 · 8 | APP ±62 (±63 = bit bị khóa); C2V −32..31; V2C −93..94 và mã ±127 |
| Check node | ×0.75 / offset | NMS min − (min >> 2), hoặc offset 3/2/1 đổi ở vòng lặp 10 và 30 (CFG2\[5\]) |
| `NGRP · PIPE_AT` | 16 · 3 | Nhân bản điều khiển shifter và chỉ số cạnh; thanh ghi giữa shifter sau tầng 3 |
| `CTX_W` | 2 | 4 ngữ cảnh khối; CH và SYN RAM sâu 32·2^CTX_W |
| `OUT_REG` (APP, C2V) | 1 | Thanh ghi đầu ra BSRAM, đọc trễ 2 chu kỳ; CH / SGN / SYN trễ 1 |
| Xung nhịp | 70 MHz | `syn/qkd_ir.sdc` 14.286 ns; PnR đạt 70.14 MHz |
| `L_OUT` (PA) | 1024 | Số bit hash mỗi lượt; cửa sổ seed 1056 bit; 8 bit/chu kỳ |

## 8. Kết quả

Hai chỉ số, theo công thức Kprac của Yang et al. (JLT 2020) viết cho DV-QKD, tỉ lệ khóa bí mật tính với khối PA 1 Mbit:

- **η**: số bit bí mật trên mỗi bit khóa thô. Quan trọng khi IR theo kịp nguồn khóa thô.
- **Khóa bí mật khi bão hòa**: Mbit/s khi IR là nút cổ chai (tính ở 100 MHz, 1 ngữ cảnh, mỗi lần thử tốn một lượt hỏi–đáp 100 µs). Ở xung nhịp chốt 70 MHz nhân 0.70; 4 ngữ cảnh nhân thêm khoảng 3.5.

### Chuỗi QBER trôi 1 → 6 → 1% (54 khối)

| Cấu hình | Thành công | f | Lần thử | η | Năng lực IR | Khóa bí mật bão hòa |
| --- | --- | --- | --- | --- | --- | --- |
| basic (10-10) | 54/54 | 1.61 | 2.28 | 0.464 | 7.1 Mbit/s | 3.30 Mbit/s |
| dynamic (10-10) | 54/54 | 1.87 | 1.44 | 0.429 | 12.7 | 5.43 |
| **EFFICIENCY** | 54/54 | 1.50 | 1.69 | **0.481** | 12.1 | 5.81 |
| **THROUGHPUT** | 54/54 | 2.07 | 1.06 | 0.388 | **22.3** | **8.67** |

### Khóa bí mật theo tốc độ khóa thô (Mbit/s)

| Khóa thô | basic 10-10 | dynamic 10-10 | EFFICIENCY | THROUGHPUT | Tự chuyển |
| --- | --- | --- | --- | --- | --- |
| 5 | 2.32 | 2.14 | 2.40 | 1.94 | **2.40** |
| 11 | 3.28 | 4.54 | 5.05 | 4.27 | **5.05** |
| 14 | 3.29 | 5.30 | 5.68 | 5.43 | **5.87** |
| 18 | 3.30 | 5.41 | 5.77 | 6.94 | **7.03** |
| 40 | 3.30 | 5.43 | 5.81 | 8.67 | 8.12 |

Ở 40 Mbit/s, tự chuyển kém THROUGHPUT cố định vì vài khối đầu chạy trước khi hàng đợi kịp dồn; khi chạy lâu dài khoảng chênh này biến mất. Ở RTT 100 µs, phần lớn thời gian mỗi khối là chờ Alice, nên chồng layer chỉ thêm 3–5% khóa bí mật; không tính RTT, THROUGHPUT tăng từ 48.0 lên 58.7 Mbit/s.

### Phiên mô phỏng vật lý, khóa hữu hạn (mỗi phiên ≥ 1.2 Mbit sàng lọc)

`model/gen_qkd_session.py` mô phỏng theo sự kiện: decoy μ = 0.6/0.2/0 (6:1:1) ở 100 MHz, kênh Gamma-Gamma có tương quan thời gian (τc = 5 ms), đầu thu hiệu suất 10%, Y₀ = 2·10⁻⁶, thời gian chết 2 µs, afterpulse 0.5%. QBER do ngân sách suy hao quyết định.

| Mức | QBER | Suy hao | basic 10-10 | EFFICIENCY | THROUGHPUT | bit/s bí mật |
| --- | --- | --- | --- | --- | --- | --- |
| WEAK | 1.58% | 15 dB | 79 792 | **105 472** | 94 693 | 2 776 |
| MILD | 1.72% | 22 dB | 56 860 | **76 588** | 66 880 | 464 |
| MODERATE | 3.19% | 27 dB | 0 | 0 | 0 | 0 (470k sau khi gom 1 h) |
| STRONG · SEVERE | 5.2% · 6.9% | 30 · 32 dB | 0 | 0 | 0 | 0 |

STRONG và SEVERE bằng 0 là đúng: với f ≈ 1.45 mà IR đạt ở QBER 5–7%, tỉ lệ tiệm cận của decoy đã ≤ 0. Muốn có khóa phải đưa f xuống ≤ khoảng 1.25 hoặc giảm Y₀ 4–10 lần (`results/exp_decoy.txt`). Trên RTL, 30 khối của các phiên này đều giải được, khớp từng bit (`results/sessions_rtl.md`); IR nhanh hơn tốc độ khóa thô 500–20 000 lần.

### Trên dữ liệu BB84 của nhóm (16 khối × 2765 bit, chỉ số tiệm cận cũ)

| Cấu hình | Thành công | f | Lần thử | η | Khóa bí mật @ RTT 100 µs |
| --- | --- | --- | --- | --- | --- |
| basic (10-10) | 10/16 | 1.91 | 3.62 | 0.245 | 1.04 Mbit/s |
| dynamic (10-10) | 10/16 | 2.12 | 0.81 | 0.231 | 5.40 |
| EFFICIENCY | 10/16 | 1.55 | 1.06 | **0.265** | 4.52 |
| THROUGHPUT | 10/16 | 2.48 | 0.62 | 0.202 | **7.64** |

6 khối có QBER 11–14% bị loại sớm ở mọi cấu hình mới (BB84 không còn khóa an toàn ở mức này). Không có khối nào báo thành công mà sai key.

### Phần cứng

Logic36%48 584 LUT+ALU · FF 23 840 · CLS 48%

BSRAM135 / 3404 ngữ cảnh và PA không tốn thêm

Xung nhịp chốt70 MHzPnR 70.14 MHz · TNS 0 · biên +0.03 ns

Mô phỏng RTLPASS9 khối + PA; 30 khối / 4 ngữ cảnh, 133 728 chu kỳ

- PnR dùng top đánh giá `syn/qkd_pp_pnr_top.v` (IP có 365 cổng, vượt 292 chân I/O; trong SoC IP nối nội bộ với CPU). Diễn biến Fmax: 65 MHz (bản đầu), 73.5 MHz sau khi thêm thanh ghi đầu ra BSRAM, chốt 70 MHz (`results/pnr_2026-10-24_70mhz/`).
- Thử 85 và 100 MHz bằng tối ưu logic: tổng hợp ước tính 104–111 MHz nhưng router không hội tụ. Chia đôi cho thấy vùng decoder đã sát giới hạn đi dây; chỉ một thay đổi nhỏ ngoài decoder cũng làm kết quả dao động 61–73 MHz. Muốn cao hơn cần bớt dây (shifter 7 bit) hoặc ràng buộc vị trí. Nếu ghép SoC làm mất timing: hạ về 65 MHz.
- Firmware `qkd_pp_driver.c` là mã tham chiếu theo đúng mô hình; DMA, kênh tới Alice và TRNG cần BSP của AE350.

## 9. So với các bài báo

Bài A: IR + PA cho CV-QKD trên Virtex-7. Bài B: QC-LDPC rate-compatible trên ZCU102. Bài C: syndrome encoder phía Alice. Bài D: PA MMH-MH trên NTT, Zynq UltraScale+. Số liệu bài báo lấy từ tài liệu "Post-processing Tuần 1" của nhóm; số liệu hệ thống từ `results/exp_compare.txt` (48 khối mỗi điểm QBER, chế độ EFFICIENCY) và PnR 70 MHz.

| Chỉ số | Bài báo | Hệ thống hiện tại | Đánh giá |
| --- | --- | --- | --- |
| f (hiệu suất IR) | B: 1.0–1.32 | 1.20–1.47 ở QBER 3–8%; 1.6–1.9 ở 1–2% | **Kém hơn 0.2–0.6** |
| Tỉ lệ khối giải được | B: FER 10⁻³ | 88–100% sau khi công bố bit; 0 khối báo sai | Kém hơn; cần đo trên ≥ 10⁴ khối |
| Chu kỳ / (bit · vòng lặp) | B: khoảng 0.092 | 0.065 (r56) – 0.090 (r12) | Bằng hoặc tốt hơn |
| Xung nhịp | B: 250 MHz · C, D: 125 MHz | 70 MHz | Kém hơn |
| Thông lượng IR | B: 136 Mbit/s, không tính RTT | 15–110 Mbit/s (1 ngữ cảnh); khoảng 43 Mbit/s có RTT 100 µs (4 ngữ cảnh) | Thấp hơn do xung nhịp, nhưng nhanh hơn khóa thô 500–20 000 lần |
| Tài nguyên | B (chỉ IR): 26.8k LUT6, 16.7k FF, 82 BRAM36 | IR + PA + 4 ngữ cảnh: 40.7k LUT4 + 7.9k ALU, 23.8k FF, 135 BSRAM18 | Cùng cỡ; chip còn trống khoảng 64% logic |
| PA | D: 1.5 Gbit/s, khối ≤ 768 kbit | Hankel; khối 1–5 Mbit trong ≤ khoảng 2 s | **Không mở rộng được cho khối lớn** |
| Khóa hữu hạn | Thường tính tiệm cận | Decoy hữu hạn (Lim 2014) + gom khối PA tự động | Tốt hơn |

So sánh f và FER không hoàn toàn cùng điều kiện. Bài B chọn rate cố định từ QBER đã biết và đo sau một lần giải. Ở đây f gồm cả các bit công bố thêm trong vòng hỏi–đáp, và QBER chỉ được ước lượng.

### Điểm mạnh

- Hiệu năng mỗi chu kỳ bằng hoặc hơn bài B
- 4 ngữ cảnh che thời gian chờ Alice (×3.48)
- Băm xác minh; RTL khớp từng bit với mô hình
- Tính khóa hữu hạn, tự quyết định EMIT/ABORT

### Điểm yếu

- f cao: QBER 5–7% không ra khóa (f ≈ 1.45, cần ≤ khoảng 1.25)
- PA chưa xử lý được khối 10⁷–10⁸ bit
- Xung nhịp bị giới hạn bởi đi dây của decoder
- Chưa có syndrome encoder phía Alice

## 10. Hướng phát triển

Xếp theo tác động lên lượng khóa bí mật. Hai hướng đầu quyết định có ra khóa ở QBER 3–7% hay không và gần như không đụng tới timing.

| # | Hướng | Lợi ích dự kiến | Chi phí, rủi ro |
| --- | --- | --- | --- |
| 1 | **Code dài hơn, giữ 128 lane:** base matrix 48–96 cột (n = 6 144–12 288), phân bố bậc tối ưu bằng density evolution, đặt cạnh bằng PEG/ACE | f giảm khoảng 0.1–0.2; mở khóa cho QBER 3–5% | RAM sâu hơn, ROM lớn hơn; số lane không đổi nên không thêm dây (ZC = 256 đã không route được). Chu kỳ mỗi khối ×2–4, vẫn dư thông lượng |
| 2 | **Thêm code rate khoảng 0.95** (QBER \< 1%) và **khoảng 0.40** (QBER 8–11%) | f ở 1% từ 1.9 xuống khoảng 1.3; phủ vùng QBER cao | Chỉ mô hình + ROM |
| 3 | **Kiểm tra trên mạch** qua cầu UART từ PC, rồi tích hợp SoC AE350, DMA, kênh cổ điển thật | Số liệu thật; xác nhận timing | Trung bình; cần BSP và toolchain |
| 4 | **PA khối lớn:** MMH-MH/Toeplitz qua NTT, dữ liệu trong DDR3 của board | Khối 10⁷–10⁸ bit, điều kiện cần cho khóa hữu hạn ở QBER ≥ 3% | Lớn: DSP, BSRAM, bộ điều khiển DDR |
| 5 | Syndrome encoder phía Alice, dùng lại shifter và ROM | Một bitstream cho cả hai phía | Nhỏ |
| 6 | Đo FER trên ≥ 10⁴ khối | So trực tiếp với FER 10⁻³ của bài báo | Chỉ thời gian máy |
| 7 | Phía quang: giảm Y₀ 4–10 lần, tối ưu tham số decoy theo cỡ khối | STRONG/SEVERE từ 0 lên trên 100k bit mỗi phiên | Phần cứng thu, ngoài FPGA |
| 8 | Xung nhịp cao hơn: shifter 7 bit, ràng buộc vị trí decoder | ×1.2–1.4 thông lượng IR | Ưu tiên thấp: IR không phải nút cổ chai |

Chi tiết: `results/compare_papers.md`, `DEVLOG.md` (2026-10-22 đến 10-24), `README.md`.
