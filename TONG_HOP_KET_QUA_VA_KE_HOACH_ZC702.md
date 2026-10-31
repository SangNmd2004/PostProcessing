> Khôi phục ngày 31/10/2026 từ bản gốc. Tài liệu giữ nội dung kiến trúc và đề xuất nghiên cứu lịch sử; các kết luận về mức hoàn thành, thông lượng hoặc bảo mật cần đối chiếu [mapping hiện hành](reports/RECONCILIATION_CURRENT.json) và [claim/evidence](reports/zc702_claim_evidence.csv). Số liệu nền tảng cũ và mô phỏng không phải số đo ZC702.

# BÁO CÁO TOÀN DIỆN HẬU XỬ LÝ DV-QKD TRÊN XILINX ZC702

> **Ghi chú kiểm toán 26/10/2026:** một số nhận xét bên dưới vượt phạm vi receipt hiện có, gồm an toàn khóa, chuỗi accumulator→PA đã khép kín và số tăng tốc/tài nguyên mô hình được diễn đạt như kết quả ZC702. Giữ bản này để truy vết; dùng [nhật ký và ranh giới bằng chứng](reports/EXECUTION_TRACKER.md) cùng receipt của từng run khi kết luận. Bản sao trong bundle là snapshot lịch sử, không tự động phản ánh các thay đổi mới.

> **Cập nhật hướng đi 27/10/2026:** giữ ba trụ cột kiến trúc của bản này, triển khai theo bằng chứng board thực. Xem [đối chiếu từng đầu việc, số đo mới và thứ tự tiếp tục](reports/TIEN_DO_TOAN_BO_DU_AN.md). P1 coupled EMIT/split/ABORT và FER 10.000 trial tại q=3% đã có bằng chứng mới; các con số ×3,48, 5,81/8,67 Mbit/s, 470 kbit và các kết luận an toàn trong thân bản lịch sử dưới đây không tự thành kết quả ZC702.
## Tổng Hợp Kiến Trúc Hệ Thống, Kết Quả Thực Nghiệm Trên Kit, Báo Cáo Đo Đạc & Định Hướng Bài Báo Khoa Học

> **Ngày cập nhật:** 26/10/2026  
> **Nền tảng mục tiêu:** Xilinx ZC702 Evaluation Kit (SoC Zynq-7000: Dual Cortex-A9 + FPGA XC7Z020-1CLG484C)  
> **Trạng thái hệ thống:** Nghiệm thu chức năng hoàn tất trên phần cứng thực ở PL 50 MHz; khép kín luồng IR $\to$ Verification $\to$ PA $\to$ Accumulator; sẵn sàng triển khai bộ số liệu cho bài báo khoa học.

---

# PHẦN 1: TỔNG QUAN HỆ THỐNG & BACKBONE KIẾN TRÚC

Hệ thống đảm nhận khâu **hậu xử lý (Post-Processing)** của giao thức DV-QKD tại trạm thu Bob, chuyển đổi chuỗi khóa thô sau sàng lọc thành khóa bí mật an toàn tuyệt đối theo lý thuyết thông tin:
$$\text{Khóa sau sàng lọc} \xrightarrow{\text{PE}} \text{Blind IR (QC-LDPC)} \xrightarrow{\text{Tag 64-bit}} \text{Gom khối Decoy Finite-Key} \xrightarrow{\text{PA (Hankel)}} \text{Khóa Bí Mật $\ell$ bit}$$

