# Kế hoạch tổng thể ZC702: tích hợp và kiểm chứng nghiên cứu

Cập nhật 02/11/2026. [Mô hình/thực nghiệm](MO_HINH_TOAN_HOC_VA_KE_HOACH_THUC_NGHIEM.md) và [35 ID chuẩn](reports/zc702_work_items.csv) điều khiển phạm vi. Bản trước bảo tồn trong checkpoint execution; không đổi ID/title/status.

## Mục tiêu

Khép kín IR → verify → verified buffer → finite-key decision → Hankel PA. Kiểm chứng ba đóng góp: che RTT đa context, profile thích ứng backlog và tích lũy finite-key. Baseline PL 50 MHz giữ nguyên. Số model/RTL lịch sử không là target board bắt buộc.

## Thứ tự triển khai

1. PUB02/PUB03/PUB04: sửa split/event/budget/stale claims, phân biệt input/output và attempts. Đồng bộ evidence, không tự nâng PASS.
2. P01/P02/P06/PUB05/PUB01: pipeline đúng, PE/leak ledger, reuse K/RTT proof. Chỉ đo workload thiếu, freeze trước capture. Scheduler wave barrier cần mô tả/validation riêng.
3. PUB02/PUB06: paired EFF/THR, DDR timer pacing; đo arrival/backlog/drop/resource demand. Nhận cả kết quả không có crossover. IR proxy là bước đầu; cần verified-buffer/PA trước yield toàn pipeline.
4. PUB03/P08/PUB07: nguồn synthetic mới đã hash, WAIT/EMIT/split/ABORT và đúng clock. Qualification strata thiếu với input độc lập; không dùng replay fixture tăng mẫu FER.
5. Tổng hợp số đo và limitations. PUB08 deferred theo chỉ đạo hiện có.

## Hướng mở rộng

- R01/R02: code dài/rate mới qua matrix/rank/FER trước ABI/RTL/build riêng.
- P03/R06: entropy vật lý/dataset quang cần nguồn thật; simulator không thay hardware.
- P05/R07: timing 70 MHz cần route provenance trên build riêng; không đổi baseline từ số quy đổi.
- R04: NTT PA trong PL dài hạn; NTT host là oracle, RTL stub không là implementation.
- P04/PUB04 production: trust anchor, nonce, control/error authentication, reboot accounting cần triển khai/kiểm thử riêng. CRC/RAM không là anti-rollback; giữ PARTIAL.
- R03: AE350 không ưu tiên; tập trung Zynq-7000.

Các hướng trên không chặn mọi gate nghiên cứu hiện hành. Output fixture chức năng không là khóa bí mật đã chứng minh.

## Tiêu chí chung

Input hash, lệnh/config, raw evidence, independent verifier, case dương/âm và giới hạn rõ. Không auto-PASS theo file tồn tại, không ép speedup/throughput/FER về số lịch sử. Giữ ID/REV; tỷ lệ đầu mục không là tỷ lệ công sức.

Preflight source/build/baseline, một owner COM3, timeout/fail-closed và restore trong finally. Không overwrite checkpoint lịch sử. Mapping/current pointer chỉ cập nhật sau kiểm chứng; kiểm tra checkpoint trước và 27 baseline hash.
