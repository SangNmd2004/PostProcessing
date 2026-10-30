"""Summarize tracked work without treating partial implementation as completion."""
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'reports'


def verified_report(run_root, run_id, report_kind):
    raw = ROOT / 'build/zc702' / run_root / run_id / 'result.json'
    report = OUT / f'zc702_{report_kind}_{run_id}'
    proof = report / 'verified_evidence.json'
    if not raw.exists() or not proof.exists():
        return None
    result = json.loads(raw.read_text())
    evidence = json.loads(proof.read_text())
    if (result.get('complete') and evidence.get('source_result_sha256') ==
            hashlib.sha256(raw.read_bytes()).hexdigest()):
        return report.relative_to(OUT).as_posix() + '/REPORT.md'
    return None


def main():
    with (OUT / 'zc702_work_items.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    assert len({r['id'] for r in rows}) == len(rows)
    groups = [('Chức năng trên board', 'F'), ('Hoàn thiện hệ thống', 'P'),
              ('Mô hình, thí nghiệm, bài báo', 'PUB'), ('Hướng phát triển', 'R')]
    def bucket(row):
        if row['status'] == 'PASS_FUNCTIONAL_BOARD':
            return 'done'
        if row['status'] in ('PARTIAL', 'IN_PROGRESS'):
            return 'partial'
        if row['status'] in ('TODO', 'TODO_RESEARCH'):
            return 'todo'
        raise ValueError(row['status'])
    counts = Counter(bucket(r) for r in rows)
    stamp = datetime.now(timezone(timedelta(hours=7))).isoformat(timespec='seconds')
    lines = ['# Tiến độ toàn bộ dự án ZC702', '', f'Cập nhật: {stamp}.', '',
             f'Danh sách hiện có **{len(rows)} mục được định danh**, không có mục thứ 36. '
             'Không tự tạo thêm mục để khớp một tổng số đã nêu trong trao đổi.', '',
             f'Đạt tiêu chí chức năng hiện có: **{counts["done"]}/{len(rows)} '
             f'({100*counts["done"]/len(rows):.1f}% theo số đầu mục)**. '
             'Không dùng tỷ lệ này làm tỷ lệ công sức, mức an toàn hay mức sẵn sàng sản phẩm.', '',
             '| Nhóm | Tổng | Đạt trong phạm vi thử | Một phần/đang làm | Chưa làm |',
             '|---|---:|---:|---:|---:|']
    for title, prefix in groups:
        selected = [r for r in rows if ''.join(c for c in r['id'] if c.isalpha()) == prefix]
        c = Counter(bucket(r) for r in selected)
        lines.append(f'| {title} | {len(selected)} | {c["done"]} | {c["partial"]} | {c["todo"]} |')
    lines += ['', 'Alice, thống kê decoy và dữ liệu BSC là mô phỏng. PL hiện chạy 50 MHz; '
              'PASS chức năng không đồng nghĩa chứng nhận bảo mật QKD.', '',
              '## Kết quả mới có bằng chứng', '']
    ablation = verified_report('board_ablation_runs', '20261027T024201Z', 'board_ablation')
    if ablation:
        lines += [f'- [Ablation board bốn cấu hình]({ablation}): 1.000 cặp đầu vào ×4; '
                  'không chạy tag/PA trong phép đo. Có một đầu vào hội tụ sai 11 bit ở ba cấu hình GS; '
                  'kết quả kiểm thử tag riêng phải được đọc độc lập, không đổi nhãn tag của cohort ablation.']
    for kind, description in [
        ('wrong_codeword', 'Kiểm thử tag Alice trên wrong codeword tự nhiên'),
        ('schedule_validation', 'Đối chiếu mô hình lập lịch trên timing held-out')]:
        reports = []
        for candidate in sorted(OUT.glob(f'zc702_{kind}_*/verified_evidence.json')):
            run_id = candidate.parent.name.removeprefix(f'zc702_{kind}_')
            report = verified_report(f'{kind}_runs', run_id, kind)
            if report:
                reports.append(report)
        if reports:
            lines.append(f'- [{description}]({reports[-1]}): đã có raw proof; đọc giới hạn và kết luận riêng trong báo cáo.')
        else:
            lines.append(f'- {description}: chưa có kết quả hoàn tất khớp raw proof.')
    catalog = OUT / 'FER_CATALOG.csv'
    if catalog.exists():
        with catalog.open(encoding='utf-8-sig', newline='') as f:
            cohorts = list(csv.DictReader(f))
        qualified = [c for c in cohorts if int(c['n']) >= 10000]
        lines += [f'- [FER catalog](FER_CATALOG.md): {len(cohorts)} cohort hoàn tất có proof; '
                  f'{len(qualified)} cohort đủ cỡ mẫu ≥10.000. Không gộp các QBER/code/seed khác nhau.']
    lines += ['- [Đo pha PS/PL/UART và PA lớn](zc702_profiling_20261027/REPORT.md): '
              '36 ca per-block và một phiên PA 103 pass; chưa phải thông lượng khóa bí mật của sản phẩm.', '',
              '## Trạng thái job lúc tạo báo cáo', '']
    for filename in ('RUNNING_JOBS.json', 'FOLLOWUP_JOBS.json'):
        path = ROOT / filename
        if path.exists():
            job = json.loads(path.read_text())
            progress = job.get('stage_progress', {})
            detail = (f'; checkpoint {progress.get("verified_evaluations")}/'
                      f'{progress.get("planned_evaluations")} lượt' if progress else '')
            lines.append(f'- `{filename}`: `{job["status"]}`{detail}. '
                         'Đây là snapshot; đọc file live trước khi dùng COM3.')
    lines += ['', '## Phần còn lại theo từng mục', '',
              '| ID | Trạng thái | Công việc cần tiếp tục |', '|---|---|---|']
    for row in rows:
        if bucket(row) != 'done':
            lines.append(f'| {row["id"]} | {row["status"]} | {row["next_action"].replace("|", "/")} |')
    lines += ['', 'Ưu tiên: hoàn tất cohort đang chạy → kiểm thử tag với wrong codeword tự nhiên → '
              'đối chiếu mô hình đã đóng băng với dữ liệu board mới → fault recovery và security accounting → '
              'traffic/backlog/crossover thực → mở rộng thống kê và bản thảo. Các mục R là hướng phát triển riêng.', '',
              'Nguồn: [work items](zc702_work_items.csv), [claim/evidence](zc702_claim_evidence.csv), '
              '[kế hoạch thực thi](ONGOING_RESEARCH_STAGES.md).', '']
    (OUT / 'TIEN_DO_TOAN_BO_DU_AN.md').write_text('\n'.join(lines), encoding='utf-8')
    remaining = [dict(r, progress_bucket=bucket(r)) for r in rows if bucket(r) != 'done']
    with (OUT / 'zc702_remaining_work.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(remaining[0]))
        writer.writeheader()
        writer.writerows(remaining)
    print('PROJECT_PROGRESS_WRITTEN', dict(counts))


if __name__ == '__main__':
    main()
