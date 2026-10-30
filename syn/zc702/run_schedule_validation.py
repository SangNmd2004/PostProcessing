"""Train PS/DMA costs on one cohort, freeze a two-resource model, measure disjoint held-out vectors."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,random,struct,subprocess,sys,time
import numpy as np
from uart_session import ROOT,UARTSession
sys.path.insert(0,str(ROOT/'model'))
from zc702_resource_model import packet_workload,simulate
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--ablation',required=True,type=Path)
ap.add_argument('--port',default='COM3');ap.add_argument('--jobs',type=int,default=32);ap.add_argument('--repeats',type=int,default=3)
args=ap.parse_args()
if args.jobs<4 or args.jobs%4 or args.jobs>128 or args.repeats<1:ap.error('jobs multiple of four in [4,128]')
source=args.ablation.resolve();ablation=json.loads((source/'result.json').read_text());n=ablation['config']['trials']
proof_path=ROOT/'reports'/('zc702_board_ablation_'+ablation['started_utc'])/'verified_evidence.json'
assert ablation['complete'] and n>=32
assert json.loads(proof_path.read_text())['source_result_sha256']==hashlib.sha256((source/'result.json').read_bytes()).hexdigest()
candidates=[]
for batch in ablation['batches']:
    if batch['configuration']!='NMS_GS':continue
    session=ROOT/batch['session'];frames={f['seq']:f for f in json.loads((session/'tx_manifest.json').read_text())}
    for slot,row in enumerate(batch['rows']):
        if row['outcome']!='SUCCESS':continue
        frame=frames[batch['load_seqs'][slot]];data=(session/frame['file']).read_bytes()
        assert hashlib.sha256(data).hexdigest()==frame['sha256']
        w=struct.unpack('<'+'I'*(len(data)//4),data);payload=w[3:]
        try:work=packet_workload(payload)
        except ValueError:continue
        candidates.append(dict(trial=row['trial'],input_sha256=row['input_sha256'],payload=list(payload),
                               payload_sha256=row['payload_sha256'],workload=work))
def choose(pool):
    pool=sorted(pool,key=lambda r:r['trial']);selected=[];attempts=set()
    for r in pool:
        if len(r['workload']) not in attempts:selected.append(r);attempts.add(len(r['workload']))
        if len(selected)==4:break
    for r in pool:
        if len(selected)==4:break
        if r['trial'] not in {x['trial'] for x in selected}:selected.append(r)
    assert len(selected)==4
    return selected
training=choose([r for r in candidates if r['trial']<n//2]);heldout=choose([r for r in candidates if r['trial']>=n//2])
assert not {r['input_sha256'] for r in training}&{r['input_sha256'] for r in heldout}
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');folder=ROOT/'build/zc702/schedule_validation_runs'/stamp;folder.mkdir(parents=True)
model_path=ROOT/'model/zc702_resource_model.py'
config=dict(jobs=args.jobs,repeats=args.repeats,clock_mhz=50,training=training,held_out=heldout,
            source_ablation=str(source.relative_to(ROOT)),source_result_sha256=hashlib.sha256((source/'result.json').read_bytes()).hexdigest(),
            model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
            runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            latency_acceptance=dict(mean_absolute_error_pct_max=10,max_absolute_error_pct_max=20,
                                    note='Predeclared engineering tolerances; not statistical confidence bounds'),
            selection='first distinct attempt counts then fill by trial ID; ET=PP=0, strict successes; latency cohort, not FER sampling')
(folder/'experiment_config.json').write_text(json.dumps(config,indent=2)+'\n')
(folder/'resource_model_at_start.py').write_bytes(model_path.read_bytes())
(folder/'runner_at_start.py').write_bytes(Path(__file__).read_bytes())
result=dict(complete=False,hardware_capture=True,started_utc=stamp,config=config,training_measurements=[],held_out_measurements=[])
def save():(folder/'result.json').write_text(json.dumps(result,indent=2)+'\n')
def fit_nonnegative(x,y):
    candidates=[np.zeros(2)];free=np.linalg.lstsq(x,y,rcond=None)[0]
    if min(free)>=0:candidates.append(free)
    for index in [0,1]:
        value=np.zeros(2);value[index]=max(0,float(x[:,index]@y/(x[:,index]@x[:,index]))) if np.any(x[:,index]) else 0
        candidates.append(value)
    return min(candidates,key=lambda p:float(np.sum((x@p-y)**2)))
try:
    with UARTSession(folder,args.port) as session:
        result['firmware_manifest']=session.manifest
        def load(vectors):
            for slot,vector in enumerate(vectors):
                payload=vector['payload'];session.command([70,slot,len(payload),*payload],r'QKD_BENCH_VECTOR seq={seq} index='+str(slot))
        def measure(k,jobs,rtt,repeat,workloads):
            seq,reply=session.command([71,k,jobs,rtt],r'QKD_BENCH_PASS seq={seq} contexts=(\d+) jobs=(\d+) corrected=(\d+) discarded=(\d+) attempts=(\d+) rtt_us=(\d+) elapsed_us=(\d+) busy_cycles=(\d+)')
            contexts,count,correct,discard,attempts,delay,elapsed,busy=map(int,reply.groups())
            expected_attempts=sum(len(workloads[i%len(workloads)]) for i in range(jobs))
            expected_busy=sum(sum(t['cycles'] for t in workloads[i%len(workloads)]) for i in range(jobs))
            assert [contexts,count,correct,discard,attempts,delay]==[k,jobs,jobs,0,expected_attempts,rtt]
            assert busy==expected_busy,('RTL-cycle model mismatch on this cohort',busy,expected_busy)
            return dict(seq=seq,contexts=k,jobs=jobs,rtt_us=rtt,repeat=repeat,elapsed_us=elapsed,
                        busy_cycles=busy,predicted_busy_cycles=expected_busy,attempts=attempts)
        for i,vector in enumerate(training):
            load([vector]*4)
            for repeat in range(args.repeats):
                row=measure(1,4,0,repeat,[vector['workload']]);row['training_fixture']=i
                result['training_measurements'].append(row);save()
        x=[];y=[]
        for row in result['training_measurements']:
            vector=training[row['training_fixture']]
            revealed=sum(t['reveal_bits'] for t in vector['workload'])*4
            x.append([4,revealed]);y.append(row['elapsed_us']-row['predicted_busy_cycles']/50)
        x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float);assert np.linalg.matrix_rank(x)==2
        params=fit_nonnegative(x,y);assert params[0]>0
        frozen=dict(load_us=float(params[0]),reveal_us_per_bit=float(params[1]),decoder_model='28 + iterations*C_iter + (E+8*layers+1 if final USC)',
                    training='K1 DDR, four copies of one training fixture per batch; no held-out target timing in fit',
                    frozen_before_validation_utc=datetime.now(timezone.utc).isoformat(),frozen_monotonic_ns=time.perf_counter_ns(),model_sha256=config['model_sha256'],
                    assumptions='One decoder, serial PS/DMA input and reveal, RR queue. Per-job output/control approximated in load intercept. No separate IRQ/KEY contention model.')
        (folder/'frozen_model.json').write_text(json.dumps(frozen,indent=2)+'\n');result['frozen_model']=frozen
        result['frozen_model_sha256']=hashlib.sha256((folder/'frozen_model.json').read_bytes()).hexdigest();save()
        print('SCHEDULE_MODEL_FROZEN',json.dumps(frozen),flush=True)
        load(heldout);workloads=[r['workload'] for r in heldout]
        cases=[(k,rtt,repeat) for k in [1,2,4] for rtt in [0,100,500,1000,5000,10000] for repeat in range(args.repeats)]
        random.Random(2026102703).shuffle(cases)
        for k,rtt,repeat in cases:
            prediction=simulate(k,workloads,args.jobs,frozen['load_us'],frozen['reveal_us_per_bit'],rtt)
            predicted_at=time.perf_counter_ns();measurement_start=time.perf_counter_ns()
            row=measure(k,args.jobs,rtt,repeat,workloads)
            row.update(predicted_elapsed_us=prediction['elapsed_us'],prediction_error_pct=100*(row['elapsed_us']-prediction['elapsed_us'])/prediction['elapsed_us'],
                       prediction_monotonic_ns=predicted_at,measurement_start_monotonic_ns=measurement_start,measurement_end_monotonic_ns=time.perf_counter_ns())
            result['held_out_measurements'].append(row);save()
            print('SCHEDULE_HELD_OUT',len(result['held_out_measurements']),'/',len(cases),'K',k,'RTT',rtt,'error_pct',row['prediction_error_pct'],flush=True)
        errors=[abs(r['prediction_error_pct']) for r in result['held_out_measurements']]
        result['latency_model_accepted']=bool(np.mean(errors)<=10 and max(errors)<=20)
        result['complete']=True
except BaseException as exc:result['error']=repr(exc);raise
finally:save();print('SCHEDULE_VALIDATION_EVIDENCE',folder,flush=True)
subprocess.run([sys.executable,str(ROOT/'syn/zc702/report_schedule_validation.py'),str(folder)],check=True)
print('SCHEDULE_BOARD_COMPARISON_COMPLETE',folder,'latency_model_accepted',result['latency_model_accepted'],flush=True)
