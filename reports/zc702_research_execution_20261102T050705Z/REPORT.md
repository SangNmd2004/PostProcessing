# Kết quả triển khai kế hoạch nghiên cứu ZC702 — 02/11/2026

Đã sửa kế hoạch và triển khai tuần tự trong phạm vi đã cho phép. **35ID/tên/trạng thái giữ nguyên:13 PASS_FUNCTIONAL_BOARD,20 PARTIAL,2 TODO/TODO_RESEARCH.** Tỷ lệ đầu mục không là tỷ lệ công sức hoặc mức an toàn. Baseline PL50MHz/27file giữ nguyên; không rebuild PL, NTT, LDPC dài hay TRNG mô phỏng thành kết quả hardware.

## Kế hoạch và host

Hai kế hoạch gốc đã sửa để tách mục tiêu, model, đo board và production. Bản trước trong before/, bản host đã niêm phong ở host_checkpoint/. Đã sửa split bằng emitted(), event/session replay và hai quyết định cùng bit count; chỉ commit sau PA thành công. 12 regression PASS;92 quyết định split và18 quyết định EMIT cũ được raw-event replay khớp. Đây là retrospective regression.

Budget generator nay chỉ phân tích collision có điều kiện, không tự nhận persistence PASS;16Mbit input chứa5786block trọn, khác PA output. Generator trạng thái không còn coi report simulator là crossover board. Hợp đồng leakage/tag/epsilon được ghi rõ, không giảm term trong baseline để tạo yield tốt hơn.

## DDR-paced IR thực trên board

ELF riêng dùng timer ARM cho scheduled/actual arrival, dispatch/completion, backlog/drop, profile, attempts/leak/cycles. UART chỉ nạp và lấy log ngoài timed loop. C queue được kiểm tra capacity1..128,100 vòng wrap và256 cấu hình reveal-safety. ARM compile với Wall/Wextra/Werror.

Pilot chính42 phép đo/1344job: K1/2/4, EFF/THR/adaptive, RTT0/1ms, arrival100/1000us. Thêm30 lịch arrival mới/3840job K1, dự đoán freeze trước capture. Mean absolute error trên mẫu số prediction=0.203898%, max=2.947016%, proxy-bit error lớn nhất=0.065464%; model_accepted=True. Đây là tolerance kỹ thuật, không CI. [CSV](paced_sequence/model_snapshot_recheck/prediction_comparison.csv), [proof](paced_sequence/model_snapshot_recheck/verified_prediction.json), [đồ thị](paced_sequence/IR_proxy_validation.png), [SVG](paced_sequence/IR_proxy_validation.svg).

Trên metric IR proxy trừ IR leakage, hai lần lặp tại mỗi arrival point cho EFF tốt hơn THR ở746,83 và1344,09block/s, THR vượt ở1492,54/1642,04/2985,07block/s. Đây là finite-batch component proxy, **không phải throughput khóa bí mật**. Chưa có tag/PE/PA trong vòng đo, f_adj giữ1,3/job; cùng hai input paired lặp lại. Chỉ lịch arrival là held-out; không gọi input là chưa từng chạy.

Verifier đọc TX/UART thật, kiểm tra source Alice/Bob/channel/syndrome/golden, plan/code/r0, outcome, attempts/leak, timestamps, in-flight bound và hysteresis. KEY được firmware bench_check đối chiếu golden; raw metric không chứa literal DMA KEY. Negative control sửa leak trong UART trong khi runner JSON không đổi bị verifier từ chối.

## Các lỗi và hồi phục được giữ

Lượt smoke đầu chạy4case rồi restore gặp Already stopped; giữ raw run20261102T051641Z và receipt hồi phục. Helpers JTAG nay chỉ bỏ qua lỗi chính xác đó, các lỗi khác vẫn fail. Smoke chạy lại có raw proof.