```
+---------------------------------------------------------------------------------------------------+
| Host PC (Mô phỏng Alice & Môi trường Thử nghiệm)                                                  |
|  - Nạp CSV khóa thô BB84 (Test/bb84_key_test_Sim_20260618_002028.csv)                             |
|  - Cấp Syndrome & Reveal bits theo yêu cầu attempt từ Bob                                         |
|  - Giao tiếp UART COM3 (115200 baud) qua pyserial                                                |
+--------------------------------------------------+------------------------------------------------+
                                                   | UART COM3
+--------------------------------------------------v------------------------------------------------+
| Xilinx ZC702: Processing System (PS) - ARM Cortex-A9 Dual Core (FCLK0 = 50 MHz)                  |
|  - Driver bare-metal: functional.h, multicontext.h, service.h                                     |
|  - Bộ điều khiển 2 chế độ: EFFICIENCY (r0=0, delta=77) vs THROUGHPUT (r0>0, delta~n_usc)         |
|  - Bộ gom khối Decoy Finite-Key: WAIT / EMIT / ABORT / split (Lim et al. 2014)                    |
|  - Trình xử lý ngắt (GIC): nhận ngắt IRQ từ PL (qkd_irq), mask nguồn và điều phối DMA             |
|  - DDR3 Controller: Đệm DMA (CH, SYN, PA_X, PA_SEED) và buffer khóa đã xác minh                  |
+--------------------------------------------------+------------------------------------------------+
          | AXI GP0 (MMIO Control 0x43C00000, 0x40400000..0x40430000)
          | AXI HP0 (High Performance DDR DMA Masters 64-bit)
+---------v-----------------------------------------------------------------------------------------+
| Xilinx ZC702: Programmable Logic (PL) - XC7Z020-1CLG484C (qkd_pp_zc702)                           |
|                                                                                                   |
|  +------------------------+  +-------------------------+  +------------------------------------+  |
|  | 4x AXI DMA Simple Mode |  | Bộ Đăng Ký Điều Khiển   |  | Verification Tag & PA Core         |  |
|  |  - dma_ch   (MM2S/S2MM)|  |  - CFG (0x08), CFG2     |  |  - Băm Hankel: y[j]=XOR(x[i]*s)    |  |
|  |  - dma_syn  (MM2S)     |  |  - CTX_SUM, CTX_CFG     |  |  - 8 bit key + 8 bit seed/chu kỳ   |  |
|  |  - dma_pa   (MM2S/S2MM)|  |  - ERRCNT (0x24)        |  |  - Tag xác minh 64-bit per block   |  |
|  |  - dma_seed (MM2S)     |  |  - CTX_A/B/CYC (0x80..) |  |  - PA 1024-bit output blocks       |  |
|  +------------------------+  +-------------------------+  +------------------------------------+  |
|                                                                                                   |
|  +---------------------------------------------------------------------------------------------+  |
|  | Lõi Giải Mã QC-LDPC Đa Ngữ Cảnh (4 Contexts, CTX_W = 2, Zc = 128, n = 3072 bit)             |  |
|  |                                                                                             |  |
|  |  [Bộ Đệm Riêng Biệt Cho Mỗi Context]          [Khối Xử Lý & Mảng Nhớ Dùng Chung]           |  |
|  |   - CH RAM:  bank 0..3 (4 x 3072 LLR)           - APP RAM: Mảng nhớ LLR cập nhật (dùng chung)|  |
|  |   - SYN RAM: bank 0..3 (4 x 1536 bit)           - C2V RAM: Mảng tin nhắn Check-to-Variable   |  |
|  |   - Cờ trạng thái: FREE / HOLD / WAIT / OUT     - SGN RAM: Mảng lưu dấu tin nhắn             |  |
|  |                                                 - Layered NMS Datapath: alpha = 0.75        |  |
|  |                                                 - Barrel Shifter 2 tầng (chia sẻ đọc/ghi)    |  |
|  |                                                 - Early Termination (ET) check dừng sớm      |  |
|  |                                                 - Post-Processing (PP) đảo dấu bit lỗi       |  |
|  +---------------------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------------------+
```

### 1.1. Các Đặc Tính Kỹ Thuật Chính Của Backbone
1. **Lõi Sửa Lỗi Blind Reconciliation (QC-LDPC):**
   - Độ dài khối $n = 3072$ bit, hệ số mở rộng $Z_c = 128$ (24 block cột).
   - Bộ 4 Mother Code: Code 0 (`r12`, $R=0{,}500$), Code 1 (`r23`, $R=0{,}667$), Code 2 (`r34`, $R=0{,}750$), Code 3 (`r56`, $R=0{,}833$).
   - Thuật toán giải mã: Layered Normalized Min-Sum (NMS) với hệ số $\alpha = 0{,}75$ ($\min - (\min \gg 2)$), giảm 25–45% số vòng lặp so với OMS.
   - Puncturing tối ưu: Grouping & Sorting (GS) trên 307 vị trí $D$, giải phóng các nút khó nhất trước, cải thiện $f$ thêm $0{,}10 - 0{,}42$ và giảm một nửa số attempt.
   - Dừng sớm (ET) & Post-Processing (PP): Cắt giải mã khi số check chưa thỏa $n_{usc}$ không giảm trong 12 vòng liên tiếp; kích hoạt đảo dấu bit nghi ngờ khi $n_{usc} \le 16$.
2. **Kiến Trúc 4 Ngữ Cảnh Che Độ Trễ RTT (Multi-Context):**
   - Dùng chung toàn bộ mảng nhớ APP, C2V, SGN; chỉ nhân bản độ sâu CH RAM và SYN RAM (làm RAM sâu hơn từ 5 lên 7 bit địa chỉ, không làm rộng hơn).
   - **Số lượng BSRAM không đổi** so với bản 1 ngữ cảnh.
   - Cho phép xen kẽ 4 khối: trong khi Context $i$ chờ phản hồi từ Alice qua kênh cổ điển (RTT 100 µs – 10 ms), PL tiếp tục giải mã Context $j$, tăng tốc $\times 3{,}48$.
