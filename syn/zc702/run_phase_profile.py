"""Measure actual UART/PS/PL phase spans on repeated public golden vectors, not FER trials."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,random,struct,sys,time
import numpy as np
from uart_session import ROOT,UARTSession
sys.path.insert(0,str(ROOT/'model'))
import ir_model as ir
import puncture as pu
import pa_model as pa

ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--port',default='COM3')
ap.add_argument('--repeats',type=int,default=3);ap.add_argument('--pilot',action='store_true')
args=ap.parse_args()
if not 1<=args.repeats<=10:ap.error('repeats must be in [1,10]')
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
folder=ROOT/'build/zc702/phase_profile_runs'/stamp;folder.mkdir(parents=True)
campaign_dir=ROOT/'build/zc702/uart_csv_nms_gs';campaign=json.loads((campaign_dir/'campaign.json').read_text())
chosen=[]
for name in ir.CODE_ORDER:
    candidates=[r for r in campaign['records'] if r['code']==name and r['model_outcome']=='SUCCESS']
    chosen.append(candidates[0] if name=='r56' else next((r for r in candidates if 1<r['attempts']<=5),candidates[0]))
fixtures=[];codes=ir.load_codes(128);rng=np.random.default_rng(2026102702)
for record in chosen:
    data=(campaign_dir/record['file']).read_bytes();assert hashlib.sha256(data).hexdigest()==record['sha256']
    v=list(struct.unpack('<'+'I'*(len(data)//4),data));cfg,cfg2,pre,att,ns,err,nrev=v[:7]
    expected=v[7:7+att];counts=v[7+att:7+2*att];at=7+2*att
    ch=v[at:at+192];at+=192;syn=v[at:at+ns];at+=ns;reveals=v[at:at+nrev];at+=nrev
    key=[v[i]|v[i+1]<<32 for i in range(at,len(v),2)]
    positions=list(map(int,pu.order(record['code'],codes[record['code']],128,307)))
    bits=np.unpackbits(np.frombuffer(struct.pack('<48Q',*key),dtype=np.uint8),bitorder='little')
    mask=np.ones(3072,dtype=bool);mask[positions]=False;x=np.pad(bits[mask],(0,19))
    seeds=[list(map(int,rng.integers(0,2**32,120,dtype=np.uint32))) for _ in range(2)]
    outputs=[]
    for seed in seeds:
        sb=np.unpackbits(np.frombuffer(struct.pack('<120I',*seed),dtype=np.uint8),bitorder='little')
        outputs.append(list(map(int,np.frombuffer(np.packbits(pa.pa_hash(x,sb),bitorder='little').tobytes(),dtype='<u8'))))
    tag=outputs[0][0];expected32=[w for word in outputs[1] for w in [word&0xffffffff,word>>32]]
    pipe=[20,cfg&3,*positions,*seeds[0],tag&0xffffffff,tag>>32,*seeds[1],*expected32]
    assert len(pipe)==583
    fixtures.append(dict(record=record,cfg=cfg,cfg2=cfg2,pre=pre,att=att,ns=ns,err=err,ch=ch,syn=syn,
                         expected=expected,counts=counts,reveals=reveals,key=key,pipe=pipe,pa=outputs[1]))
cases=[(i,delay,rep) for i in range(4) for delay in [0,1000,10000] for rep in range(args.repeats)]
if args.pilot:cases=[(0,0,0),(1,1000,0)]
random.Random(2026102702).shuffle(cases)
result={'complete':False,'hardware_capture':True,'started_utc':stamp,'clock_pl_mhz':50,
        'scope':'Repeated golden K=1 functional UART workload; not independent FER or secret-key throughput',
        'seed_source':'public_numpy_PCG64_fixture','records':[],
        'harness_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'syn/zc702/uart_session.py']}}
(folder/'experiment_config.json').write_text(json.dumps({'cases':cases,'fixtures':chosen,
    'repeats':args.repeats,'pilot':args.pilot,'order_seed':2026102702,
    'cpu_timer':'PMU CCNT divider disabled plus 64-bit global timer',
    'measurement_scope':'K1 repeated UART transactions; delay is host sleep before reveal, not network RTT'},indent=2)+'\n')
def save():(folder/'result.json').write_text(json.dumps(result,indent=2)+'\n')
try:
    with UARTSession(folder,args.port,profile_transport=True) as session:
        result['firmware_manifest']=session.manifest
        for fixture_id,delay,rep in cases:
            f=fixtures[fixture_id];row={'fixture':f['record'],'fixture_id':fixture_id,'delay_us':delay,'repeat':rep,
                                      'attempts':[],'snapshots':[],'injections':[],'command_seqs':[]}
            _,config=session.command([74,1],r'QKD_PROFILE_CONFIG seq={seq} enabled=1 timer_hz=(\d+) cpu_hz=(\d+) cal_ticks=(\d+) cal_cycles=(\d+) read_ticks=(\d+)')
            timer,cpu,ct,cc,overhead=map(int,config.groups());assert ct>0 and abs(cc/ct-cpu/timer)<.02
            row['timer']=dict(timer_hz=timer,cpu_hz=cpu,cal_ticks=ct,cal_cycles=cc,read_ticks=overhead)
            def command(values,pattern=None):
                seq,answer=session.command(values,pattern);row['command_seqs'].append(seq);return seq,answer
            host_start=time.perf_counter_ns()
            command([10,f['cfg'],f['cfg2'],f['ns'],f['pre'],*f['ch'],*f['syn'],*f['reveals'][:f['pre']]],r'QKD_FUNC_LOADED seq={seq}')
            cursor=f['pre']
            for attempt,(expected,count) in enumerate(zip(f['expected'],f['counts'])):
                _,reply=command([11],r'QKD_FUNC_ATTEMPT seq={seq} status=([0-9a-fA-F]+) iters=([0-9a-fA-F]+) errcnt=(\d+) cycles=(\d+) ticks=(\d+)')
                status,iters=int(reply.group(1),16),int(reply.group(2),16)
                wanted=(1 if expected>>31 else 2)|((expected>>28)&3)<<4|(expected&0x0fff0000)
                assert status&0x0fff0033==wanted and iters&0xfff==expected&0xfff and iters>>16&255==attempt+1
                row['attempts'].append({'status':status,'iters':iters,'cycles':int(reply.group(4)),'ticks':int(reply.group(5))})
                if expected>>31:
                    assert int(reply.group(3))==f['err'];break
                before=time.perf_counter_ns()
                if delay:time.sleep(delay/1e6)
                row['injections'].append({'planned_us':delay,'host_sleep_ns':time.perf_counter_ns()-before})
                command([12,count,*f['reveals'][cursor:cursor+count]],r'QKD_FUNC_REVEALED seq={seq} count='+str(count));cursor+=count
            seq,_=command([14]);key=[]
            for k in range(48):
                key.append(int(session.expect(fr'QKD_FUNC_KEY seq={seq} word={k} value=([0-9a-fA-F]{{16}})').group(1),16))
            session.complete_response(seq);assert key==f['key']
            seq,_=command(f['pipe']);output=[]
            for k in range(16):output.append(int(session.expect(fr'QKD_FUNC_PA seq={seq} word={k} value=([0-9a-fA-F]{{16}})').group(1),16))
            session.expect(fr'QKD_FUNC_PIPE_PASS seq={seq} input_bits=2765 output_bits=1024');session.complete_response(seq)
            assert output==f['pa'];row['key_and_pa_match']=True
            row['host_transaction_ns']=time.perf_counter_ns()-host_start
            _,meta=session.command([75,0xffffffff],r'QKD_PROFILE_META seq={seq} count=(\d+) dropped=(\d+) enabled=1 timer_hz=(\d+) cpu_hz=(\d+)')
            count,dropped,_,_=map(int,meta.groups());assert dropped==0 and count==len(row['command_seqs'])
            for index in range(count):
                seq,head=session.command([75,index],r'QKD_PROFILE_SNAPSHOT seq={seq} index=(\d+) command_seq=(\d+) op=(\d+) phases=(\d+) total_ticks=([0-9a-fA-F]{16})')
                i,command_seq,op,nphase=map(int,head.groups()[:4]);assert i==index and command_seq==row['command_seqs'][index]
                snap={'command_seq':command_seq,'op':op,'total_ticks':int(head.group(5),16),'phases':[]}
                for _ in range(nphase):
                    p=session.expect(fr'QKD_PROFILE_PHASE seq={seq} id=(\d+) count=(\d+) valid=(\d+) ticks=([0-9a-fA-F]{{16}}) cycles=([0-9a-fA-F]{{16}})')
                    phase_id,n,valid=map(int,p.groups()[:3]);ticks=int(p.group(4),16);cycles=int(p.group(5),16)
                    assert n==valid and ticks>0
                    if ticks>1000*n:assert abs(cycles-ticks*cpu/timer)<max(200*n,.03*ticks*cpu/timer)
                    snap['phases'].append(dict(id=phase_id,count=n,valid=valid,ticks=ticks,cycles=cycles))
                session.expect(fr'QKD_PROFILE_END seq={seq}');session.complete_response(seq)
                row['snapshots'].append(snap)
            result['records'].append(row);save()
            print('PHASE_PROFILE_BLOCK_PASS',len(result['records']),'code',f['record']['code'],'delay',delay,'attempts',f['att'],flush=True)
        session.command([74,0],r'QKD_PROFILE_CONFIG seq={seq} enabled=0 timer_hz=\d+ cpu_hz=\d+ cal_ticks=\d+ cal_cycles=\d+ read_ticks=\d+')
        result['complete']=True
except BaseException as exc:result['error']=repr(exc);raise
finally:save();print('PHASE_PROFILE_EVIDENCE',folder,flush=True)
print('PHASE_PROFILE_BOARD_PASS',len(result['records']),flush=True)
