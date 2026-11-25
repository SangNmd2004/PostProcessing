"""Independent BSC trials, exact golden IR traces, one physical evaluation per vector.

The component benchmark checks every status/key against golden data in PL path.
It does not apply verification tags or PA; wrong codewords are classified by
ground truth, not called tag rejections. Resume preserves a unique seed/trial ID.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,collections,csv,hashlib,json,struct,sys,time,subprocess
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
import ir_model as m
import eval_csv as ev
import puncture as pu
from experiment_metrics import wilson_interval,zero_failures_upper
from generate_uart_campaign import encode
from uart_session import UARTSession

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--port',default='COM3');ap.add_argument('--trials',type=int,default=256)
ap.add_argument('--qber',type=float,default=.03);ap.add_argument('--code',choices=m.CODE_ORDER,default='r23')
ap.add_argument('--seed-base',type=int,default=200000);ap.add_argument('--resume',type=Path)
ap.add_argument('--max-batches',type=int,help='Stop cleanly at a verified batch boundary for resume validation')
args=ap.parse_args()
if args.trials<4 or args.trials%4 or not 0<=args.qber<=.2:ap.error('trials must be a multiple of 4, QBER in [0,0.2]')
if args.resume:
    folder=args.resume.resolve();result=json.loads((folder/'result.json').read_text())
    assert result['planned_trials']==args.trials and result['qber']==args.qber and result['code']==args.code and result['seed_base']==args.seed_base
    journal=folder/'verified_batches.jsonl'
    if journal.exists():
        recovered={r['trial_id']:r for r in result['records']}
        lines=journal.read_text().splitlines()
        for index,line in enumerate(lines):
            try:batch=json.loads(line)
            except json.JSONDecodeError:
                if index!=len(lines)-1:raise
                raise RuntimeError('Incomplete journal tail: recover explicitly before resuming')
            for row in batch:
                if row['trial_id'] in recovered:assert recovered[row['trial_id']]==row
                recovered[row['trial_id']]=row
        result['records']=[recovered[i] for i in range(len(recovered))]
else:
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');folder=ROOT/'build/zc702/fer_runs'/stamp;folder.mkdir(parents=True)
    result={'complete':False,'hardware_capture':True,'started_utc':stamp,'planned_trials':args.trials,'qber':args.qber,
            'code':args.code,'seed_base':args.seed_base,'channel':'independent Bernoulli bit flips (synthetic BSC)',
            'cn':'nms75','puncturing':'gs','FER_definition':'decoder discard OR converged wrong key; transport/hardware errors reported separately',
            'verification_tags_applied':False,'records':[],'attempt_sessions':[]}
if 'error' in result:result.setdefault('previous_session_errors',[]).append(result.pop('error'))
result['complete']=False
snapshot=Path(__file__).read_bytes();(folder/'runner_at_start.py').write_bytes(snapshot)
result['runner_sha256']=hashlib.sha256(snapshot).hexdigest()
result['model_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
    [ROOT/'model/ir_model.py',ROOT/'model/eval_csv.py',ROOT/'model/codes.json',ROOT/'model/punct.json']}
def save():
    target=folder/'result.json';temp=folder/'result.json.tmp'
    temp.write_text(json.dumps(result,indent=2)+'\n')
    for retry in range(4):
        try:temp.replace(target);return
        except PermissionError:
            if retry==3:raise
            time.sleep(.05)
base=m.load_codes(128)[args.code];positions=pu.order(args.code,base,128,307);m.CN_MODE='nms75'
cfg=m.CODE_ORDER.index(args.code)|(8<<2)|(50<<8)|(1<<16)|(2<<18)|(16<<20)
def make_trial(index):
    rng=np.random.default_rng(args.seed_base+index)
    alice=rng.integers(0,2,2765,dtype=np.int64);bob=alice^(rng.random(2765)<args.qber).astype(np.int64)
    q=float((alice!=bob).mean())
    res=ev.run_block({'alice':alice,'bob':bob,'q_block':q},base,args.seed_base+10000000+index,pos_d=positions)
    sym=res['sym'];sbits=res['syn'].reshape(-1)
    ch=[sum(int(sym[t*16+k])<<(2*k) for k in range(16)) for t in range(192)]
    syn=[sum(int(sbits[t*32+k])<<k for k in range(32)) for t in range(len(sbits)//32)]
    expected=[(int(t['conv'])<<31)|(t['pp']<<28)|(t['usc']<<16)|t['iters'] for t in res['trace']]
    key=[sum(int(res['hard'][w*64+i])<<i for i in range(64)) for w in range(48)]
    payload=encode(cfg,44,0,expected,[t['nrev'] for t in res['trace']],res['errcnt'],ch,syn,res['revs'],key)
    outcome='SUCCESS' if res['success'] else 'WRONG_CODEWORD' if res['undetected'] else 'DISCARD'
    row={'trial_id':index,'seed':args.seed_base+index,'errors_in':int((alice!=bob).sum()),'qber_actual':q,
         'outcome':outcome,'attempts':res['attempts'],'revealed':res['revealed'],'residual_errors':res['resid'],
         'packet_sha256':hashlib.sha256(payload).hexdigest(),'hardware_match':False}
    return row,payload
start=len(result['records']);assert start%4==0 and start<=args.trials
sessionfolder=folder/'sessions'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
try:
    with UARTSession(sessionfolder,args.port) as session:
        result['attempt_sessions'].append(str(sessionfolder));save()
        for offset in range(start,args.trials,4):
            batch=[make_trial(i) for i in range(offset,offset+4)]
            for cache,(row,payload) in enumerate(batch):
                values=struct.unpack('<'+'I'*(len(payload)//4),payload)
                session.command([70,cache,len(values),*values],r'QKD_BENCH_VECTOR seq={seq} index='+str(cache))
            _,answer=session.command([71,4,4,0],r'QKD_BENCH_PASS seq={seq} contexts=(\d+) jobs=(\d+) corrected=(\d+) discarded=(\d+) attempts=(\d+) rtt_us=(\d+) elapsed_us=(\d+) busy_cycles=(\d+)')
            k,n,conv,discarded,attempts,rtt,elapsed,busy=map(int,answer.groups())
            expected_conv=sum(row['outcome']!='DISCARD' for row,_ in batch)
            assert [k,n,conv,discarded,attempts,rtt]==[4,4,expected_conv,4-expected_conv,sum(row['attempts'] for row,_ in batch),0]
            for row,_ in batch:
                row['hardware_match']=True;row['batch_elapsed_us']=elapsed
                result['records'].append(row)
            with (folder/'verified_batches.jsonl').open('a',encoding='utf-8') as journal:
                journal.write(json.dumps([row for row,_ in batch])+'\n');journal.flush()
            save()
            if len(result['records'])%64==0:
                counts=collections.Counter(row['outcome'] for row in result['records'])
                print('FER_PROGRESS',len(result['records']),'/',args.trials,dict(counts),flush=True)
            if args.max_batches and (offset-start)//4+1>=args.max_batches:break
        result['complete']=len(result['records'])==args.trials
except BaseException as exc:
    result['error']=repr(exc);raise
finally:save();print('FER_EVIDENCE',folder,flush=True)
if not result['complete']:
    print('FER_PARTIAL_SAVED',len(result['records']),'/',args.trials,flush=True);raise SystemExit(0)
rows=result['records'];counts=collections.Counter(row['outcome'] for row in rows)
events=counts['DISCARD']+counts['WRONG_CODEWORD'];n=len(rows)
summary={'trials':n,'discard':counts['DISCARD'],'wrong_codeword_ground_truth':counts['WRONG_CODEWORD'],
         'success':counts['SUCCESS'],'FER':events/n,'FER_Wilson_two_sided_95':wilson_interval(events,n),
         'zero_failure_exact_one_sided_95_upper':zero_failures_upper(n) if events==0 else None,
         'hardware_errors_in_completed_batches':0,'tag_rejections':'NOT_TESTED','scope':'synthetic IID BSC; one code/QBER stratum'}
summary['previous_session_errors']=result.get('previous_session_errors',[])
result['summary']=summary;save()
out=ROOT/'reports'/('zc702_fer_'+result['started_utc']);out.mkdir(parents=True,exist_ok=True)
with (out/'trials.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
text=['# FER thành phần IR trên ZC702','',f"QBER BSC={args.qber:g}, code={args.code}, NMS+GS, {n} trial độc lập theo seed. PL 50 MHz.",'',
      f"SUCCESS={counts['SUCCESS']}, DISCARD={counts['DISCARD']}, WRONG_CODEWORD={counts['WRONG_CODEWORD']}. FER={events/n:.8g}.",
      f"Khoảng Wilson hai phía 95%: {summary['FER_Wilson_two_sided_95']}.",'',
      'Mỗi vector được đánh giá trên board một lần, kiểm tra toàn bộ trạng thái và KEY theo golden. '
      'Không dùng vòng lặp một vector làm mẫu độc lập. Đây là FER của lõi IR với ground truth biết trước; '
      'không chạy tag/PA trong phép đo này và không gọi wrong codeword là lỗi đã bị tag bắt. '
      'Các lỗi tool/UART/hardware làm dừng và lưu run incomplete; không đưa batch chưa xác minh vào số liệu PASS.','',
      'Chưa thể khẳng định FER≈1e-3 nếu số mẫu/CI không đủ; không ép outcome theo mục tiêu bài báo.','']
(out/'REPORT.md').write_text('\n'.join(text),encoding='utf-8')
subprocess.run([sys.executable,str(ROOT/'syn/zc702/verify_experiment_run.py'),'fer',str(folder)],check=True,cwd=ROOT)
latest={'complete':True,'trials':n,'qber':args.qber,'code':args.code,'scope':'one selected synthetic BSC stratum; other strata not completed',
        'report':str(out/'REPORT.md'),'raw_result':str(folder/'result.json'),
        'verified_evidence':str(out/'verified_evidence.json')}
(ROOT/'reports/FER_LATEST_COMPLETE.json').write_text(json.dumps(latest,indent=2)+'\n')
print('FER_CAMPAIGN_PASS',n,summary,flush=True)