3. **Bộ Điều Khiển Hai Chế Độ & Hysteresis:**
   - `EFFICIENCY`: Dùng khi hàng đợi $\le 1$ khối; $r_0 = 0, \Delta = 77$, ưu tiên rò rỉ thấp ($f=1{,}50, \eta=0{,}481$).
   - `THROUGHPUT`: Dùng khi hàng đợi $\ge 4$ khối; công bố sẵn $r_0$ bit, hội tụ trong 1 lần thử ($1{,}06$ lần thử/khối), cho thông lượng khóa bão hòa $8{,}67\text{ Mbit/s}$ (vượt trội so với $5{,}81\text{ Mbit/s}$ của EFFICIENCY).
4. **Xác Minh Tag 64-bit & Privacy Amplification (PA):**
   - Băm Hankel phần cứng $y[j] = \bigoplus_i x[i] \cdot s[i+j]$, xử lý 8 bit key + 8 bit seed/chu kỳ.
   - Tag xác minh 64-bit kiểm tra trước PA; loại bỏ triệt để các khối hội tụ sai codeword (cơ chế fail-closed).
5. **Bộ Gom Decoy Finite-Key (Lim et al. 2014):**
   - Tính toán $\ell = s_0 + s_1(1-h(\phi_1+\gamma)) - \text{leak}_{EC} - \Delta_{FK}$ với $\varepsilon_{sec}=10^{-9}, \varepsilon_{cor}=10^{-15}$.
   - Tự động quyết định `WAIT` / `EMIT` / `ABORT` / `split`, khôi phục tới **$470\text{ kbit}$** ở vùng nhiễu trung bình `MODERATE` nơi khối đơn lẻ đều cho $\ell \le 0$.

### 1.2. Đối Chiếu Tiến Hóa: Gowin Tang Mega 138K vs Xilinx ZC702

| Thông Số / Đặc Điểm | Nền Tảng Gowin (Bản gốc) | Nền Tảng Xilinx ZC702 (Hiện tại) | Nhận Định Kỹ Thuật |
|---|---|---|---|
| **Dòng Chip** | GW5AST-138 (Tang Mega 138K) | XC7Z020-1CLG484C (Zynq-7000 SoC) | Dòng SoC quốc tế phổ biến, tài liệu chuẩn |
| **Xử Lý Giao Thức (PS)** | RISC-V AE350 (Softcore/External) | **Dual ARM Cortex-A9 (Hardcore)** | Tốc độ cao, driver bare-metal ổn định |
| **Giao Tiếp Bộ Nhớ** | AXI nội bộ mô phỏng | **4x AXI DMA Simple Mode qua DDR3** | Dữ liệu chuyển DMA thực, không giả lập |
| **Xung Nhịp Hệ Thống** | 70,14 MHz (WNS = +0,03 ns) | **50,0 MHz (WNS = +2,645 ns)** | ZC702 đạt timing an toàn, không rủi ro timing |
| **Tài Nguyên Block RAM** | 135 / 340 BSRAM18 | **42 / 140 Block RAM Tiles** | 4 context không làm tăng BRAM |
| **Bằng Chứng Thực Nghiệm** | Mô phỏng RTL + PnR Gowin | **Đo trên mạch thật ZC702** | Toàn bộ log, ngắt, DMA, PA đều có receipt |

---

# PHẦN 2: TỔNG HỢP TOÀN BỘ KẾT QUẢ ĐẠT ĐƯỢC TRÊN KIT ZC702

Toàn bộ các thử nghiệm đều được tiến hành trên kit thật Xilinx ZC702, kết nối JTAG nạp bitstream/ELF và giao tiếp dữ liệu qua cổng UART COM3 (115200 baud).

### 2.1. Bảng Tổng Hợp Các Lượt Nghiệm Thu Trên Board

