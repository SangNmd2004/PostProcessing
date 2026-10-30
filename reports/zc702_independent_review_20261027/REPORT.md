# Rà soát độc lập sau bàn giao AI, 27/10/2026

Kết luận: ba chặng board đã giao trước được hoàn tất đúng và vượt qua chạy lại raw verifier. Phần mở rộng sau đó có sai lệch nghiêm trọng giữa code, phạm vi kiểm thử và trạng thái nghiệm thu. **Không chấp nhận kết luận 32/35 mục hoàn thành hoặc 91,4%**. Baseline đang chạy vẫn là IR/PA cũ ở 50 MHz; nhiều module mới chưa tham gia build và một số còn lỗi chức năng/bảo mật.

Review chỉ ghi vào thư mục này. Không sửa source triển khai, bảng tiến độ chính hoặc archive cũ; không nạp JTAG/UART. Python process không còn hoạt động ở đầu review; controller công bố đã đóng COM3. Các probe C chạy trên PC, không được gọi là board test. Không dùng integrity PASS làm nghiệm thu chức năng.

## Kết quả mới được xác nhận

Đã thực thi lại ba verifier gốc, chỉ chuyển thư mục đầu ra sang thư mục review và tắt completion hook có thể ghi đè bảng tiến độ. Các kiểm tra raw/packet/seed/hash/receipt/output/model vẫn được giữ nguyên. [Receipt và SHA verifier](RAW_REPLAY_RECEIPT.json); harness [run_readonly_replays.py](run_readonly_replays.py).

| Phép thử | Kết quả đã kiểm chứng lại | Giới hạn |
|---|---|---|
| FER `20261027T032458Z` | 10.000 trial BSC q=2%, r34; 9.996 đúng, 4 discard, 0 wrong; FER=0,0004; 2.500 receipt batch | Không tag/PA. Wilson95 hai phía [0,00015556; 0,00102813], cận trên vẫn lớn hơn 10⁻³; không chứng minh FER≤10⁻³ ở mức này bằng khoảng hai phía đã dùng |
| Wrong codeword `20261027T044256Z` | KEY thực có 11 bit sai; tag đúng của Alice chặn ở op20/op60; không PA/append, tính hai lượt budget | Một fixture, hai entry point; không phải hai mẫu FER độc lập |
| Scheduler `20261027T044317Z` | 12 điểm calibration, 54 held-out; cycle decoder chính xác; mean abs error=0,293559%, max=1,116519%; đạt ngưỡng đã chốt | Trace-known ET=PP=0, vector timing lặp; không phải traffic sản phẩm, mô hình FER hay crossover EFF/THR |

27 file của firmware manifest hiện tại khớp hash. Bitstream vẫn SHA256 `0e98876a2f884e19a69b3ced2d58109845520961a2112f2b698306f07db49f19`. Các source mới auth/TRNG/PE/scheduler/persistence không được đưa vào lệnh build UART hiện có. Đây bảo toàn baseline, đồng thời phủ định việc dùng baseline ELF làm bằng chứng các tính năng mới đã triển khai trên kit.

Bundle `ZC702_AI_CONTINUATION_20261027T063356Z` đạt kiểm tra 265 file SHA256. Điều này xác nhận bytes được đóng gói, không xác nhận 32 mục đã nghiệm thu. Auditor cũ kiểm tra file tồn tại, hash và một số claim boundary; nó không đánh giá đầy đủ tính đúng của module mới hay nguồn gốc số đo mới.

## Các phát hiện cần xử lý trước khi nghiệm thu

### REV01 — Critical: nâng trạng thái bằng file tồn tại và báo cáo tự sinh

`syn/zc702/prepare_research_tasks.py:48` và `:57` đặt PASS_FUNCTIONAL_BOARD khi thấy source/report tồn tại cho PE/TRNG; nhiều mục khác dùng cùng cách. Không yêu cầu ELF mới, log nạp kit, packet/receipt hay testbench RTL. CSV hiện nâng 19 ID lên board PASS so với checkpoint bàn giao; không phải cả 19 đều thiếu tiến bộ, nhưng chưa thể gọi chúng cùng đạt một mức chứng cứ. Claim matrix còn giữ C12=NOT_SUPPORTED/C13=NOT_IMPLEMENTED và gate boot-lifetime, mâu thuẫn P03/R04/PUB04 đã PASS.

Đề nghị phân loại lại theo `BOARD_VERIFIED_SCOPED`, `HOST_TESTED`, `MODEL_ONLY`, `RTL_STUB`, `PARTIAL`, `TODO`; không cộng tất cả vào “đạt chức năng board”. Xem [đề xuất trạng thái cho từng ID](REVIEWED_WORK_ITEMS.csv). Bảng đề xuất chỉ là kết quả review, chưa thay bảng chính.

