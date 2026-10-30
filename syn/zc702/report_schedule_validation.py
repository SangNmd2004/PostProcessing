"""Check frozen train/held-out boundaries and raw timing/cycle receipts; report prediction errors honestly."""
from pathlib import Path
import argparse,csv,hashlib,json,random,re,statistics,struct,sys,zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
from zc702_resource_model import packet_workload,simulate
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path)
args=ap.parse_args();folder=args.run.resolve();result=json.loads((folder/'result.json').read_text())
assert result['complete'] and result['hardware_capture'] and not result.get('error')
config=result['config'];frozen=json.loads((folder/'frozen_model.json').read_text())
assert frozen==result['frozen_model'] and hashlib.sha256((folder/'frozen_model.json').read_bytes()).hexdigest()==result['frozen_model_sha256']
assert hashlib.sha256((folder/'resource_model_at_start.py').read_bytes()).hexdigest()==config['model_sha256']
assert hashlib.sha256((ROOT/'model/zc702_resource_model.py').read_bytes()).hexdigest()==config['model_sha256']
assert hashlib.sha256((folder/'runner_at_start.py').read_bytes()).hexdigest()==config['runner_sha256']
source=ROOT/config['source_ablation'];raw=(source/'result.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()==config['source_result_sha256']
ablation=json.loads(raw);parent_proof=ROOT/'reports'/('zc702_board_ablation_'+ablation['started_utc'])/'verified_evidence.json'
assert json.loads(parent_proof.read_text())['source_result_sha256']==config['source_result_sha256']
assert not {r['input_sha256'] for r in config['training']}&{r['input_sha256'] for r in config['held_out']}
for vector in config['training']+config['held_out']:
    data=struct.pack('<'+'I'*len(vector['payload']),*vector['payload'])
    assert hashlib.sha256(data).hexdigest()==vector['payload_sha256']
    assert packet_workload(vector['payload'])==vector['workload']
uart=(folder/'uart.log').read_text();xsct=(folder/'xsct.log').read_text(errors='replace')
assert 'ZC702_PROGRAM_MMIO_PASS' in xsct and 'ZC702_SMOKE_CPU_STARTED' in xsct
assert not re.search(r'FATAL|TIMEOUT|DMA_ERROR|MISMATCH',uart)
measurements={r['seq']:dict(r,scope='training') for r in result['training_measurements']}
for r in result['held_out_measurements']:assert r['seq'] not in measurements;measurements[r['seq']]=dict(r,scope='held_out')
assert max(r['seq'] for r in result['training_measurements'])<min(r['seq'] for r in result['held_out_measurements'])
cache={};seen=set()
for packet in json.loads((folder/'tx_manifest.json').read_text()):
    data=(folder/packet['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==packet['sha256'] and f'{zlib.crc32(data):08x}'==packet['crc32']
    values=struct.unpack('<'+'I'*(len(data)//4),data);seq=packet['seq']
    if values[0]==70:
        assert values[2]==len(values)-3;cache[values[1]]=list(values[3:]);continue
    assert values[0]==71 and seq in measurements and set(cache)=={0,1,2,3}
    row=measurements[seq];seen.add(seq)
    vectors=[config['training'][row['training_fixture']]]*4 if row['scope']=='training' else config['held_out']
    assert [cache[i] for i in range(4)]==[v['payload'] for v in vectors]
    assert values==(71,row['contexts'],row['jobs'],row['rtt_us'])
    work=[packet_workload(cache[i]) for i in range(4)]
    expected_busy=sum(sum(t['cycles'] for t in work[i%4]) for i in range(row['jobs']))
    attempts=sum(len(work[i%4]) for i in range(row['jobs']))
    response=re.search(fr'^QKD_BENCH_PASS seq={seq} contexts=(\d+) jobs=(\d+) corrected=(\d+) discarded=(\d+) attempts=(\d+) rtt_us=(\d+) elapsed_us=(\d+) busy_cycles=(\d+)',uart,re.MULTILINE);assert response
    assert list(map(int,response.groups()))==[row['contexts'],row['jobs'],row['jobs'],0,attempts,row['rtt_us'],row['elapsed_us'],expected_busy]
    assert expected_busy==row['busy_cycles']==row['predicted_busy_cycles']
assert seen==set(measurements)
x=[];y=[]
for row in result['training_measurements']:
    vector=config['training'][row['training_fixture']]
    x.append([4,4*sum(t['reveal_bits'] for t in vector['workload'])]);y.append(row['elapsed_us']-row['predicted_busy_cycles']/50)
x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float)
candidates=[np.zeros(2)];free=np.linalg.lstsq(x,y,rcond=None)[0]
if min(free)>=0:candidates.append(free)
for i in [0,1]:
    p=np.zeros(2);p[i]=max(0,float(x[:,i]@y/(x[:,i]@x[:,i]))) if np.any(x[:,i]) else 0;candidates.append(p)
fit=min(candidates,key=lambda p:float(np.sum((x@p-y)**2)))
assert np.allclose(fit,[frozen['load_us'],frozen['reveal_us_per_bit']],rtol=1e-12,atol=1e-10)
cases=[(k,rtt,rep) for k in [1,2,4] for rtt in [0,100,500,1000,5000,10000] for rep in range(config['repeats'])]
random.Random(2026102703).shuffle(cases)
assert [(r['contexts'],r['rtt_us'],r['repeat']) for r in result['held_out_measurements']]==cases
work=[r['workload'] for r in config['held_out']]
for row in result['held_out_measurements']:
    assert frozen['frozen_monotonic_ns']<=row['prediction_monotonic_ns']<=row['measurement_start_monotonic_ns']<=row['measurement_end_monotonic_ns']
    prediction=simulate(row['contexts'],work,row['jobs'],frozen['load_us'],frozen['reveal_us_per_bit'],row['rtt_us'])['elapsed_us']
    assert abs(prediction-row['predicted_elapsed_us'])<1e-8
    assert abs(row['prediction_error_pct']-100*(row['elapsed_us']-prediction)/prediction)<1e-9
errors=[abs(r['prediction_error_pct']) for r in result['held_out_measurements']]
accepted=statistics.mean(errors)<=config['latency_acceptance']['mean_absolute_error_pct_max'] and max(errors)<=config['latency_acceptance']['max_absolute_error_pct_max']
assert accepted==result['latency_model_accepted']
out=ROOT/'reports'/('zc702_schedule_validation_'+result['started_utc']);out.mkdir(parents=True,exist_ok=True)
def write(name,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
write('training.csv',result['training_measurements']);write('held_out.csv',result['held_out_measurements'])
summary=[]
for rtt in [0,100,500,1000,5000,10000]:
    reference=statistics.median(r['elapsed_us'] for r in result['held_out_measurements'] if r['contexts']==1 and r['rtt_us']==rtt)
    for k in [1,2,4]:
        group=[r for r in result['held_out_measurements'] if r['contexts']==k and r['rtt_us']==rtt]
        elapsed=statistics.median(r['elapsed_us'] for r in group);prediction=group[0]['predicted_elapsed_us']
        summary.append(dict(contexts=k,rtt_us=rtt,median_elapsed_us=elapsed,min_elapsed_us=min(r['elapsed_us'] for r in group),
            max_elapsed_us=max(r['elapsed_us'] for r in group),predicted_elapsed_us=prediction,error_pct=100*(elapsed-prediction)/prediction,
            measured_speedup_vs_K1=reference/elapsed,scope='DDR IR; repeated held-out vectors; UART/tag/PA excluded'))
write('summary.csv',summary)
proof=dict(raw_replay_verified=True,training_target_disjoint=True,decoder_busy_cycle_prediction_exact=True,
    calibration_measurements=len(result['training_measurements']),held_out_measurements=len(result['held_out_measurements']),
    mean_absolute_error_pct=statistics.mean(errors),max_absolute_error_pct=max(errors),latency_model_accepted=accepted,
    criteria=config['latency_acceptance'],source_result_sha256=hashlib.sha256((folder/'result.json').read_bytes()).hexdigest())
(out/'verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
text=['# Kiểm chứng mô hình hai tài nguyên trên workload held-out','',
      'Một decoder dùng chung, PS/DMA load/reveal tuần tự có thể chồng lên decode, context queue round robin. '
      'Cohort ET=PP=0, r0=0, chọn trước các job thành công strict trước iteration limit để công thức cycle không nhập nhằng đường USC. '
      'Model nhận trace attempts/iterations từ golden, chưa tự dự đoán trace hoặc FER từ QBER.','',
      f"Training load intercept={frozen['load_us']:.6f} µs/job, retry cost={frozen['reveal_us_per_bit']:.6f} µs/reveal bit. "
      'Chỉ fit các timing K1 training; tham số và model SHA đóng băng trước held-out. Tập trial/input hash training và held-out không giao nhau. '
      'Các vector từng được dùng trong ablation; timing validation K/RTT mới không được dùng để fit.','',
      f"Chu kỳ decoder khớp đúng trên toàn bộ {len(measurements)} batch calibration/validation. "
      f"Latency mean absolute error={statistics.mean(errors):.3f}%, max={max(errors):.3f}%. "
      f"Tiêu chí kỹ thuật chốt trước: mean≤10%, max≤20%; kết quả {'ACCEPTED' if accepted else 'NOT ACCEPTED — cần model/training mới rồi held-out mới'}. "
      'PASS raw replay không tự đồng nghĩa đạt tiêu chí model.','',
      '| K | RTT µs | Median board µs | Prediction µs | Error % | Speedup vs K1 |',
      '|---:|---:|---:|---:|---:|---:|']
for r in summary:text.append(f"| {r['contexts']} | {r['rtt_us']} | {r['median_elapsed_us']} | {r['predicted_elapsed_us']:.3f} | {r['error_pct']:.3f} | {r['measured_speedup_vs_K1']:.3f} |")
text+=['','Chưa mô hình hóa riêng IRQ, KEY-output contention, phân bố arrival hoặc kênh UART sản phẩm. '
       'Per-job load intercept gộp overhead output/control trung bình, không phải đo load thuần. RTT được chèn sau khi PS phát hiện FAIL. '
       'Bốn vector lặp lại không phải FER samples độc lập và không phải secret-key throughput. '
       'Thứ tự config random, ba lần lặp; min/max không phải CI. Không hiệu chỉnh lại tham số bằng các điểm held-out trong báo cáo này.','']
(out/'REPORT.md').write_text('\n'.join(text),encoding='utf-8')
print('SCHEDULE_RAW_REPLAY_PASS',out,'latency_model_accepted',accepted,flush=True)