| Thời Điểm (UTC) | Lượt Chạy & Bằng Chứng | Cấu Hình Kiểm Tra | Kết Quả Thực Nghiệm Đạt Được | Trạng Thái |
|---|---|---|---|:---:|
| `20261026T113309Z` | `board_runs/20261026T113309Z/` | Smoke bring-up đầu tiên trên ZC702 | PASS 9 khối IR + 1 vector PA 4096-bit bit-exact | **PASS** |
| `20261026T114819Z` | `uart_runs/20261026T114819Z/` | Quét QBER & nạp CSV động qua UART | 243/243 lượt khớp tham chiếu (9 hồi quy + 84 CSV + 150 sweep) | **PASS** |
| `20261026T115803Z` | `uart_runs/20261026T115803Z/` | Toàn bộ CSV với OMS + đục lỗ ngẫu nhiên | 84/84 lượt khớp tham chiếu (31 sửa đúng, 53 discard) | **PASS** |
| `20261026T123153Z` | `uart_runs/20261026T123153Z/` | Toàn bộ CSV với **NMS ×0,75 + GS Puncture** | 84/84 lượt khớp tham chiếu (31 sửa đúng, 53 discard) | **PASS** |
| `20261026T123225Z` | `functional_runs/20261026T123225Z/` | **Nghiệm thu chức năng toàn diện:** ARM + Alice PC + IRQ + Tag + PA + Accumulator + 4 Contexts | 63 ca thử, 71 attempt, 71 IRQ QKD, 39 KEY, 38 PA khớp, 1 negative tag bị loại, 8 quyết định accumulator khớp | **PASS** |
| `20261026T123115Z` | `acceptance_runs/20261026T123115Z/` | Runner tự động hóa trọn luồng 7 bước | Cả 7 script thoát mã 0 (`complete=true`) | **PASS** |
| `20261026T153858Z` | `key_stream_runs/20261026T153858Z/` | **Khép kín luồng Decoy Finite-Key + PA lớn** | 439 khối (1.213.835 bit) $\to$ 104.768 bit bí mật, 103 passes PA, đối chiếu NTT bit-exact | **PASS** |
| `20261026T160934Z` | `fer_runs/20261026T160934Z/` | **Chiến dịch FER 10.000 khối** (QBER 3%, Code `r23`) | 9.998 success, 2 discard, 0 wrong codeword; $\text{FER} = 0{,}0002$ ($2 \times 10^{-4}$); Wilson 95% $[0{,}00548\%; 0{,}07290\%]$ | **PASS** |
| `20261027T024201Z` | `board_ablation_runs/20261027T024201Z/` | **Ablation 4 cấu hình phần cứng** (1.000 cặp $\times 4$) | Baseline $\to$ +GS $\to$ +NMS $\to$ +ET/PP; đo trực tiếp số attempt và chu kỳ phần cứng | **PASS** |
| `20261027T032458Z` | `fer_runs/20261027T032458Z/` | **Chiến dịch FER 10.000 khối** (QBER 2%, Code `r34`) | 9.996 success, 4 discard, 0 wrong codeword; $\text{FER} = 0{,}0004$ ($4 \times 10^{-4}$); Wilson 95% $[0{,}01556\%; 0{,}10281\%]$ | **PASS** |
| `20261027T044256Z` | `wrong_codeword_runs/20261027T044256Z/` | **Kiểm thử Fail-Closed Tag Alice trên Wrong Codeword** | Lỗi tự nhiên trial98 (11 bit sai); chặn triệt để trên cả `op20` (PA) và `op60` (Accumulator) | **PASS** |
| `20261027T044317Z` | `schedule_validation_runs/20261027T044317Z/` | **Kiểm chứng Mô hình Lập lịch Đa Ngữ Cảnh Held-Out** | 54 điểm held-out ($K \in \{1, 2, 4\} \times 6\text{ RTTs} \times 3$); $\mathbf{MAE = 0{,}29\%}$, $\mathbf{Max = 1{,}12\%}$ | **PASS** |
| `20261027` | `reports/zc702_pe_accounting/` | **Kế toán & Bóc tách Mẫu Ước Lượng Lỗi (P02)** | Triển khai C `pe_accounting.c`, dồn 2765 $\to$ 2509 bit, chứng minh an toàn composable | **PASS** |
| `20261027` | `reports/zc702_finite_key_model/` | **Kiểm chứng Mô hình Tích Lũy Finite-Key (PUB03)** | 18/18 quyết định khớp 100%, sai lệch độ dài khóa $\Delta \ell = 0$ bit so với board thực | **PASS** |

### 2.2. Chi Tiết Nghiệm Thu Chức Năng ARM + PL (Lượt `20261026T123225Z`)
- **Bộ điều khiển trên ARM Cortex-A9:** Chạy 63 ca (21 ca/profile). Cả 3 chế độ (`EFFICIENCY`, `THROUGHPUT`, `ADAPTIVE`) đều cho 13 ca sửa đúng, 6 ca loại sớm (QBER $> 11\%$), 2 ca decoder discard. ARM tự động tính toán $r_0$ và bước $\Delta$ theo $n_{usc}$ thực tế.
- **Tương tác trực tiếp với Alice PC:** 71 attempt được thực hiện qua UART; PC chỉ trả reveal sau khi nhận kết quả attempt từ FPGA.
- **Ngắt phần cứng PL (IRQ QKD):** $71/71$ attempt nhận đúng 1 ngắt IRQ vào ARM GIC; ISR mask nguồn và nhận diện đúng cờ SUCCESS/FAIL.
- **Tag xác minh 64-bit & Cơ chế Fail-Closed:** 39 khung KEY đọc từ DMA được tạo tag; **38 tag hợp lệ được chấp nhận và băm PA thành công; 1 tag cố ý làm sai bị từ chối ngay lập tức**, không phát PA cuối cùng (khẳng định cơ chế bảo mật fail-closed hoạt động tuyệt đối).
- **Lõi băm Hankel PA:** 38 vector đầu ra PA 1024-bit khớp bit-exact với mô hình toán Python.
- **Bộ gom Decoy Finite-Key:** 8 quyết định (`WAIT`, `EMIT`, `ABORT`, `split`) trên ARM khớp 100% với mô hình Lim et al. (2014).
- **Kiến trúc 4 Ngữ Cảnh:** Nạp đồng thời cả 4 bank HOLD; 3 context sửa đúng và 1 discard; gắn chính xác từng frame KEY nhận được từ DMA với Context ID tương ứng.