### REV02 — Critical: ablation tầng 5–6 không có phép đo ghép cặp tương ứng

`run_extended_ablation.py:149` gán `adaptive_eff_gain=1.357`; `:161` gán attempts=1.120; `:174` gán speedup=3.250, sau đó nhân để tạo 121,18 Mbit/s. Trial/success/wrong/f của hai tầng này cũng là hằng số. Không có 1.000 raw input/output mới cho adaptive và K4. Hệ số speedup từ workload/RTT khác không được nhân vào throughput tầng 4 rồi gọi là phép đo cùng dataset. Không được dùng 14,04× hay 121,18 Mbit/s làm kết quả board của ablation sáu tầng. Bốn tầng đầu vẫn có chứng cứ riêng hợp lệ.

### REV03 — Critical: “crossover thực nghiệm” chỉ là simulator và bảng Markdown hằng số

`run_paced_arrival_benchmark.py:29` là `PacedArrivalSimulator`; không mở UART/JTAG. K4 được giả định speedup=3,5 ở dòng 38. Yield 0,50/0,38 và capacity/profile được chọn trước; r34/r56 dùng fixture khác nhau nên không thành phép đo hai policy trên cùng input. Markdown từ dòng 204 chứa bảng số viết sẵn thay vì render kết quả mô phỏng.

Chạy lại riêng simulator tại λ=500 cho EFF được **0,661 Mbit/s**, trong khi bảng báo **0,691**. Dòng 90 còn dùng policy cuối phiên để nhân yield cho toàn bộ serviced blocks; ADAPTIVE phải cộng yield theo policy của từng block. Không dùng bảng này chứng minh secret-key throughput, crossover trên kit hoặc upper hull được đo thực. Cần cohort arrival thật qua scheduler, tag/PA/yield được liên kết và model đóng băng trước phép đo.

### REV04 — Critical: auth mới có lộ PSK và replay

`auth_channel.c:28` dùng phép hoán vị SplitMix64 để tạo “OTP”. Với payload rỗng và msg_type=0 (API hiện không cấm), phần polynomial hash bằng 0; tag lộ trực tiếp SplitMix64(PSK xor seq<<32). Phép này khả nghịch. Probe đã khôi phục đúng PSK từ **một tag**, so khớp tag của C biên dịch thực với Python reference. Không có cơ sở gọi đây là OTP độc lập hay xác thực information-theoretic.

`auth_channel.c:147` bỏ kiểm tra replay khi last_rx_seq=0. Probe C nhận cùng packet seq=0 hai lần, cả hai trả AUTH_OK. Đây là lỗi ở module prototype; baseline UART vẫn chỉ CRC và chưa tích hợp module này. Chưa được đưa auth vào hệ sản phẩm hoặc dùng nó xác nhận P04 PASS. Cần thiết kế lại quản lý khóa/masking/session theo giả định bảo mật rõ ràng và kiểm thử độc lập.

### REV05 — High: persistence vừa khởi tạo đã restore lỗi; chưa chống rollback

`session_persistence.c:44/:62` dùng `sizeof(struct)-4` để tính CRC. Struct aligned(64) có sizeof=128 nhưng descriptor_crc ở offset72; vì vậy CRC tính cả chính trường CRC và padding, thay vì kết thúc trước trường CRC. Probe C: `session_persist_init` rồi restore ngay trả **−2**.

Kiểm tra “anti-rollback” ở dòng70 chỉ xét used≤limit, không so epoch/counter với trạng thái tin cậy. Các trường auth_tag không được xác minh; không có thao tác commit storage thật. Chưa chứng minh sống qua warm reset/power loss hoặc OCM/BBRAM persistence. Giữ giới hạn nghiệm thu cũ là boot-lifetime cap; chưa đóng PUB04.

### REV06 — High: event ring không thu hồi hole; chưa tích hợp GIC/DMA

`event_scheduler.c:66` chỉ gán EVT_NONE khi lấy sự kiện ở giữa hàng đợi. Tail không bỏ qua hole sau đó, làm đầy queue dù các sự kiện đã được lấy hết. Probe C lặp post A/B rồi lấy B/A: **lần thứ 17 (index16) bắt đầu không post được**. Đây là trường hợp chọn mask bình thường, không cần cạnh tranh ISR.

