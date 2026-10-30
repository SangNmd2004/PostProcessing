"""Export Excel-friendly per-block and aggregate CSVs from verified board evidence."""
from pathlib import Path
import argparse
import collections
import csv
import hashlib
import json
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('run', type=Path)
args = ap.parse_args()
run = args.run.resolve()
subprocess.run([sys.executable, str(ROOT/'syn/zc702/report_uart_campaign.py'), str(run)], check=True)
result = json.loads((run/'result.json').read_text())
campaign_path = Path(result['source_campaign'])
campaign = json.loads(campaign_path.read_text())
out = ROOT/'reports'/('zc702_uart_'+result['started_utc'])
out.mkdir(parents=True, exist_ok=True)
rows = []
for record in result['records']:
    payload = (campaign_path.parent/record['file']).read_bytes()
    words = struct.unpack('<'+'I'*(len(payload)//4), payload)
    cfg, cfg2, pre, attempts, syn_words, expected_errcnt, reveal_words = words[:7]
    expected = words[7:7+attempts]
    conv = record['hardware_conv']
    known = record['source'] != 'baseline'
    rows.append({
        'run_utc':result['started_utc'], 'board':'ZC702', 'uart_port':result['port'],
        'sequence':record['seq'], 'source':record['source'],
        'group':record.get('group',''), 'source_block':record.get('block',''),
        'input_test_ids':';'.join(str(r['test_id']) for r in record.get('input_rows',[])),
        'input_row_ranges_json':json.dumps(record.get('input_rows',[]),separators=(',',':')),
        'source_bit_start':record.get('bit_start',record.get('alice_start','')),
        'repeat':record.get('repeat',''), 'seed':record.get('seed',''),
        'code':['r12','r23','r34','r56'][cfg & 3],
        'check_node_mode':'nms75' if cfg2&32 else 'oms', 'puncturing':record.get('puncturing','not_recorded'),
        'ldpc_bits':3072, 'key_bits':2765, 'puncture_bits':307,
        'target_qber_pct':record.get('target_qber_pct',''),
        'actual_qber_pct':record.get('qber_pct',''),
        'input_error_bits':round(record['qber_pct']/100*2765) if 'qber_pct' in record else '',
        'hardware_match':int(record['hardware_match']), 'hardware_converged':int(conv),
        'outcome':record['model_outcome'], 'attempts':record['hardware_attempts'],
        'iterations_sum_checked':sum(v & 0xfff for v in expected),
        'revealed_bits':reveal_words, 'pre_revealed_bits':pre,
        'syndrome_bits':syn_words*32,
        'errcnt_valid':int(conv), 'errcnt':record['hardware_errcnt'] if conv else '',
        'residual_errors_received_key':record.get('residual_errors','') if conv and known else '',
        'correction_outcome_known':int(known),
        'packet_bytes':len(payload), 'packet_crc32':record['crc32'],
        'packet_sha256':record['sha256'], 'source_result':str(run/'result.json')})

def write_csv(path, values):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(values[0]))
        writer.writeheader(); writer.writerows(values)

write_csv(out/'chi_tiet_block.csv', rows)
summary = []
def summarize(scope, source, group, code, target, subset):
    known = [r for r in subset if r['correction_outcome_known']]
    success = sum(r['outcome']=='SUCCESS' for r in subset)
    qbers = [r['actual_qber_pct'] for r in subset if r['actual_qber_pct']!='']
    summary.append({
        'run_utc':result['started_utc'], 'scope':scope, 'source':source, 'group':group,
        'code':code, 'target_qber_pct':target,
        'blocks_tested':len(subset), 'hardware_matches':sum(r['hardware_match'] for r in subset),
        'hardware_match_pct':100*sum(r['hardware_match'] for r in subset)/len(subset),
        'converged':sum(r['hardware_converged'] for r in subset),
        'corrected_success':success, 'discard':sum(r['outcome']=='DISCARD' for r in subset),
        'undetected_error':sum(r['outcome']=='UNDETECTED' for r in subset),
        'converged_without_csv_correction_label':sum(r['outcome']=='CONVERGED' for r in subset),
        'correction_rate_denominator':len(known),
        'correction_success_pct':100*success/len(known) if known else '',
        'actual_qber_min_pct':min(qbers) if qbers else '',
        'actual_qber_max_pct':max(qbers) if qbers else '',
        'attempts_avg':sum(r['attempts'] for r in subset)/len(subset),
        'attempts_max':max(r['attempts'] for r in subset),
        'revealed_bits_avg':sum(r['revealed_bits'] for r in subset)/len(subset),
        'unique_csv_bits_in_campaign':sum(g['unique_bits'] for g in campaign['coverage']) if scope=='overall' else '',
        'note':'Repeated codes and overlapping tail blocks are not independent samples.'})

summarize('overall','ALL','ALL','ALL','',rows)
for source in dict.fromkeys(r['source'] for r in rows):
    subset = [r for r in rows if r['source']==source]
    summarize('source',source,'ALL','ALL','',subset)
for group in campaign['coverage']:
    subset = [r for r in rows if r['source']=='csv_native' and r['group']==group['group']]
    summarize('csv_group','csv_native',group['group'],'ALL','',subset)
    for code in ['r12','r23','r34','r56']:
        rs = [r for r in subset if r['code']==code]
        if rs:summarize('csv_group_code','csv_native',group['group'],code,'',rs)
targets = sorted({r['target_qber_pct'] for r in rows if r['source']=='controlled_qber'})
for target in targets:
    subset = [r for r in rows if r['source']=='controlled_qber' and r['target_qber_pct']==target]
    summarize('qber_sweep','controlled_qber','',subset[0]['code'],target,subset)
write_csv(out/'tong_hop.csv', summary)
extra_files=[]
if campaign.get('native_only'):
    # Audit every original bit interval against completed hardware receipts, per code.
    coverage_rows=[]
    for group in campaign['coverage']:
        for original in group['rows']:
            audit={'test_id':original['test_id'],'group':group['group'],'original_key_bits':original['bits'],
                   'original_error_bits':original['errors'],'original_qber_pct':original['qber_pct']}
            for code in ['r12','r23','r34','r56']:
                intervals=[];related=[]
                for record in result['records']:
                    if record.get('group')!=group['group'] or record['code']!=code:continue
                    for fragment in record['input_rows']:
                        if fragment['test_id']==original['test_id']:
                            assert record['hardware_match']
                            lo=fragment['row_bit_start'];hi=lo+fragment['bits']
                            intervals.append((lo,hi));related.append(record)
                end=0
                for lo,hi in sorted(intervals):
                    assert lo<=end, (original['test_id'],code,'uncovered gap')
                    end=max(end,hi)
                assert end==original['bits'], (original['test_id'],code,'incomplete coverage')
                audit[code+'_covered_unique_bits']=end
                audit[code+'_containing_blocks']=len(related)
                audit[code+'_successful_containing_blocks']=sum(r['model_outcome']=='SUCCESS' for r in related)
                audit[code+'_discarded_containing_blocks']=sum(r['model_outcome']=='DISCARD' for r in related)
                audit[code+'_sequences']=';'.join(str(r['seq']) for r in related)
            audit['note']='Coverage per original row; outcomes refer to containing concatenated blocks, not an isolated row test.'
            coverage_rows.append(audit)
    assert len({r['test_id'] for r in coverage_rows})==len(coverage_rows)
    with Path(campaign['csv']).open(encoding='utf-8-sig',newline='') as source_file:
        originals={int(r['test_id']):r for r in csv.DictReader(source_file)}
    assert {r['test_id'] for r in coverage_rows}==set(originals)
    for audit in coverage_rows:
        original=originals[audit['test_id']]
        assert audit['original_key_bits']==len(original['key_alice'])==int(original['key_length'])
        assert audit['original_error_bits']==sum(a!=b for a,b in zip(original['key_alice'],original['key_bob']))
    write_csv(out/'doi_chieu_tung_dong_csv.csv',coverage_rows)
    extra_files.append(out/'doi_chieu_tung_dong_csv.csv')
assert len(rows)==result['requested']
assert sum(r['blocks_tested'] for r in summary if r['scope']=='source')==len(rows)
for name, expected_count in [('chi_tiet_block.csv',len(rows)),('tong_hop.csv',len(summary))]:
    with (out/name).open(encoding='utf-8-sig',newline='') as stream:
        assert len(list(csv.DictReader(stream)))==expected_count
(out/'README.md').write_text(
    '# Báo cáo CSV ZC702 UART\n\n'
    f'Nguồn: `{run}`. Hai CSV dùng UTF-8 BOM, dấu phẩy, có header để mở bằng Excel.\n\n'
    '- `chi_tiet_block.csv`: mỗi dòng là một lượt block/mã, gồm QBER, outcome, retry, reveal, ERRCNT và hash packet.\n'
    '- `tong_hop.csv`: chọn cột `scope` để xem overall, source, csv_group, csv_group_code hoặc qber_sweep. '
    'Các scope là các cách nhìn cùng dữ liệu; không cộng tất cả dòng tổng hợp với nhau.\n\n'
    '`hardware_match=1` gồm cả DISCARD đúng dự kiến. `SUCCESS` mới là sửa đúng khóa Alice của CSV/quét QBER. '
    'Tỷ lệ sửa đúng dùng `correction_rate_denominator`, loại bộ baseline không có nhãn sửa đúng CSV. '
    'ERRCNT trống khi discard vì thanh ghi có thể giữ giá trị cũ. Lỗi còn lại trống khi không có KEY nhận về. '
    'QBER baseline không được ghi trong receipt nên để trống. `iterations_sum_checked` là tổng giá trị thanh ghi '
    'iterations đã đối chiếu theo từng attempt, không phải số chu kỳ hay thời gian đo.\n\n'
    f"Toàn bộ {sum(g['unique_bits'] for g in campaign['coverage']):,} vị trí bit của CSV được dùng; có chồng lặp khối cuối và thử lại bốn mã. "
    'Không xem các lượt này là mẫu độc lập. Phép quét chủ động (nếu có) tạo lỗi ở Bob; CSV nguồn là mô phỏng. '
    'Nếu có `doi_chieu_tung_dong_csv.csv`, file này đối chiếu từng test_id và chứng minh đủ vị trí bit được chạy với cả bốn mã. '
    'Các cột successful/discarded_containing_blocks là kết quả block ghép chứa dòng đó, không phải kết quả sửa lỗi riêng dòng. '
    'Đây là kiểm thử IR trên board; PA chỉ có vector chuẩn lúc khởi động, chưa ghép khóa CSV vào PA.\n',encoding='utf-8')
manifest = {'source_result_sha256':hashlib.sha256((run/'result.json').read_bytes()).hexdigest(),
            'block_rows':len(rows),'summary_rows':len(summary),
            'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                     [out/'chi_tiet_block.csv',out/'tong_hop.csv',out/'README.md',*extra_files]}}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('CSV_REPORT_EXPORT_PASS',len(rows),'blocks,',len(summary),'summary rows:',out)