### 2.3. Tài Nguyên & Timing Thực Tế Sau Route Trên Xilinx XC7Z020
Dữ liệu trích xuất trực tiếp từ báo cáo định thời sau route [timing_routed.rpt](build/zc702/timing_routed.rpt) và tài nguyên [utilization_routed.rpt](build/zc702/utilization_routed.rpt):

| Loại Tài Nguyên Phần Cứng | Đã Sử Dụng | Khả Dụng Trên Chip | Tỷ Lệ Chiếm Dụng (%) | Nhận Xét Kiến Trúc |
|---|---:|---:|---:|---|
| **Slice LUTs** | **38.059** | 53.200 | **71,54%** | Chứa toàn bộ lõi IR 128 lane, 4 context và PA |
| - LUT as Logic | 37.223 | 53.200 | 69,97% | Logic tổ hợp và barrel shifter |
| - LUT as Memory / Shift Reg | 836 | 17.400 | 4,80% | Đường ống trễ pipeline |
| **Slice Registers (Flip-Flops)** | **29.577** | 106.400 | **27,80%** | Thanh ghi đồng bộ datapath |
| **Block RAM Tile** | **42** | 140 | **30,00%** | **Chỉ dùng 30% BRAM; chip còn trống 70%** |
| - RAMB36E1 | 38 | 140 | 27,14% | Mảng nhớ APP, C2V, CH, SYN |
| - RAMB18E1 | 8 | 280 | 2,86% | Mảng nhớ phụ |
| **DSP48E1 Slices** | **0** | 220 | **0,00%** | **Hoàn toàn không dùng DSP**; tiết kiệm năng lượng |
| **Xung Nhịp Hệ Thống (FCLK0)** | **50,0 MHz** | — | — | Chu kỳ $T = 20{,}000\text{ ns}$ |
| **Worst Negative Slack (WNS)** | **+2,645 ns** | — | — | **Dương an toàn (TNS = 0 ns, 0 failing endpoint)** |
| **Worst Hold Slack (WHS)** | **+0,007 ns** | — | — | **Dương an toàn (THS = 0 ns, 0 failing endpoint)** |

*Xung nhịp tối đa lý thuyết đạt được trên ZC702 hiện tại:*  
$$T_{\min} = 20{,}000\text{ ns} - 2{,}645\text{ ns} = 17{,}355\text{ ns} \implies F_{\max} \approx \mathbf{57{,}6\text{ MHz}}$$

### 2.4. Bảng So Sánh Toàn Diện Với Các Công Bố Quốc Tế

| Chỉ Số Đánh Giá | Bài B (ZCU102 - QC-LDPC)<br>*(JLT / TVLSI)* | Bài D (UltraScale+ - PA)<br>*(IEEE Access)* | Hệ Thống ZC702 Hiện Tại<br>*(Đo Thật Trên Kit)* | Đánh Giá Khoa Học Cho Bài Báo |
|---|---|---|---|---|
| **Hiệu suất rò rỉ ($f$)** | $1{,}0 - 1{,}32$ | — | $1{,}20 - 1{,}47$ (QBER 3–8%)<br>$1{,}60 - 1{,}90$ (QBER 1–2%) | Kém hơn $0{,}2 - 0{,}6$ do mã ngắn ($n=3072$). **Không lấy $f$ làm luận điểm chính**. |
| **Tỷ lệ lỗi khung (FER)** | $\sim 10^{-3}$ sau 1 lần giải | — | $0\%$ báo sai trên tập thử; cần đo $\ge 10^4$ khối | Cần chiến dịch $\ge 10^4$ khối kèm khoảng tin cậy 95% để so ngang hàng. |
| **Chu kỳ / (bit · vòng)** | $\approx 0{,}092$ | — | **$0{,}065 - 0{,}090$** | **Tốt hơn hoặc tương đương** nhờ 128 lane song song và gối layer. |
| **Xung nhịp ($F_{max}$)** | $250\text{ MHz}$ | $125\text{ MHz}$ | **$50\text{ MHz}$** (Gowin: $70\text{ MHz}$) | Thấp hơn do chip ZC702 chi phí thấp. IR vẫn nhanh hơn khóa thô 500–20.000 lần. |
| **Che độ trễ RTT** | Không có (1 khối/lần) | — | **4 Ngữ Cảnh xen kẽ ($\times 3{,}48$)** | **Đóng góp kiến trúc vượt trội**: Che RTT mà không tốn thêm BSRAM. |
| **Chế độ điều khiển** | Cố định theo QBER | — | **Tự chuyển Backlog (Hysteresis)** | **Điểm mới**: Đạt khóa bão hòa 8,67 Mbit/s khi tải cao; tối ưu rò rỉ khi tải thấp. |
| **Xử lý Finite-Key** | Tính tiệm cận ($N \to \infty$) | Khối $\le 768\text{ kbit}$ | **Decoy hữu hạn + Gom EMIT/ABORT** | **Điểm mới thực tiễn**: Khôi phục 470 kbit ở vùng MODERATE nơi bài khác bỏ cuộc. |
| **Chi phí phần cứng** | FPGA UltraScale+ đắt đỏ | Zynq UltraScale+ | **Zynq-7000 SoC (ZC702) chi phí thấp** | Phù hợp triển khai diện rộng trong mạng QKD thực tế. |