Các thử nghiệm full-pilot trước gặp CPU timeout ở K4/adaptive, trước hết RTT1ms rồi RTT0; không tính các cohort đó là complete/PASS. Chẩn đoán CPU có trường hợp không halt được. RTL cho thấy REVEAL AXI write có thể chờ reveal engine trong lúc KEY output chiếm CH read port; một simple RX buffer cần CPU rearm tạo nguy cơ chờ vòng. Nhánh thử mới thu hết lượt đang active trước khi load/reveal lượt kế, rồi queue các context đã chuẩn bị. Không tuyên bố đã chứng minh mọi nguyên nhân phần cứng; hàng rào này loại nguy cơ đã nhận diện và hồi quy K4/RTT0 đạt10lượt/320job, sau đó pilot chính đạt. RTL/baseline không đổi. Failed captures và ELF variants vẫn được giữ dưới build/zc702/paced_runs và paced_test.

## FER qualification mới

Fixed n, synthetic BSC độc lập, seed disjoint; không dừng sớm theo CI. Mỗi vector được board đánh giá một lần. KEY/status được firmware so golden và verifier đối chiếu lại input/source/packet/receipt; không chạy tag/PA trong cohort này. Captured counter trong RUNNING_JOBS không được coi là đã raw-verified.

- QBER=1%, r34: n=10000, success=10000, discard=0, wrong=0, FER=0, Wilson95=[0, 0.00038399837067659573]. [Proof](../zc702_fer_20261102T053801Z/verified_evidence.json).

Catalog được cập nhật nhưng không gộp seed/QBER/code; kết quả một stratum không là FER toàn hệ. Các error/partial run giữ nguyên.

## Finite-key source mới

Status=VERIFIED_COMPLETE. 450 block append và 19 quyết định được kiểm chứng nếu STATUS có complete=true. [Trạng thái/proof](prospective_finite/STATUS.json). Source seed2026110220 mới; input/key/counts test-basis theo cùng cửa sổ mô phỏng, prediction được freeze trước board. Raw verifier tái tính tag và PA từ actual KEY/seed, không tin expected/PASS runner.

Outcome của nguồn mới: {'INJECTED_TAG_REJECT': 1, 'VERIFIED_ADDED': 450, 'DISCARD': 1}. Tag sai có chủ đích được tách khỏi discard decoder; không dùng tập nguồn tương quan này như cohort FER BSC độc lập.

Clock được quy định trước: tăng virtual time theo block retained rồi idle+3601s để kiểm tra age gate. Đây là prospective **functional replay** của nguồn đã generate và biết trước; không là dự đoán phân bố first-EMIT của nguồn quang tương lai hoặc wall time. Không đóng PUB03/composable security từ phép khớp này. Nếu STOPPED_ERROR thì giữ lỗi và không thêm claim PASS cho chặng này.

## Gate còn thiếu và checkpoint

Tiếp tục q7/r12 qualification, nguồn/tập input rộng hơn, controller feedback, PA/verified-buffer trong pacing và finite-key source-clock split/ABORT. PE/leak/selection/epsilon cần hợp đồng và review trước claim secret yield. P04/PUB04 production trust, entropy, reboot accounting và rollback vẫn PARTIAL. Không chạy NTT/PL rebuild để thay các gate còn thiếu này.

Baseline27hash khớp; checkpoint secure-accumulator trước và host_checkpoint không bị đổi. Các run thử đã restore qua MMIO/READY, cohort FER dùng chính baseline firmware. COM3 đã đóng và được controller probe lại. [RUNNING_JOBS](../../RUNNING_JOBS.json) là trạng thái live.

## Document encoding correction

The sealed host checkpoint retained its original hash, including a prose encoding defect (Vietnamese accents replaced by question marks). It is not rewritten. The two live plan documents were rewritten as UTF-8 and their readable copies are preserved in current_sources/. This final report supersedes the defective prose; host receipts and raw replay results remain unchanged.
