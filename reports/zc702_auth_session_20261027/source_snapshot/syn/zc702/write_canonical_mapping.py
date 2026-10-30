"""Render work-item IDs verbatim and preserve original review identifiers."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,csv,json

ROOT=Path(__file__).resolve().parents[2]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',required=True,type=Path,help='Current stage directory; never an immutable archive')
    args=ap.parse_args();OUT=args.output.resolve()
    assert OUT.is_relative_to(ROOT), 'Output must be within workspace'
    assert (OUT/'REPORT.md').exists(), 'Write the concrete stage report first'
    OUT.mkdir(exist_ok=True)
    with (ROOT/'reports/zc702_work_items.csv').open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    expected={f'{p}{i:02d}' for p,n in [('F',12),('P',8),('R',7),('PUB',8)] for i in range(1,n+1)}
    assert len(rows)==35 and {r['id'] for r in rows}==expected
    with (ROOT/'reports/zc702_independent_recheck_20261027/REV_STATUS.csv').open(encoding='utf-8-sig',newline='') as f:
        findings=list(csv.DictReader(f))
    assert [r['original_finding_id'] for r in findings]==[f'REV{i:02d}' for i in range(1,15)]
    lines=['# Mapping chuẩn cho phiên làm việc tiếp theo','',
           'ID và tên dưới đây lấy nguyên văn từ work items. Không đánh số hoặc đổi nghĩa ID theo một báo cáo kể chuyện. '
           'Mapping này thay thế bảng 35 mục và bảng REV bị đổi nghĩa trong báo cáo đối soát trước; '
           'bản cũ được giữ nguyên để bảo toàn manifest lịch sử.','',
           '| ID | Mục tiêu chuẩn | Trạng thái | Gate tiếp theo |','|---|---|---|---|']
    for r in rows:
        lines.append('| '+' | '.join(r[k].replace('|','/') for k in ['id','title','status','next_action'])+' |')
    lines+=['','## ID phát hiện gốc','',
            'Tên finding giữ theo review độc lập lần đầu. Trạng thái review ở lần hai là checkpoint lịch sử; '
            'đọc REPORT.md và test receipt của chặng này để biết thay đổi mới.','',
            '| REV | Nội dung gốc |','|---|---|']
    lines += [f'| {r["original_finding_id"]} | {r["original_subject"]} |' for r in findings]
    lines += ['','P03 là TRNG; R06 là quang; P05 là timing; PUB04 là ngân sách xác minh. '
              'Không dùng các ID này cho pacing, persistence hoặc số đo khác.','']
    (OUT/'MAPPING_CANONICAL.md').write_text('\n'.join(lines),encoding='utf-8')
    pointer=dict(updated_at=datetime.now(timezone(timedelta(hours=7))).isoformat(),
                 status='PARTIAL_IMPLEMENTATION_WITH_SCOPED_TESTS',
                 current_report=(OUT/'REPORT.md').relative_to(ROOT).as_posix(),
                 canonical_mapping=(OUT/'MAPPING_CANONICAL.md').relative_to(ROOT).as_posix(),
                 supersedes_mapping_in='reports/zc702_reconciliation_20261027/REPORT.md',
                 old_report_is_preserved=True,physical_board_rerun=False)
    (ROOT/'reports/RECONCILIATION_CURRENT.json').write_text(json.dumps(pointer,indent=2)+'\n')
    print('CANONICAL_MAPPING_WRITTEN',len(rows),'work items',len(findings),'original findings')

if __name__=='__main__':main()
