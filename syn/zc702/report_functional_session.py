"""Check raw functional-session receipts and export board evidence/report CSVs."""
from pathlib import Path
import argparse,collections,csv,hashlib,json,re,struct

ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('run',type=Path)
args=parser.parse_args();folder=args.run.resolve()
result=json.loads((folder/'result.json').read_text())
assert result['complete'] and result['hardware_capture']
uart=(folder/'uart.log').read_text();xsct=(folder/'xsct.log').read_text(errors='replace')
assert not re.search(r'FATAL|TIMEOUT|DMA_ERROR|MISMATCH',uart)
assert 'ZC702_PROGRAM_MMIO_PASS' in xsct and 'ZC702_SMOKE_CPU_STARTED' in xsct
assert 'QKD_PA_VECTOR_PASS bits=4096' in uart
key_groups=collections.OrderedDict();pa_groups=collections.OrderedDict()
for seq,index,value in re.findall(r'QKD_FUNC_KEY seq=(\d+) word=(\d+) value=([0-9a-fA-F]{16})',uart):
    key_groups.setdefault(seq,[]).append((int(index),int(value,16)))
for seq,index,value in re.findall(r'QKD_FUNC_PA seq=(\d+) word=(\d+) value=([0-9a-fA-F]{16})',uart):
    pa_groups.setdefault(seq,[]).append((int(index),int(value,16)))
converged=[r for r in result['records'] if r['outcome'] in ('SUCCESS','UNDETECTED_CODEWORD')]
assert len(key_groups)==len(converged)
for group,row in zip(key_groups.values(),converged):
    assert [index for index,_ in group]==list(range(48))
    assert hashlib.sha256(struct.pack('<48Q',*[v for _,v in group])).hexdigest()==row['key_sha256']
passed=[r for r in result['records'] if r['pa_pass']]
assert len(pa_groups)==len(passed)==len(re.findall(r'QKD_FUNC_PIPE_PASS seq=',uart))
for group,row in zip(pa_groups.values(),passed):
    assert [index for index,_ in group]==list(range(16))
    assert hashlib.sha256(struct.pack('<16Q',*[v for _,v in group])).hexdigest()==row['pa_sha256']
assert len(re.findall(r'QKD_FUNC_TAG_REJECT seq=',uart))==sum(r['verification_rejected'] for r in result['records'])
actual_attempts=re.findall(r'QKD_FUNC_ATTEMPT seq=\d+ status=([0-9a-fA-F]+) iters=([0-9a-fA-F]+) errcnt=(\d+) cycles=(\d+) ticks=(\d+)',uart)
record_attempts=[a for r in result['records'] for a in r['attempts']]
assert len(actual_attempts)==len(record_attempts)
for raw,record in zip(actual_attempts,record_attempts):
    status,iters,errcnt,cycles,ticks=raw
    assert int(status,16)==record['status'] and int(iters,16)==record['iters']
    assert int(cycles)==record['decoder_cycles'] and int(ticks)==record['elapsed_timer_ticks']
    assert record['errcnt'] is None or int(errcnt)==record['errcnt']
raw_irqs=re.findall(r'QKD_FUNC_IRQ_RESULT seq=\d+ count=(\d+) status=([0-9a-fA-F]+)',uart)
irq_records=[r for r in record_attempts if 'irq_count' in r]
assert len(raw_irqs)==len(irq_records)
for (count,status),record in zip(raw_irqs,irq_records):
    assert int(count)==record['irq_count']==1 and int(status,16)==record['irq_status']
checks=result.get('control_checks',[])
raw_checks=re.findall(r'QKD_FUNC_ACC_DECISION seq=\d+ action=(\d+) ell=(\d+) split=(\d+) emit_n=(\d+)',uart)
assert len(raw_checks)==len(checks)
for raw,check in zip(raw_checks,checks):
    assert int(raw[0])=={'wait':0,'emit':1,'abort':2}[check['action']]
    assert int(raw[1])==check['ell_rounded'] and bool(int(raw[2]))==check['split']
mc=result.get('multicontext_checks',[])
mc_keys=collections.OrderedDict()
for seq,ctx,index,value in re.findall(r'QKD_FUNC_MC_KEY seq=(\d+) ctx=(\d+) word=(\d+) value=([0-9a-fA-F]{16})',uart):
    mc_keys.setdefault((seq,int(ctx)),[]).append((int(index),int(value,16)))
for _,summary,rx,owner in re.findall(r'QKD_FUNC_MC_STATUS seq=(\d+) summary=([0-9a-fA-F]+) rx=(\d+) owner=(\d+)',uart):
    if int(rx):assert (int(summary,16)>>16)&15==1<<int(owner),'ambiguous S2MM ownership'
if mc:
    assert len(mc)==4 and {r['ctx'] for r in mc}==set(range(4)) and 'QKD_FUNC_MC_DONE' in uart
    assert len(mc_keys)==sum(r['outcome']=='SUCCESS' for r in mc)
    for (_,ctx),group in mc_keys.items():
        record=next(r for r in mc if r['ctx']==ctx)
        assert [i for i,_ in group]==list(range(48))
        assert hashlib.sha256(struct.pack('<48Q',*[v for _,v in group])).hexdigest()==record['key_sha256']
