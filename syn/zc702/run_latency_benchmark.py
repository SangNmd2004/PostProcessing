"""Measured DDR-replay IR scheduler benchmark with injected reveal delay.

Four repeated public golden blocks, not FER samples or end-to-end secret keys.
K1/RTT0 calibration is frozen before held-out K/RTT conditions are measured.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,hashlib,json,random,statistics,struct,sys
from uart_session import UARTSession,ROOT
sys.path.insert(0,str(ROOT/'model'))
from queue_latency_model import simulate_blind_jobs
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--port',default='COM3');ap.add_argument('--jobs',type=int,default=32);ap.add_argument('--repeats',type=int,default=3)
args=ap.parse_args()
if args.jobs<4 or args.jobs>128 or args.jobs%4 or args.repeats<1:ap.error('jobs must be a multiple of 4 in [4,128]; repeats positive')
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');folder=ROOT/'build/zc702/latency_runs'/stamp;folder.mkdir(parents=True)
campaign_dir=ROOT/'build/zc702/uart_csv_nms_gs';campaign=json.loads((campaign_dir/'campaign.json').read_text())
selected=[r for r in campaign['records'] if r['model_outcome']=='SUCCESS' and r['attempts']>1][:4]
assert len(selected)==4
result={'complete':False,'hardware_capture':True,'started_utc':stamp,'scope':'DDR_replay_IR_only','independent_FER_trials':False,
        'clock_mhz':50,'port':args.port,'vectors':selected,'records':[]}
def save():(folder/'result.json').write_text(json.dumps(result,indent=2)+'\n')
try:
    with UARTSession(folder,args.port) as session:
        result['firmware_manifest']=session.manifest
        for index,r in enumerate(selected):
            payload=(campaign_dir/r['file']).read_bytes();assert hashlib.sha256(payload).hexdigest()==r['sha256']
            values=struct.unpack('<'+'I'*(len(payload)//4),payload)
            session.command([70,index,len(values),*values],r'QKD_BENCH_VECTOR seq={seq} index='+str(index))
        attempts=sum(r['attempts'] for r in selected)*(args.jobs//4)
        def measure(k,rtt,rep,scope):
            _,reply=session.command([71,k,args.jobs,rtt],r'QKD_BENCH_PASS seq={seq} contexts=(\d+) jobs=(\d+) corrected=(\d+) discarded=(\d+) attempts=(\d+) rtt_us=(\d+) elapsed_us=(\d+) busy_cycles=(\d+)')
            contexts,jobs,corrected,discarded,att,rtt_actual,elapsed,busy=map(int,reply.groups())
            assert [contexts,jobs,corrected,discarded,att,rtt_actual]==[k,args.jobs,args.jobs,0,attempts,rtt]
            row={'contexts':k,'jobs':jobs,'repeat':rep,'rtt_us':rtt,'elapsed_us':elapsed,'decoder_busy_cycles':busy,
                 'attempts':att,'corrected_blocks':corrected,'IR_corrected_Mbit_s':jobs*2765/elapsed,'scope':scope}
            result['records'].append(row);save()
            print('IR_BENCH_MEASURED',k,'RTT',rtt,'us','elapsed',elapsed,'us',row['IR_corrected_Mbit_s'],'Mbit/s',flush=True)
            return row
        calibration=[measure(1,0,rep,'calibration_K1_RTT0') for rep in range(args.repeats)]
        service=statistics.median(r['elapsed_us'] for r in calibration)/attempts
        params={'service_us_per_attempt':service,'calibration':'K1 RTT0 only','frozen_before_validation':True,
                'model_sha256':hashlib.sha256((ROOT/'model/queue_latency_model.py').read_bytes()).hexdigest(),
                'assumptions':'constant mean attempt service including averaged software/load overhead; no UART/PA; RTT only on failed attempts'}
        (folder/'frozen_model.json').write_text(json.dumps(params,indent=2)+'\n');result['model']=params
        cases=[(k,rtt,rep) for k in [1,2,4] for rtt in [0,100,1000,10000] for rep in range(args.repeats) if (k,rtt)!=(1,0)]
        random.Random(20261026).shuffle(cases)
        for k,rtt,rep in cases:
            predicted=simulate_blind_jobs(k,service,rtt,[r['attempts'] for r in selected],args.jobs)
            row=measure(k,rtt,rep,'held_out_K_RTT');row['predicted_elapsed_us']=predicted
            row['prediction_relative_error']=(row['elapsed_us']-predicted)/predicted;save()
        result['complete']=True
except BaseException as exc:result['error']=repr(exc);raise
finally:save();print('LATENCY_EVIDENCE',folder,flush=True)
out=ROOT/'reports'/('zc702_latency_'+stamp);out.mkdir(parents=True)
fields=list(dict.fromkeys(k for r in result['records'] for k in r))
with (out/'measurements.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(result['records'])
summary=[]
for rtt in [0,100,1000,10000]:
    baseline=statistics.median(r['elapsed_us'] for r in result['records'] if r['contexts']==1 and r['rtt_us']==rtt)
    for k in [1,2,4]:
        rows=[r for r in result['records'] if r['contexts']==k and r['rtt_us']==rtt]
        median=statistics.median(r['elapsed_us'] for r in rows)
        predicted=simulate_blind_jobs(k,service,rtt,[r['attempts'] for r in selected],args.jobs)
        summary.append({'contexts':k,'rtt_us':rtt,'median_elapsed_us':median,'measured_speedup_vs_K1':baseline/median,
                        'IR_corrected_Mbit_s':args.jobs*2765/median,'predicted_elapsed_us':predicted,
                        'model_error_pct':100*(median-predicted)/predicted,'scope':'DDR replay; repeated vectors; PA/UART excluded'})
with (out/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
lines=['# IR latency benchmark trên ZC702','',
       'DDR replay, PL 50 MHz, timer Cortex-A9. Không có UART hoặc tính Python trong vòng được đo. '
       'Bốn vector chuẩn lặp lại, không phải mẫu FER độc lập; không phải thông lượng khóa bí mật hay hệ quang. '
       'Thời gian có bao gồm phần kiểm tra correctness bằng golden trong vòng đo. '
       'RTT là độ trễ thêm sau khi PS phát hiện FAIL trước REVEAL; không gồm lần trao đổi syndrome ban đầu.','',
       '| K | Reveal RTT µs | Median µs | Tăng tốc đo so K1 | IR Mbit/s | Sai số model % |',
       '|---:|---:|---:|---:|---:|---:|']
for r in summary:lines.append(f"| {r['contexts']} | {r['rtt_us']} | {r['median_elapsed_us']} | {r['measured_speedup_vs_K1']:.3f} | {r['IR_corrected_Mbit_s']:.4f} | {r['model_error_pct']:.2f} |")
lines+=['','Model được đóng băng sau K1/RTT0 trước điều kiện kiểm chứng. Là mô hình service trung bình đơn giản; '
        'khác biệt giữa vector, DMA/load/reveal và polling có thể gây sai số. Không hiệu chỉnh lại tham số từ dữ liệu held-out trong báo cáo này.','',
        f'[Raw receipt](../../build/zc702/latency_runs/{stamp}/result.json) · '
        f'[UART](../../build/zc702/latency_runs/{stamp}/uart.log)','']
(out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
print('IR_LATENCY_BENCHMARK_PASS',out,flush=True)