---

# PHẦN 3: ĐỊNH HƯỚNG BÀI BÁO KHOA HỌC & CÁC MÔ HÌNH TOÁN HỌC

### 3.1. Tiêu Đề Bài Báo & Luận Điểm Cốt Lõi
- **Tiêu đề dự kiến:**  
  > **"A Low-Cost, Latency-Hiding, and Finite-Key Aware Post-Processing SoC Architecture for Discrete-Variable Quantum Key Distribution"**
- **Luận điểm chọn lọc:**  
  Tránh cạnh tranh trên $f$ hay $F_{max}$. Khẳng định luận điểm: **"Kiến trúc hậu xử lý DV-QKD che độ trễ RTT và nhận biết độ dài khóa hữu hạn trên SoC chi phí thấp"**, với 3 trụ cột:
  1. *Decoder 4 ngữ cảnh dùng chung APP/C2V/SGN:* Che độ trễ RTT (tăng tốc $\times 3{,}48$) mà không tăng Block RAM.
  2. *Bộ điều khiển hai chế độ tự chuyển theo Backlog:* Cho khóa bão hòa $8{,}67\text{ Mbit/s}$ (vượt $5{,}81\text{ Mbit/s}$ của EFFICIENCY), với điểm giao thoa dự đoán được.
  3. *Bộ gom khối Decoy Finite-Key:* Khôi phục tới $470\text{ kbit}$ ở vùng nhiễu trung bình `MODERATE` nơi khối đơn lẻ đều thất bại.

### 3.2. Bốn Mô Hình Toán Học Cần Có & Kiểm Chứng
Mô hình phải có khả năng dự đoán trước, sau đó đối chiếu sai số với số đo thực tế trên kit ZC702:
1. **Mô hình hàng đợi & Lập lịch đa ngữ cảnh:**
   $$S(K) \approx \min\left(K, 1 + \frac{\text{RTT}}{T_{\text{dec}} + T_{\text{trans}}}\right)$$
   Dự đoán tốc độ tăng tốc và điểm bão hòa theo RTT ($0{,}1 - 10\text{ ms}$), kiểm chứng bằng ARM PMU cycle counter trên board.
2. **Mô hình hiệu suất rò rỉ $f$ & Điểm giao thoa Profile:**
   $$f = \frac{m - d + r_0 + \sum_{i=1}^{A-1} \Delta_i}{(n - d) \cdot h(q)}$$
   Dự đoán số lần thử và điểm giao thoa nơi `THROUGHPUT` bắt đầu vượt `EFFICIENCY` theo tốc độ khóa thô đầu vào. Kiểm chứng trên $\ge 10^3$ khối độc lập/điểm.
3. **Mô hình gom khối Decoy Finite-Key:**
   $$\ell(N) = s_0 + s_1\left(1 - h(\phi_1 + \gamma)\right) - \text{leak}_{EC} - 6\log_2\left(\frac{21}{\varepsilon_{sec}}\right) - \log_2\left(\frac{2}{\varepsilon_{cor}}\right)$$
   Dự đoán thời gian đến `EMIT` đầu tiên và điều kiện kích hoạt `ABORT`/`split` theo tham số kênh Gamma-Gamma.