out=ROOT/'reports'/('zc702_functional_'+result['started_utc']);out.mkdir(exist_ok=True,parents=True)
def write(name,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
records=[];attempt_rows=[]
for row in result['records']:
    item={k:v for k,v in row.items() if k!='attempts'};records.append(item)
    for index,attempt in enumerate(row['attempts']):
        attempt_rows.append(dict(policy=row['policy'],group=row['group'],block=row['block'],attempt=index+1,**attempt))
write('chi_tiet_phien.csv',records);write('tung_attempt.csv',attempt_rows)
write('decoy_mo_phong.csv',checks);write('bon_context.csv',mc)
summary=[]
for policy in dict.fromkeys(r['policy'] for r in records):
    rs=[r for r in records if r['policy']==policy]
    summary.append({'policy':policy,'cases':len(rs),'ir_success':sum(r['outcome']=='SUCCESS' for r in rs),
                    'early_discard':sum(r['outcome']=='EARLY_DISCARD' for r in rs),
                    'decoder_discard':sum(r['outcome']=='DISCARD' for r in rs),
                    'pa_pass':sum(r['pa_pass'] for r in rs),'tag_rejected':sum(r['verification_rejected'] for r in rs)})
write('tong_hop.csv',summary)
lines=['# Nghiệm thu chức năng: ARM + IR + xác minh + PA','',
       f"Lượt `{result['started_utc']}` trên ZC702, PL 50 MHz; Alice mô phỏng PC, UART, seed công khai từ PC OS CSPRNG.",'',
       '| Policy | Ca thử | IR sửa đúng | Loại sớm | Decoder discard | PA khớp | Tag bị từ chối |',
       '|---|---:|---:|---:|---:|---:|---:|']
for row in summary:lines.append('| '+' | '.join(str(row[k]) for k in ['policy','cases','ir_success','early_discard','decoder_discard','pa_pass','tag_rejected'])+' |')
lines+=['',f"Đã đối chiếu log thô: {len(actual_attempts)} attempt, {len(key_groups)} KEY, {len(pa_groups)} PA; "
        f"{len(checks)} quyết định accumulator mô phỏng; {len(mc)} context trong phép thử nhiều bank.",'',
        'ARM chạy các hàm chọn profile/plan/next_reveal/update trích từ driver tham chiếu. '
        'Host chỉ mô phỏng Alice, cấp syndrome/reveal và kiểm tra mô hình sau từng phản hồi phần cứng. '
        'KEY đọc từ DMA được bỏ 307 vị trí D, đệm zero tới 2784 bit, rồi đi qua PA FPGA để tạo tag 64 bit và hash 1024 bit. '
        'Một tag được cố ý làm sai; firmware từ chối và không phát PA cuối cùng cho ca đó.','',
        ('Bốn context được nạp HOLD và cùng đưa vào hàng đợi. DMA nhận từng frame; cờ SUCCESS duy nhất xác định context '
        'trước khi nhận frame tiếp. Kiểm tra dừng nếu ownership mơ hồ; không giả định DDR giữ TUSER. '
        'Phép thử này chưa xác nhận mức tăng thông lượng hay RTT theo tài liệu.' if mc else 'Lượt này không chạy phép thử bốn context.'),'',
        'Thống kê decoy trong phép thử accumulator lấy từ phiên mô phỏng có sẵn; không ghép với khóa CSV và chưa phát '
        'khóa tích lũy theo độ dài finite-key. PE 256 bit của ca IR là mẫu công khai trong harness, vẫn nằm trong đầu vào hash '
        'chức năng; chưa có xử lý loại mẫu/tính leakage để tuyên bố khóa bí mật. '
        'Backlog là kích thích được lập trước để kiểm tra hysteresis, không phải hàng đợi đo từ luồng quang.','',
        f'IRQ lõi QKD đã được đối chiếu ở {len(raw_irqs)} attempt trong lượt này; ISR mask nguồn, polling vẫn dùng để chờ kết quả. '
        'Chưa xác nhận ngắt DMA hay bộ lập lịch hoàn toàn theo ngắt. '
        'Chưa nghiệm thu 70 MHz, FER trên 10⁴ block độc lập, PA khối lớn, TRNG vật lý hay kênh xác thực Alice/Bob.','',
        f'[Receipt](../../build/zc702/functional_runs/{result["started_utc"]}/result.json) · '
        f'[UART thô](../../build/zc702/functional_runs/{result["started_utc"]}/uart.log)','']
(out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
proof={'raw_receipts_verified':True,'ir_cases':len(records),'ir_attempts':len(actual_attempts),'keys':len(key_groups),
       'qkd_irq_receipts':len(raw_irqs),
       'pa_outputs':len(pa_groups),'accumulator_checks':len(checks),'multicontext_checks':len(mc),
       'source_files':{name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ['result.json','uart.log','xsct.log']}}
(out/'verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
print('FUNCTIONAL_RAW_VERIFY_PASS',out)
