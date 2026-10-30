"""Independently check raw UART receipts against packets and summarize a board run."""
from pathlib import Path
import argparse
import collections
import csv
import hashlib
import json
import re

ROOT=Path(__file__).resolve().parents[2]
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('run',type=Path)
args=ap.parse_args()
run=args.run.resolve()
result=json.loads((run/'result.json').read_text())
campaign_path=Path(result['source_campaign'])
campaign=json.loads(campaign_path.read_text())
csv_rows=list(csv.DictReader(Path(campaign['csv']).open(encoding='utf-8-sig',newline='')))
assert result['complete'] and result['hardware_capture'] and result['bad_crc_rejected']
assert hashlib.sha256(campaign_path.read_bytes()).hexdigest()==result['campaign_sha256']
assert hashlib.sha256(Path(campaign['csv']).read_bytes()).hexdigest()==campaign['csv_sha256']
uart=(run/'uart.log').read_text()
assert not re.search(r'FATAL|MISMATCH|TIMEOUT|DMA_ERROR',uart)
assert 'QKD_UART_CRC_REJECT seq=4294967295' in uart
receipts=re.findall(r'QKD_UART_RESULT seq=(\d+) crc=([0-9a-fA-F]{8}) conv=(\d+) attempts=(\d+) errcnt=(\d+)',uart)
ir=re.findall(r'QKD_IR_VECTOR_PASS block=(\d+) attempts=(\d+)',uart)
assert len(receipts)==len(ir)==result['requested']==result['hardware_matches']==len(result['records'])
assert len({r[0] for r in receipts})==len(receipts)
assert f"QKD_UART_DONE passed={result['session_passed_total']}" in uart
if not (run/'xsct.log').stat().st_size:
    raise ValueError('Report requires a fresh programming receipt, not --attach')
xsct=(run/'xsct.log').read_text(errors='replace')
assert 'ZC702_PROGRAM_MMIO_PASS' in xsct and 'ZC702_SMOKE_CPU_STARTED' in xsct
assert 'QKD_PA_VECTOR_PASS bits=4096' in uart
expected={r['seq']:r for r in campaign['records']}
for receipt,ir_receipt,row in zip(receipts,ir,result['records']):
    seq,crc,conv,attempts,errcnt=receipt
    r=expected[int(seq)]
    assert r['seq']==row['seq']==int(ir_receipt[0])
    assert int(attempts)==int(ir_receipt[1])==r['attempts']
    assert crc.lower()==r['crc32'] and bool(int(conv))==(r['model_outcome']!='DISCARD')
    assert not int(conv) or int(errcnt)==r['expected_errcnt']
    assert hashlib.sha256((campaign_path.parent/r['file']).read_bytes()).hexdigest()==r['sha256']
    assert r.get('residual_errors',0)==0 or r['model_outcome']!='SUCCESS'

native=[r for r in result['records'] if r['source']=='csv_native']
sweep=[r for r in result['records'] if r['source']=='controlled_qber']
counts=collections.Counter(r['model_outcome'] for r in result['records'])
lines=['# Kết quả dữ liệu CSV truyền UART trên ZC702','',
       f"Lượt chạy UTC: `{result['started_utc']}`. UART `{result['port']}`, 115200 baud, context 0, polling, PL 50 MHz.",'',
       f"**{len(receipts)}/{len(receipts)} lượt phần cứng khớp vector tham chiếu**; một gói CRC sai bị từ chối đúng. "
       'Firmware so sánh trạng thái/số vòng từng attempt, toàn bộ word KEY khi hội tụ, ERRCNT khi hợp lệ và kiểm tra DMA. '
       'Lượt discard đúng dự kiến được tính là khớp phần cứng, không tính là sửa lỗi thành công.','',
       f"Gồm {sum(r['source']=='baseline' for r in result['records'])} vector hồi quy, {len(native)} lượt từ CSV và {len(sweep)} lượt QBER tạo thêm. "
       'PA 4096 → 1024 bit chỉ chạy vector chuẩn lúc khởi động, chưa chạy PA từ khóa CSV đã sửa.','',
       f"CSV: `{campaign['csv']}`; SHA256 `{campaign['csv_sha256']}`. "
       f"Đã dùng toàn bộ {sum(g['unique_bits'] for g in campaign['coverage']):,} vị trí bit Alice/Bob thuộc {len(csv_rows)} dòng. "
       'Ghép riêng từng nhóm nhiễu; khối cuối chồng lên khối trước để không bỏ phần dư. '
       'Các khối chồng lặp và việc thử nhiều mã không tạo thêm mẫu độc lập.','',
       '## Dữ liệu Alice/Bob giữ nguyên từ CSV','',
       'Các ô là số khối sửa đúng / số khối thử. Mỗi khối có 2.765 bit khóa và 307 vị trí puncture, tổng 3.072 bit.','',
       '| Nhóm | r12 (1/2) | r23 (2/3) | r34 (3/4) | r56 (5/6) |',
       '|---|---:|---:|---:|---:|']