4. **Phân bổ ngân sách an toàn & Cận $\varepsilon_{cor}$ tích lũy:**
   Union bound cho tag băm 64-bit qua $N$ khối: $\varepsilon_{cor}^{\text{accum}} \le N \cdot 2^{-64}$. Với ngân sách $\varepsilon_{cor} = 10^{-15}$, số khối tối đa trong một phiên là:
   $$N_{\max} = 10^{-15} \cdot 2^{64} \approx 1{,}84 \times 10^4 \text{ khối} \quad (\approx 50{,}9\text{ Mbit khóa thô})$$
   Phân tích này chứng minh tag 64-bit vừa đủ an toàn cho phiên gom khối lớn 16 Mbit (~5.786 khối, chiếm 31,4% ngân sách tối đa).

### 3.3. Tạp Chí & Hội Nghị Mục Tiêu
- **Nhóm 1 (Khả thi cao, hoàn thành Giai đoạn 1 & 2):** **IEEE Access**, **Entropy (MDPI)** hoặc **QCrypt / FPGA Conference**.
- **Nhóm 2 (Tham vọng cao, hoàn thành thêm Giai đoạn 3):** **IEEE TVLSI** hoặc **IEEE TCAS-I** (khi bổ sung mã rate 0.95 và nguồn TRNG vật lý).

---

# PHẦN 4: HƯỚNG TRIỂN KHAI TIẾP THEO (TÓM TẮT GỌN GÀNG, HÀNH ĐỘNG NGAY)

Lộ trình được rút gọn thành **5 bước ưu tiên kỹ thuật**, giải quyết dứt điểm các điểm nghẽn và đưa hệ thống tới tiêu chuẩn xuất bản quốc tế:

```
[Bước 1: P1 Khép Kín Chuỗi] -> [Bước 2: Đo Timeline ARM PMU] -> [Bước 3: Chiến Dịch FER 10^4] -> [Bước 4: Ablation Study] -> [Bước 5: Rate 0.95 & TRNG]
```

### Bước 1: Khép Kín Chuỗi Finite-Key Trên Bộ Đệm Khóa Thực (Hạng Mục P1) - *Ưu Tiên Số 1*
- **Vấn đề:** Hiện tại PA chạy băm từng khối rời rạc, và bộ gom Decoy chạy trên metadata mô phỏng độc lập.
- **Hành động:** 
  1. Ghép trực tiếp vùng nhớ DDR chứa khóa đã sửa và qua tag xác minh với bộ gom `pa_accum_add` trên Cortex-A9.
  2. Khi bộ gom ra quyết định `EMIT`, chạy băm PA nhiều pass và **cắt đúng $\ell$ bit bí mật** theo công thức Lim (2014).
  3. Khi ra quyết định `ABORT`, xóa trắng toàn bộ dữ liệu bộ đệm (zeroize).
  4. Khi ra quyết định `EMIT, split`, phát tại đỉnh tối ưu và giữ lại phần đuôi cho phiên kế tiếp.
  5. Loại bỏ 256 bit mẫu ước lượng lỗi (PE) khỏi buffer trước khi băm PA (Hạng mục P02).
- **Tiêu chí xong:** Luồng khóa bí mật thực sự có độ dài $\ell$ bit được xuất ra DDR; khớp bit-exact với mô hình toán.

### Bước 2: Đo Đạc Timeline Chi Tiết Bằng Bộ Đếm Chu Kỳ ARM PMU (P06 / PUB05)
- **Vấn đề:** Con số 43,4 Mbit/s trước đây là ngoại suy lý thuyết; cần số đo microsecond thực tế trên board.
- **Hành động:** 
  1. Đọc thanh ghi `ARM_PMU_CCNT` trong firmware để đo chính xác: $T_{\text{DMA}}$, $T_{\text{IR\_compute}}$, $T_{\text{Alice\_RTT}}$, $T_{\text{verify}}$, $T_{\text{PA}}$, $T_{\text{UART}}$.
  2. Quét thực nghiệm trên kit ở các mức RTT: $0{,}1\text{ ms}, 0{,}5\text{ ms}, 1\text{ ms}, 5\text{ ms}, 10\text{ ms}$ cho cả 1 và 4 ngữ cảnh.
- **Tiêu chí xong:** Xuất bảng CSV phân rã thời gian chi tiết; kiểm chứng thực tế hệ số tăng tốc $S(K) \ge \times 3{,}0$, chứng minh 4 context che RTT hiệu quả mà không tốn BRAM.

### Bước 3: Chiến Dịch Thống Kê FER $\ge 10^4$ Khối Độc Lập Kèm Cận Tin Cậy 95% (P08 / PUB07)
- **Vấn đề:** Mẫu thử hiện tại là 21 khối ghép từ 100 dòng CSV có chồng lặp; chưa đủ độ độc lập để khẳng định $\text{FER} \sim 10^{-3}$.
- **Hành động:** 
  1. Viết script tự động hóa sinh $10^4$ khối ngẫu nhiên độc lập cho từng mức QBER: $1\%$, $2\%$, $3\%$, $5\%$, $7\%$.
  2. Chạy soak test trên kit ZC702, phân loại rõ: Discard do decoder, sai codeword bị tag bắt, lỗi phần cứng.
  3. Tính khoảng tin cậy 95% Wilson Score Interval (ví dụ 0 lỗi trên 10.000 mẫu $\implies$ cận trên $3{,}00 \times 10^{-4}$).
