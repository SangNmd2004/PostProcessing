# Mapping chuẩn cho phiên làm việc tiếp theo

ID và tên dưới đây lấy nguyên văn từ work items. Không đánh số hoặc đổi nghĩa ID theo một báo cáo kể chuyện. Mapping này thay thế bảng 35 mục và bảng REV bị đổi nghĩa trong báo cáo đối soát trước; bản cũ được giữ nguyên để bảo toàn manifest lịch sử.

| ID | Mục tiêu chuẩn | Trạng thái | Gate tiếp theo |
|---|---|---|---|
| F01 | QC-LDPC 3072 and four codes with NMS75 + GS | PASS_FUNCTIONAL_BOARD | Expand to independent synthetic / real optical dataset (PUB07) |
| F02 | HOLD reveal retry discard and ERRCNT tracking | PASS_FUNCTIONAL_BOARD | Inject transport errors and timeouts to verify robust recovery (P04) |
| F03 | EFFICIENCY and THROUGHPUT controller policies on ARM | PASS_FUNCTIONAL_BOARD | Perform formal PE bit removal and leakage accounting (P02) |
| F04 | Backlog hysteresis profile switching | PASS_FUNCTIONAL_BOARD | Drive queue with varying raw key generation rates (PUB01) |
| F05 | Dynamic code selection r0 delta and early abort | PASS_FUNCTIONAL_BOARD | Sweep full channel drift envelope from 0.5% to 11% (PUB02) |
| F06 | Early termination (ET) and post-processing (PP) | PASS_FUNCTIONAL_BOARD | Use paired ET-only and PP-only trials before attributing individual gains |
| F07 | Verification tag and fail-closed rejection | PASS_FUNCTIONAL_BOARD | Test larger pool of undetected false codewords and tag collisions (PUB04) |
| F08 | IR strip D-positions followed by per-block PA1024 | PASS_FUNCTIONAL_BOARD | P01 coupled stream EMIT/split/ABORT is already board-verified; extend fault recovery and security review |
| F09 | Four contexts resident and queued in PL | PASS_FUNCTIONAL_BOARD | Long multi-context DMA soak test and RTT speedup benchmark (P06, PUB01) |
| F10 | QKD PL interrupt delivery to ARM GIC | PASS_FUNCTIONAL_BOARD | Integrate DMA completion IRQs and build purely interrupt-driven scheduler (P07) |
| F11 | Decoy finite-key WAIT EMIT ABORT split state machine | PASS_FUNCTIONAL_BOARD | EMIT/split/ABORT with actual buffer is verified; expand fault cases and prospective finite-key modeling |
| F12 | DMA UART infrastructure and verified artifacts | PASS_FUNCTIONAL_BOARD | Implement authenticated channel protocol for Alice-Bob communication (P04) |
| P01 | Accumulated verified IR buffer coupled with finite-key PA emission | PASS_FUNCTIONAL_BOARD | Expand fault cases and enforce verification budget; review security assumptions independently |
| P02 | PE sample leakage removal and exact error counting | PARTIAL | Integrate PE accounting into actual PA path; execute C and board negative cases |
| P03 | Physical on-chip TRNG seed source with online health tests | PARTIAL | Physical source integration, raw board capture and entropy assessment |
| P04 | Authenticated classical Alice-Bob channel | PARTIAL | Design independent keys, authenticated session/rekey and durable replay state; then validate transport on a separate board firmware build |
| P05 | 70 MHz Zynq PL system implementation and timing closure | PARTIAL | Inspect actual reset-to-APP critical paths in the original DCP; retain 50MHz baseline and isolate any new PnR experiment |
| P06 | Throughput and 4-context RTT hiding benchmark with HW timers | PARTIAL | Use measured phases to refine scheduling; measure controlled arrival/backlog crossover and multi-context end-to-end phases |
| P07 | Purely interrupt-driven DMA and context scheduling | PARTIAL | Queue-hole regression fixed in C; test concurrency, GIC/DMA/WFI and hardware timeout behavior before integration |
| P08 | FER measurement over at least 10000 independent blocks | PARTIAL | Complete staged qualification cohorts, then expand remaining QBER/code strata and tag/PA end-to-end fault statistics |
| R01 | Longer LDPC code length (6144 to 12288 bits, 128 lanes) | PARTIAL | Implement real APP/CN/VN/syndrome/output and RTL golden tests |
| R02 | High rate (~0.95) and low rate (~0.40) LDPC mother codes | PARTIAL | Validate both graphs/rank/FER, then implement the rate ABI and ROM on an isolated build |
| R03 | Port to Andes AE350 RISC-V SoC platform | TODO_RESEARCH | Skip Andes AE350; maintain 100% focus on Xilinx Zynq-7000 |
| R04 | Large-block PA via NTT-based MMH-MH / Toeplitz hashing | PARTIAL | Implement real NTT/burst engine with valid transform lengths |
| R05 | FPGA-based Alice syndrome encoder reusing LDPC shifter and ROM | PARTIAL | Use deployed codes.json matrix, correct pipeline and RTL testbench |
| R06 | Optical channel optimization and realistic decoy parameters | PARTIAL | Label synthetic source and validate against independent published or real data |
| R07 | High clock optimization (7-bit shifter and floorplanning) | PARTIAL | Validate constraints on real hierarchy and run isolated PnR |
| PUB01 | Multi-context queueing and scheduling model S(K) & board RTT validation | PARTIAL | Extend to paced arrival and production phases without refitting this held-out cohort |
| PUB02 | Analytical f and attempts model vs (code, QBER, r0, delta) & crossover proof | PARTIAL | Crossover empirically confirmed; integrate into publication manuscript draft (PUB08) |
| PUB03 | Finite-key accumulation model ell(N) and ABORT/split empirical validation | PARTIAL | Freeze finite-key/first-EMIT predictions before new independent sessions, including split and ABORT regimes |
| PUB04 | Cumulative correctness security bound eps_cor <= N * 2^(-64) tag budget analysis | PARTIAL | Design trusted monotonic durable storage and atomic authenticated commits; test reset/power-loss/old-snapshot restore before closing session accounting |
| PUB05 | High-resolution hardware counter integration for latency profiling | PARTIAL | Preserve old profiler; fix new header/API and validate missing PL/IRQ phases |
| PUB06 | Controlled ablation study across all optimization layers | PARTIAL | Four-stage board ablation verified; extend paired dynamic profile, hysteresis switching and K1/K4 under paced traffic |
| PUB07 | Rigorous FER statistical campaign with 95% confidence intervals | PARTIAL | Complete staged qualification cohorts, then expand remaining QBER/code strata and tag/PA end-to-end fault statistics |
| PUB08 | Paper manuscript drafting, target venue alignment and literature benchmarking | TODO | Deferred per user instruction until hardware engineering is complete |

## ID phát hiện gốc

Tên finding giữ theo review độc lập lần đầu. Trạng thái review ở lần hai là checkpoint lịch sử; đọc REPORT.md và test receipt của chặng này để biết thay đổi mới.

| REV | Nội dung gốc |
|---|---|
| REV01 | Status promotion by file existence |
| REV02 | Unmeasured ablation layers 5 and 6 |
| REV03 | Paced crossover simulator claimed as board experiment |
| REV04 | Authentication PSK exposure and seq0 replay |
| REV05 | Persistence CRC and rollback |
| REV06 | Event queue holes and IRQ integration |
| REV07 | TRNG synthetic data claimed physical entropy |
| REV08 | NTT RTL stub and unsupported transform scaling |
| REV09 | Long LDPC decoder structural stub |
| REV10 | Alice encoder wrong matrix |
| REV11 | Timing report lacks provenance |
| REV12 | Profiler C includes wrong API header |
| REV13 | PE C simulation and retrospective finite-key claims |
| REV14 | Optical/rate/resource models called implemented results |

P03 là TRNG; R06 là quang; P05 là timing; PUB04 là ngân sách xác minh. Không dùng các ID này cho pacing, persistence hoặc số đo khác.