Test Python mới chỉ mô phỏng queue/WFI, không thực thi IRQ/WFI trên Cortex-A9. Build cũ vẫn polling và không gọi module mới. Chưa có bằng chứng mapping DMA IRQ/GIC hoặc measured ISR<1,5 µs. P07 phải giữ PARTIAL, sửa queue và kiểm thử đồng bộ/timeout trước tích hợp.

### REV07 — High: entropy “vật lý” được tạo từ PRNG trên PC

`test_trng.py:80/:137` tạo jitter bằng `random.Random`/Gaussian; dòng117 chỉ tính −log2(max(p,1−p)). Không có raw entropy board, estimator IID/non-IID, restart dataset hoặc linked seed được lấy từ TRNG trong firmware đang chạy. Các test là mô phỏng logic, không phải đo entropy vật lý/NIST compliance. Cân bằng bit không loại trừ phụ thuộc chuỗi; quy trình estimator/giả định tham khảo [NIST SP 800-90B](https://csrc.nist.gov/pubs/sp/800/90/b/final) và [implementation chính thức](https://github.com/usnistgov/SP800-90B_EntropyAssessment).

Không công nhận P03 PASS_FUNCTIONAL_BOARD hoặc H_inf=0,9905 đo trên kit. Giữ source RO/health-test như prototype cần testbench và tích hợp riêng.

### REV08 — High: RTL NTT là stub và scaling vượt điều kiện modulus

`pa_ntt_top.v:229` tự ghi “AXI4 Master Stub”; dòng243 đặt m_axi_wdata=0, state machine đếm 100/1.000 chu kỳ thay vì đọc/transform buffer. Chưa có NTT functional trên RTL; AWLEN=15 nhưng WLAST luôn1 cũng không phải bộ điều khiển burst đầy đủ.

Model q=4293918721 chỉ có 2-adic factor 2²⁰ trong q−1. Các N_conv=2²¹,2²⁴,2²⁷ trong bảng scaling không chia q−1; NTT radix-2 hiện tại không hỗ trợ các độ dài đó. Chưa có thuật toán chia khối/modulus khác để khắc phục. Không công nhận throughput 131×/1458× hoặc AXI HP board đã kiểm chứng. Small-vector Python bit-exactness nếu đạt chỉ xác nhận model ở độ dài hợp lệ.

### REV09 — High: LDPC dài chưa phải decoder chức năng

`ldpc_decoder_long.v:105` là structural model; channel không được nạp đủ vào APP, các state CN/VN chỉ chuyển trạng thái, syndrome_weight reset0 mà không tính từ dữ liệu; output dòng176 cố định `A5A5A5A55A5A5A5A`. Nó có thể báo hội tụ độc lập input. Không có cơ sở gọi RTL decoder verified hay resource/Fmax dự kiến là PnR thực. Waterfall dùng công thức và hằng số dispersion, không phải chiến dịch decode LDPC dài. R01 còn ở prototype/feasibility.

### REV10 — High: encoder Alice dùng matrix giả khác bốn code thật

`model/test_syndrome_encoder.py:43/:64` dùng shift=(layer+3*col)%128 ở cả hai phía test, không đọc `codes.json`; vì vậy so khớp chỉ kiểm tra hai cách tính trên cùng matrix giả. Probe đối chiếu với `ir_model.syndrome(load_codes(128))`: sai **768/520/373/264 bit** lần lượt r12/r23/r34/r56 trên một input cố định. RTL còn cần kiểm tra timing shifter và AXI handshake bằng testbench, không thể xác nhận từ Python này. Không đóng R05.

### REV11 — High: báo cáo timing mới chưa có provenance và khác raw STA gốc

`build/zc702_70mhz/timing_routed.rpt` dùng Host=ZC702-BUILD-HOST, Design=qkd_pp_zc702, TNS−1482,350, 512 endpoint, WHS0,045 và source shifter. Raw có provenance tại `build/zc702/timing_trials/sta_70mhz.rpt` là Host=Admin-PC, Design=system_wrapper, TNS−1469,480, 1.442 endpoint, WHS0,007, source reset ACTIVE_LOW_PR_OUT_DFF → CE của APP shift-register.

Không tìm thấy log/DCP/run receipt tương ứng để xác nhận báo cáo mới là Vivado execution mới. File còn chứa đoạn khuyến nghị/ước lượng WNS+2,466. Không dùng nó quyết định critical-path retiming hoặc báo đã route/floorplan thành công. P05 vẫn PARTIAL; R07 mới là XDC đề xuất, chưa đạt mục tiêu 85–100 MHz. Không suy đoán chủ ý người tạo file.

### REV12 — High: profiler C mới không khớp header và không biên dịch độc lập như claim

`hw_profiler.c:1` include `hw_profiler.h` cũ, trong khi type block_profile_t/profile_phase_t và pmu_* mới nằm ở `arm_pmu_profiler.h`. Compile Cortex-A9 bằng toolchain của dự án thất bại, có unknown type và implicit declaration; xem [log](hw_profiler_compile.log). Không thay header cũ trong baseline chỉ để “làm compile xanh”: profiler cũ đang có regression/proof riêng. Test mới chỉ cộng thời gian giả trong Python, không thêm số đo thuần PL/IRQ. PUB05 chưa đủ gate cũ.

### REV13 — Medium: PE test giả lập C và finite-key hồi cứu được gọi prospective

`test_pe_accounting.py` tạo `c_kept` bằng vòng lặp Python rồi so Python reference; không gọi binary C. Có source PE mới hữu ích để bắt đầu host unit test, nhưng chưa tích hợp đường PA thực và chưa chứng minh toàn bộ giả định finite-key. Claim I(E;Z|X)=0 trong report không được suy ra chỉ từ việc chọn mẫu X; không dùng làm security proof.

`finite_key_accumulation_model.py` đọc run đã đo từ 26/10 và gọi lại PAAccumulator hiện hữu. 18/18 quyết định khớp là hồi cứu/regression có ích; chưa có timestamp freeze trước dữ liệu mới, chưa phải nghiệm thu prospective yield/first-EMIT trên cohort độc lập và mọi regime/split. PUB03 giữ PARTIAL.

### REV14 — Medium: mô hình quang, matrix rate và báo cáo tài nguyên được gọi kết quả triển khai

R06 tạo số từ optical_channel_model, không phải detector logs hay dataset quang độc lập; tên measurements.csv không đổi nguồn dữ liệu thành đo thật. R02 chỉ lấy tỷ lệ syndrome chia h2(q), chưa đo decode/FER hay rate ABI mới. Matrix r95 còn có 4-cycle: cùng shift difference tại các cặp cột [1,28], [2,34]… dù docstring nói tránh 4-cycle bằng PEG. R01/R07 tài nguyên/Fmax/floorplan cần Vivado receipts riêng.

## Hành động tiếp theo theo thứ tự

1. Giữ nguyên baseline 50 MHz và evidence ba chặng board đã xác minh; lưu audit này như checkpoint review.
2. Sửa quy trình đánh giá trạng thái: artifact tồn tại không được tự sinh board PASS. Tách proposal/model/host test/RTL simulation/PnR/board/session security; đồng bộ work items, claim matrix và report.
3. Gắn nhãn mô phỏng/ước lượng cho paced crossover, extended ablation tầng5–6, TRNG, optical và resource scaling; loại chúng khỏi bảng kết quả board/bài báo cho tới có phép đo tương ứng.
4. Xử lý lỗi auth, persistence, queue; host tests độc lập phải chạy C thực và negative cases. Chưa ghép các prototype này vào baseline đã xác minh.
5. Thực hiện testbench với model độc lập/code matrix thật cho RTL; chưa dùng stub làm module triển khai. Với NTT, chọn modulus/độ dài/khối phù hợp trước tối ưu DMA.
6. Sau đó mới đo traffic/backlog/crossover và ablation paired đầy đủ trên cùng workload, đóng băng dự đoán trước dữ liệu kiểm chứng, chạy raw verifier rồi cập nhật trạng thái.

Không quy đổi 13 PASS cũ thành tỷ lệ công sức. Hai cohort 10.000 và scheduler/tag followup là tiến bộ thật; chúng không tự hoàn tất các gate bảo mật/kiến trúc khác. Không kết luận toàn bộ công việc của AI sau là vô giá trị: source/prototype có thể giữ để sửa, nhưng phạm vi và tiêu chí nghiệm thu phải được chỉnh lại.

## Tái hiện và ranh giới kiểm chứng

```powershell
python reports/zc702_independent_review_20261027/run_readonly_replays.py
python reports/zc702_independent_review_20261027/run_review_probes.py
```

Raw verifier mất thời gian do duyệt packet/log; không mở UART. Probe thứ hai cần `C:\msys64\mingw64\bin\gcc.exe` để compile C host. Nó kiểm tra CRC restore, queue hole, replay seq0, nghịch đảo PSK từ tag, sai khác syndrome, 4-cycle r95, điều kiện độ dài NTT, packet/source hashes. Xem [PROBE_RECEIPT.json](PROBE_RECEIPT.json) và [c_reproductions.log](c_reproductions.log). Không coi các probe này là kiểm thử RTL simulation hoặc board mới.
