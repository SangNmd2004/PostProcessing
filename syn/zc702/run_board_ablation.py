"""Paired four-stage board ablation, with a journal and one committed evaluation per input/configuration."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,random,struct,subprocess,sys,time
import numpy as np
from uart_session import ROOT,UARTSession
from generate_uart_campaign import encode
sys.path.insert(0,str(ROOT/'model'))
import ir_model as m
import eval_csv as ev
import puncture as pu

CONFIGS=[dict(name='OMS_random',cn='oms',positions='random',ET=0,PP=[0,2,16]),
         dict(name='OMS_GS',cn='oms',positions='gs',ET=0,PP=[0,2,16]),
         dict(name='NMS_GS',cn='nms75',positions='gs',ET=0,PP=[0,2,16]),
         dict(name='NMS_GS_ET_PP',cn='nms75',positions='gs',ET=12,PP=[1,2,16])]
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--trials',type=int,default=1000);ap.add_argument('--qber',type=float,default=.03)
ap.add_argument('--code',choices=m.CODE_ORDER,default='r23');ap.add_argument('--seed-base',type=int,default=1800000)
ap.add_argument('--port',default='COM3');ap.add_argument('--resume',type=Path);ap.add_argument('--max-batches',type=int)
args=ap.parse_args()
if args.trials<4 or args.trials%4 or not 0<args.qber<.12:ap.error('trials multiple of four; QBER in (0,.12)')
sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
         [Path(__file__),ROOT/'model/ir_model.py',ROOT/'model/eval_csv.py',ROOT/'model/codes.json',ROOT/'model/punct.json']}
specs=[]
for offset in range(0,args.trials,4):
    order=list(range(4));random.Random(args.seed_base+offset).shuffle(order)
    specs.extend(dict(offset=offset,configuration=i) for i in order)
if args.resume:
    folder=args.resume.resolve();result=json.loads((folder/'result.json').read_text())
    config=result['config'];assert config['trials']==args.trials and config['qber']==args.qber and config['code']==args.code and config['seed_base']==args.seed_base
    assert config['configurations']==CONFIGS and config['sources']==sources
else:
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder=ROOT/'build/zc702/board_ablation_runs'/stamp;folder.mkdir(parents=True)
    config=dict(trials=args.trials,qber=args.qber,code=args.code,seed_base=args.seed_base,configurations=CONFIGS,
                n=3072,d=307,lq=8,iterations=50,r0=0,reveal_step=77,contexts=1,jobs_per_batch=4,rtt_us=0,
                scope='paired synthetic BSC; decoder component only; no verification tag or PA',sources=sources,
                randomized_batch_order=specs)
    result={'complete':False,'hardware_capture':True,'started_utc':stamp,'config':config,'batches':[],'sessions':[]}
    (folder/'frozen_config.json').write_text(json.dumps(config,indent=2)+'\n')
    (folder/'runner_at_start.py').write_bytes(Path(__file__).read_bytes())
if result.get('error'):result.setdefault('previous_errors',[]).append(result.pop('error'))
journal=folder/'verified_batches.jsonl'
if journal.exists():
    recovered={b['batch_index']:b for b in result['batches']}
    for line in journal.read_text().splitlines():
        batch=json.loads(line)
        if batch['batch_index'] in recovered:assert recovered[batch['batch_index']]==batch
        recovered[batch['batch_index']]=batch
    assert set(recovered)==set(range(len(recovered)))
    result['batches']=[recovered[i] for i in range(len(recovered))]
result['complete']=False
def save():
    temporary=folder/'result.json.tmp';temporary.write_text(json.dumps(result,indent=2)+'\n')
    for attempt in range(4):
        try:temporary.replace(folder/'result.json');return
        except PermissionError:
            if attempt==3:raise
            time.sleep(.05)
base=m.load_codes(128)[args.code];gs=pu.order(args.code,base,128,307)
def trial(index,settings):
    rng=np.random.default_rng(args.seed_base+index)
    alice=rng.integers(0,2,2765,dtype=np.int64);bob=alice^(rng.random(2765)<args.qber).astype(np.int64)
    actual=float((alice!=bob).mean());input_hash=hashlib.sha256(alice.astype(np.uint8).tobytes()+bob.astype(np.uint8).tobytes()).hexdigest()
    positions=gs if settings['positions']=='gs' else np.random.default_rng(args.seed_base+20000000+index).choice(3072,307,replace=False)
    m.CN_MODE=settings['cn'];ev.ET=settings['ET'];ev.PP=tuple(settings['PP'])
    res=ev.run_block({'alice':alice,'bob':bob,'q_block':actual},base,args.seed_base+10000000+index,pos_d=positions)
    sym=res['sym'];sb=res['syn'].reshape(-1)
    ch=[sum(int(sym[w*16+k])<<(2*k) for k in range(16)) for w in range(192)]
    syn=[sum(int(sb[w*32+k])<<k for k in range(32)) for w in range(len(sb)//32)]
    expected=[int(t['conv'])<<31|t['pp']<<28|t['usc']<<16|t['iters'] for t in res['trace']]
    key=[sum(int(res['hard'][w*64+k])<<k for k in range(64)) for w in range(48)]
    pp=settings['PP'];cfg=m.CODE_ORDER.index(args.code)|(8<<2)|(50<<8)|(pp[0]<<16)|(pp[1]<<18)|(pp[2]<<20)
    cfg2=settings['ET']|(32 if settings['cn']=='nms75' else 0)
    payload=encode(cfg,cfg2,0,expected,[t['nrev'] for t in res['trace']],res['errcnt'],ch,syn,res['revs'],key)
    leak=m.CODE_MB[args.code]*128-307+res['revealed'];assert res['leak']==leak
    outcome='SUCCESS' if res['success'] else 'WRONG_CODEWORD' if res['undetected'] else 'DISCARD'
    row=dict(trial=index,seed=args.seed_base+index,configuration=settings['name'],input_sha256=input_hash,
             actual_qber=actual,errors_in=int((alice!=bob).sum()),outcome=outcome,attempts=res['attempts'],
             revealed=res['revealed'],residual_errors=res['resid'],leak_ir=leak,
             f_ir=leak/(2765*m.h2(actual)) if res['success'] and actual else None,
             payload_sha256=hashlib.sha256(payload).hexdigest(),hardware_match=False)
    return row,payload
start=len(result['batches']);sessionfolder=folder/'sessions'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
try:
    with UARTSession(sessionfolder,args.port) as session:
        if result.get('firmware_manifest'):assert result['firmware_manifest']==session.manifest,'firmware changed: start a new cohort'
        result['firmware_manifest']=session.manifest;result['sessions'].append(str(sessionfolder.relative_to(ROOT)));save()
        for batch_index in range(start,len(specs)):
            spec=specs[batch_index];settings=CONFIGS[spec['configuration']]
            pairs=[trial(i,settings) for i in range(spec['offset'],spec['offset']+4)]
            loaded=[]
            for slot,(row,payload) in enumerate(pairs):
                values=struct.unpack('<'+'I'*(len(payload)//4),payload)
                seq,_=session.command([70,slot,len(values),*values],r'QKD_BENCH_VECTOR seq={seq} index='+str(slot));loaded.append(seq)
            seq,reply=session.command([71,1,4,0],r'QKD_BENCH_PASS seq={seq} contexts=(\d+) jobs=(\d+) corrected=(\d+) discarded=(\d+) attempts=(\d+) rtt_us=(\d+) elapsed_us=(\d+) busy_cycles=(\d+)')
            k,jobs,conv,discard,attempts,rtt,elapsed,busy=map(int,reply.groups())
            converged=sum(r['outcome']!='DISCARD' for r,_ in pairs)
            assert [k,jobs,conv,discard,attempts,rtt]==[1,4,converged,4-converged,sum(r['attempts'] for r,_ in pairs),0]
            for row,_ in pairs:row['hardware_match']=True
            batch=dict(batch_index=batch_index,offset=spec['offset'],configuration=settings['name'],session=str(sessionfolder.relative_to(ROOT)),
                       load_seqs=loaded,run_seq=seq,elapsed_us=elapsed,busy_cycles=busy,rows=[r for r,_ in pairs])
            with journal.open('a',encoding='utf-8') as f:f.write(json.dumps(batch)+'\n');f.flush()
            result['batches'].append(batch);save()
            if len(result['batches'])%4==0:print('BOARD_ABLATION_PROGRESS',len(result['batches']),'/',len(specs),'evaluations',len(result['batches'])*4,flush=True)
            if args.max_batches and batch_index-start+1>=args.max_batches:break
        result['complete']=len(result['batches'])==len(specs)
except BaseException as exc:result['error']=repr(exc);raise
finally:save();print('BOARD_ABLATION_EVIDENCE',folder,flush=True)
if result['complete']:
    subprocess.run([sys.executable,str(ROOT/'syn/zc702/report_board_ablation.py'),str(folder)],check=True)
    print('BOARD_ABLATION_PASS',args.trials,'paired inputs',len(result['batches'])*4,'physical evaluations',flush=True)
else:print('BOARD_ABLATION_PARTIAL_SAVED',len(result['batches']),flush=True)