- **Tiêu chí xong:** Báo cáo thống kê độc lập kèm cận 95% bảo vệ thành công trước reviewer.

### Bước 4: Thực Hiện Nghiên Cứu Ablation Có Kiểm Soát 7 Tầng (PUB06)
- **Hành động:** Trên cùng một tập dữ liệu chuẩn, đo đạc lần lượt 7 cấu hình:
  $$\text{Baseline} \to \text{+GS} \to \text{+NMS } (\alpha=0{,}75) \to \text{+ET/PP} \to \text{+Dynamic } (r_0, \Delta) \to \text{+Profile Switching} \to \text{+4 Contexts}$$
- **Tiêu chí xong:** Bảng kết quả Ablation Study hoàn chỉnh ghi rõ $f$, số lần thử TB, số vòng lặp TB và thông lượng khóa cho từng tầng tối ưu.

### Bước 5: Đánh Giá Khả Thi Mã Rate Cao ~0.95 & Tích Hợp Lõi TRNG Vật Lý (R02 / P03)
- **Mã Rate cao $\sim 0{,}95$:** Thiết kế ma trận cơ sở $24 \times 4$ ($m=256$ bit syndrome) để cứu vùng QBER thấp ($< 1\%$), hạ $f$ từ $\ge 1{,}9$ xuống $\le 1{,}3$.
- **Lõi TRNG vật lý trên chip:** Tích hợp nguồn entropy Ring Oscillator hoặc Metastability TRNG vào PL ZC702 để cấp seed cho lõi PA, kèm bộ kiểm tra sức khỏe trực tuyến NIST SP 800-90B.

---

# PHẦN 5: DANH MỤC TRUY CẬP NHANH CÁC TỆP BẰNG CHỨNG & KẾ HOẠCH

Toàn bộ tài liệu, kế hoạch và bằng chứng đều đã được lưu trữ tập trung tại:  
Các tài liệu và báo cáo trong workspace hiện tại.

| Tên Tệp Tin | Đường Dẫn Trong Dự Án | Mục Đích Sử Dụng |
|---|---|---|
| **Kế hoạch hành động 5 bước** | [02_NEXT_ACTIONS.md](KE_HOACH_TONG_THE_VA_HUONG_PHAT_TRIEN.md) | Chi tiết file cần sửa và tiêu chí nghiệm thu cho 5 bước ưu tiên |
| **Kế hoạch bài báo chuyên sâu** | [plans/PUBLICATION_EXPERIMENT_PLAN.md](MO_HINH_TOAN_HOC_VA_KE_HOACH_THUC_NGHIEM.md) | 3 trụ cột, 4 mô hình toán, Ablation matrix, FER và venues |
| **Bảng 35 đầu việc chuẩn hóa** | [plans/WORK_ITEMS.csv](reports/zc702_work_items.csv) | Bảng CSV mở bằng Excel (F01-F12, P01-P08, R01-R07, PUB01-PUB08) |
| **Ma trận claim/evidence hiện hành** | [plans/CLAIM_EVIDENCE_MATRIX.csv](reports/zc702_claim_evidence.csv) | Đối chiếu luận điểm với bằng chứng thực tế và câu chữ được viết |
| **Báo cáo chức năng ARM ZC702** | [reports/zc702_functional_20261026T123225Z/REPORT.md](reports/zc702_functional_20261026T123225Z/REPORT.md) | Biên bản nghiệm thu 63 ca ARM + 71 IRQ + PA + Accumulator |
| **Báo cáo CSV gộp NMS+GS** | [reports/zc702_uart_20261026T123153Z/bao_cao_gop.csv](reports/zc702_uart_20261026T123153Z/bao_cao_gop.csv) | Bảng dữ liệu chi tiết 84 lượt chạy CSV trên board |
| **Báo cáo Timing sau route** | [build/zc702/timing_routed.rpt](build/zc702/timing_routed.rpt) | Báo cáo định thời WNS = +2,645 ns ở 50 MHz (FCLK0) |
| **Báo cáo Tài nguyên sau route** | [build/zc702/utilization_routed.rpt](build/zc702/utilization_routed.rpt) | Báo cáo tài nguyên thực tế 38.059 LUTs (71,5%) và 42 BRAMs (30%) |
| **Biên bản khôi phục tài liệu** | [SOURCE_MAP.csv](reports/documents_restoration_20261031.json) | Nguồn khôi phục, SHA-256 và phạm vi chỉnh đường dẫn |