for group in campaign['coverage']:
    cells=[]
    for code in ['r12','r23','r34','r56']:
        rs=[r for r in native if r['group']==group['group'] and r['code']==code]
        cells.append(f"{sum(r['model_outcome']=='SUCCESS' for r in rs)}/{len(rs)}")
    lines.append('| '+group['group']+' | '+' | '.join(cells)+' |')
lines+=['','## Quét QBER có kiểm soát','',
        'Giữ Alice từ CSV, tạo Bob bằng đảo đúng số bit tại vị trí giả ngẫu nhiên không lặp. '
        'Mỗi QBER thử nhiều bộ vị trí/puncture theo số mẫu ở bảng; seed được lưu trong JSON. '
        'Đây là lỗi tạo thêm, không phải QBER gốc của CSV hay dữ liệu quang học thực. '
        'Mã được chọn bằng chính sách hiện có của mô hình, không thử cả bốn mã ở từng điểm quét.','',
        '| QBER yêu cầu | QBER thực trên 2.765 bit | Mã | Sửa đúng | Discard | Attempts trung bình |',
        '|---:|---:|---|---:|---:|---:|']
for target in sorted({r['target_qber_pct'] for r in sweep}):
    rs=[r for r in sweep if r['target_qber_pct']==target]
    ok=sum(r['model_outcome']=='SUCCESS' for r in rs)
    discard=sum(r['model_outcome']=='DISCARD' for r in rs)
    lines.append(f"| {target:g}% | {rs[0]['qber_pct']:.4f}% | {rs[0]['code']} | {ok}/{len(rs)} | {discard} | "
                 f"{sum(r['attempts'] for r in rs)/len(rs):.2f} |")
lines+=['','## Phạm vi bằng chứng','',
        'Không thấy trường hợp hội tụ nhưng sai khóa trong tập thử CSV/QBER này. '
        'Số mẫu nhỏ, có chồng lặp, chưa xác lập ngưỡng QBER bảo đảm hay tỷ lệ lỗi thống kê. '
        'Sửa lỗi thành công chưa chứng minh còn độ dài khóa bí mật dương sau rò rỉ syndrome/reveal, '
        'xác thực và phân tích finite-key. Dữ liệu CSV gốc cũng được ghi là mô phỏng.','',
        'JTAG chỉ nạp bitstream/ELF chung; tất cả payload kiểm thử được truyền qua UART. '
        'CRC32 bảo vệ lỗi truyền, không phải cơ chế xác thực bảo mật. '
        'Chưa kiểm thử đa context đồng thời, IRQ, thông lượng hay soak dài hạn.','',
        'ERRCNT chỉ được đối chiếu khi hội tụ; thanh ghi có thể giữ giá trị cũ khi discard. '
        'Các lượt dừng sớm trước đó được giữ trong thư mục uart_runs; chúng không được tính vào kết quả này.','',
        '[UART thô](uart.log) · [Receipt JSON](result.json) · [Từng khối CSV](blocks.csv) · '
        '[Manifest firmware](firmware_manifest.json) · [JTAG log](xsct.log)','']
if not sweep:
    first=lines.index('## Quét QBER có kiểm soát')
    last=lines.index('## Phạm vi bằng chứng')
    del lines[first:last]
(run/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
proof_files=['result.json','uart.log','xsct.log','blocks.csv','firmware_manifest.json','REPORT.md']
proof={'raw_receipts_verified':len(receipts),'pa_baseline_verified':True,'outcomes':dict(counts),
       'files':{name:hashlib.sha256((run/name).read_bytes()).hexdigest() for name in proof_files}}
(run/'verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
print('UART_RAW_EVIDENCE_VERIFY_PASS',len(receipts),run/'REPORT.md')
