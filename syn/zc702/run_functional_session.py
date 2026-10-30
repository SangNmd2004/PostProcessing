"""Online ARM controller + FPGA IR/verification/PA, with Alice simulated on PC.

CSV data and public PE sample are test inputs. Output hashes are functional
evidence, not finite-key secret output. Backlogs are scripted stimuli, not traffic.
"""
from pathlib import Path
from datetime import datetime,timezone
from zipfile import ZipFile
import argparse,csv,hashlib,json,re,secrets,struct,subprocess,sys,time,zlib
import numpy as np
import serial
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/zc702'
sys.path.insert(0,str(ROOT/'model'))
import ir_model as m
import dyn_ir as d
import puncture as pu
import pa_model as pa
import eval_csv as ev
from pa_accum import PAAccumulator
MAGIC=0x51465532

def packed(values):return struct.pack('<'+'I'*len(values),*map(int,values))
def words(bits,width):return pa.bits_to_words(bits,width)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',default='COM3')
    ap.add_argument('--campaign',type=Path,default=OUT/'uart_csv_nms_gs/campaign.json')
    ap.add_argument('--limit',type=int)
    ap.add_argument('--accumulator-only',action='store_true',help='Only standalone synthetic decoy accumulator tests')
    ap.add_argument('--multicontext-only',action='store_true',help='Four resident contexts plus accumulator controls')
    args=ap.parse_args()
    subprocess.run([sys.executable,str(ROOT/'syn/zc702/verify_bundle.py')],check=True)
    manifest=json.loads((OUT/'uart_firmware/manifest.json').read_text())
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    campaign=json.loads(args.campaign.read_text())
    csv_path=Path(campaign['csv'])
    assert hashlib.sha256(csv_path.read_bytes()).hexdigest()==campaign['csv_sha256']
    original={int(r['test_id']):r for r in csv.DictReader(csv_path.open(encoding='utf-8-sig',newline=''))}
    blocks=[]
    for group in campaign['coverage']:
        a=''.join(original[i]['key_alice'] for i in group['test_ids'])
        b=''.join(original[i]['key_bob'] for i in group['test_ids'])
        for idx,start in enumerate(group['block_starts']):
            aa=np.frombuffer(a[start:start+d.NKEY].encode(),dtype=np.uint8).astype(np.int64)-48
            bb=np.frombuffer(b[start:start+d.NKEY].encode(),dtype=np.uint8).astype(np.int64)-48
            blocks.append((group['group'],idx,aa,bb))
    all_blocks=blocks[:]
    if args.limit:blocks=blocks[:args.limit]
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder=OUT/'functional_runs'/stamp;folder.mkdir(parents=True,exist_ok=False)
    result={'complete':False,'hardware_capture':True,'board':'ZC702','context':0,'port':args.port,
            'started_utc':stamp,'csv_sha256':campaign['csv_sha256'],'firmware_manifest':manifest,
            'seed_source':'PC_OS_CSPRNG_public_test_seed','alice':'PC_simulation',
            'backlog_source':'scripted_hysteresis_stimulus','records':[],'control_checks':[]}
    (folder/'firmware_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    seq=0;process=None
    def persist():
        (folder/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    try:
        with serial.Serial(args.port,115200,timeout=0.1,write_timeout=5) as uart, \
             (folder/'uart.log').open('wb') as log,(folder/'xsct.log').open('wb') as xlog:
            pending=bytearray()
            def expect(pattern,timeout=45):
                deadline=time.monotonic()+timeout
                while time.monotonic()<deadline:
                    if b'\n' in pending:
                        raw,_,tail=pending.partition(b'\n');pending[:]=tail
                        text=raw.decode(errors='replace').strip()
                        if re.search(r'FATAL|TIMEOUT|DMA_ERROR|MISMATCH',text):raise RuntimeError(text)
                        found=re.fullmatch(pattern,text)
                        if found:return found
                        if text.startswith(('QKD_UART_','QKD_FUNC_')):raise RuntimeError('unexpected: '+text)
                        continue
                    chunk=uart.read(max(1,uart.in_waiting))
                    if chunk:pending.extend(chunk);log.write(chunk);log.flush()
                    if process is not None and process.poll() not in (None,0):raise RuntimeError('JTAG loader failure')
                raise TimeoutError(pattern)
            uart.reset_input_buffer()
            with ZipFile(OUT/'qkd_zc702.xsa') as z:(OUT/'ps7_init.tcl').write_bytes(z.read('ps7_init.tcl'))
            process=subprocess.Popen(['D:/Xilinx/Vitis/2020.2/bin/xsct.bat',str(ROOT/'syn/zc702/program_smoke.tcl'),'uart'],
                                     cwd=ROOT,stdout=xlog,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            expect(r'QKD_UART_READY version=1 max_words=4096',120)
            process.wait(timeout=30);xlog.flush()
            assert process.returncode==0
            xt=(folder/'xsct.log').read_text(errors='replace')
            assert 'ZC702_PROGRAM_MMIO_PASS' in xt and 'ZC702_SMOKE_CPU_STARTED' in xt
            def command(values,pattern):
                nonlocal seq
                current=seq;seq+=1;payload=packed(values)
                uart.write(packed([MAGIC,current,len(values),zlib.crc32(payload)]))
                expect(fr'QKD_UART_ACCEPT seq={current}')
                for offset in range(0,len(payload),128):
                    chunk=payload[offset:offset+128];uart.write(chunk)
                    expect(fr'QKD_UART_ACK seq={current} bytes={offset+len(chunk)}')
                return current,expect(pattern.replace('{seq}',str(current))) if pattern else None
            codes=m.load_codes(128);m.CN_MODE='nms75'
            for policy in ([] if args.accumulator_only or args.multicontext_only else ['efficiency','throughput','adaptive']):
                command([0],r'QKD_FUNC_RESET seq={seq}')
                ctrl=d.Controller(mode='basic',f_target=1.3,f_safe=1.7,pe_z=1.5,abort_basic=True)
                profile=0
                for block_no,(group,idx,alice,bob) in enumerate(blocks):
                    backlog=0 if policy=='efficiency' else 4 if policy=='throughput' else [0,4,2,1,4,2,0][block_no%7]
                    if backlog>=4:profile=1
                    elif backlog<=1:profile=0
                    ctrl.mode='dynamic' if profile else 'basic'
                    rng=np.random.default_rng(9000+block_no)
                    sample=rng.choice(d.NKEY,256,replace=False)
                    q=float(np.float32((alice[sample]!=bob[sample]).mean()))
                    qword=struct.unpack('<I',struct.pack('<f',q))[0]
                    _,answer=command([1,backlog,qword,256],r'QKD_FUNC_PLAN seq={seq} accept=(\d+) profile=(\d+) code=(\d+) r0=(\d+)')
                    accept,prof,code,r0=map(int,answer.groups())
                    ref_code,ref_r0=ctrl.plan(q,256)
                    assert accept==int(ref_code is not None) and prof==profile
                    record={'policy':policy,'group':group,'block':idx,'backlog':backlog,'profile':profile,
                            'q_pe_pct':100*q,'pe_sample_bits':256,'qber_pct':100*float((alice!=bob).mean()),
                            'attempts':[],'ir_model_match':True,'pa_pass':False,'verification_rejected':False}
                    if not accept:
                        record['outcome']='EARLY_DISCARD';result['records'].append(record);persist()
                        print('FUNCTIONAL',policy,group,idx,'EARLY_DISCARD',flush=True);continue
                    assert code==m.CODE_ORDER.index(ref_code) and r0==ref_r0,(answer.group(0),ref_code,ref_r0)
                    record.update(code=ref_code,r0=r0)
                    positions=pu.order(ref_code,codes[ref_code],128,d.D)
                    block=d.prepare_block(alice,bob,8000+block_no,positions)
                    key_pos=block['key_pos'];v=block['v']
                    types=np.zeros((1,d.N),dtype=np.int64);types[0,positions]=m.T_PUNCT
                    bits=block['ch_bit'].reshape(1,d.N).copy()
                    syn=m.syndrome(codes[ref_code],v.reshape(1,m.NCOL,128),128)
                    sym=np.where(types[0]==m.T_PUNCT,2,bits[0])
                    ch=[sum(int(sym[w*16+k])<<(2*k) for k in range(16)) for w in range(192)]
                    synwords=words(syn.reshape(-1),32)
                    def reveal_values(first,count):return [int(p)|(int(v[p])<<16) for p in positions[first:first+count]]
                    cfg=code|(8<<2)|(50<<8)|(1<<16)|(2<<18)|(16<<20)
                    command([10,cfg,44,len(synwords),r0,*ch,*synwords,*reveal_values(0,r0)],r'QKD_FUNC_LOADED seq={seq}')
                    types[0,positions[:r0]]=m.T_SHORT;bits[0,positions[:r0]]=v[positions[:r0]]
                    revealed=r0;attempts=0;correct=False;errcnt=0
                    while True:
                        attempts+=1;assert attempts<=32
                        model=m.decode_attempt(types,bits,syn,codes[ref_code],128,50,8,1,2,16,12)
                        types=model['ch_type'];converged=bool(model['conv'][0])
                        _,irq_arm=command([50],r'QKD_FUNC_IRQ_ARMED seq={seq} id=(\d+)')
                        assert int(irq_arm.group(1))==61
                        _,actual=command([11],r'QKD_FUNC_ATTEMPT seq={seq} status=([0-9a-fA-F]+) iters=([0-9a-fA-F]+) errcnt=(\d+) cycles=(\d+) ticks=(\d+)')
                        st,it=map(lambda x:int(x,16),actual.groups()[:2]);errcnt,cycles,ticks=map(int,actual.groups()[2:])
                        wanted=(1 if converged else 2)|((int(model['decodes'][0])-1)<<4)|(int(model['n_usc'][0])<<16)
                        assert st&0x0fff0033==wanted and it&0xfff==int(model['iters'][0]) and (it>>16)&255==attempts
                        _,irq_reply=command([51],r'QKD_FUNC_IRQ_RESULT seq={seq} count=(\d+) status=([0-9a-fA-F]+)')
                        irq_count=int(irq_reply.group(1));irq_status=int(irq_reply.group(2),16)
                        assert irq_count==1 and irq_status&3==(1 if converged else 2)
                        record['attempts'].append({'status':st,'iters':it,'errcnt':errcnt if converged else None,
                                                   'irq_count':irq_count,'irq_status':irq_status,
                                                   'decoder_cycles':cycles,'elapsed_timer_ticks':ticks})
                        if converged:
                            keyseq,_=command([14],None)
                            got=[]
                            for k in range(48):
                                reply=expect(fr'QKD_FUNC_KEY seq={keyseq} word={k} value=([0-9a-fA-F]{{16}})')
                                got.append(int(reply.group(1),16))
                            hard=model['hard'][0];assert got==words(hard,64)
                            residual=int((hard[key_pos]!=alice).sum());correct=residual==0
                            assert errcnt==int((hard[key_pos]!=bob).sum())
                            record.update(residual_errors=residual,errcnt=errcnt,key_sha256=hashlib.sha256(struct.pack('<48Q',*got)).hexdigest())
                            # Two independently sampled public seeds; no hardware TRNG claim.
                            seed_v=np.frombuffer(secrets.token_bytes(480),dtype=np.uint8)
                            seed_p=np.frombuffer(secrets.token_bytes(480),dtype=np.uint8)
                            vb=np.unpackbits(seed_v,bitorder='little');pb=np.unpackbits(seed_p,bitorder='little')
                            padded=np.pad(alice,(0,2784-len(alice))).astype(np.uint8)
                            tag=words(pa.pa_hash(padded,vb),64)[0]
                            y=words(pa.pa_hash(padded,pb),64)
                            force_bad_tag=policy=='efficiency' and block_no==0
                            if force_bad_tag:tag^=1
                            seedv=list(struct.unpack('<120I',seed_v.tobytes()));seedp=list(struct.unpack('<120I',seed_p.tobytes()))
                            yw=[piece for value in y for piece in [value&0xffffffff,value>>32]]
                            pseq,_=command([20,code,*map(int,positions),*seedv,tag&0xffffffff,tag>>32,*seedp,*yw],None)
                            if force_bad_tag or not correct:
                                expect(fr'QKD_FUNC_TAG_REJECT seq={pseq} pa_emitted=0')
                                record['verification_rejected']=True
                                record['negative_tag_test']=force_bad_tag
                            else:
                                for k,value in enumerate(y):
                                    response=expect(fr'QKD_FUNC_PA seq={pseq} word={k} value=([0-9a-fA-F]{{16}})')
                                    assert int(response.group(1),16)==value
                                expect(fr'QKD_FUNC_PIPE_PASS seq={pseq} input_bits=2765 output_bits=1024')
                                record['pa_pass']=True
                            record['outcome']='SUCCESS' if correct else 'UNDETECTED_CODEWORD'
                            record['pa_sha256']=hashlib.sha256(struct.pack('<16Q',*y)).hexdigest() if record['pa_pass'] else None
                            break
                        if revealed==d.D:
                            command([13],r'QKD_FUNC_DISCARD seq={seq}');record['outcome']='DISCARD';break
                        _,reply=command([2,int(model['n_usc'][0]),d.D-revealed],r'QKD_FUNC_REVEAL_PLAN seq={seq} count=(\d+)')
                        count=int(reply.group(1));assert count==ctrl.next_reveal(int(model['n_usc'][0]),d.D-revealed) and count>0
                        command([12,count,*reveal_values(revealed,count)],r'QKD_FUNC_REVEALED seq={seq} count='+str(count))
                        nxt=positions[revealed:revealed+count];types[0,nxt]=m.T_SHORT;bits[0,nxt]=v[nxt];revealed+=count
                    success=correct and record['pa_pass']
                    ctrl.update(success,errcnt if success else 0,attempts)
                    _,state=command([3,int(success),errcnt if success else 0,attempts],r'QKD_FUNC_UPDATE seq={seq} f_scaled=(\d+)')
                    assert abs(int(state.group(1))-ctrl.f_adj*1000000)<3
                    record.update(attempt_count=attempts,revealed_bits=revealed,f_adj_after=ctrl.f_adj,
                                  leak_ec_bits=m.CODE_MB[ref_code]*128-d.D+revealed+64)
                    result['records'].append(record);persist()
                    print('FUNCTIONAL',policy,group,idx,ref_code,record['outcome'],'PA',record['pa_pass'],flush=True)
            # Standalone control-plane checks with explicitly synthetic decoy counts.
            simulation=ROOT/'data/sessions/session_weak.npz'
            data=np.load(simulation)
            nk=[int(((data['k']==j)&(data['basis']==0)).sum()) for j in range(3)]
            nt=[int(((data['k']==j)&(data['basis']==1)).sum()) for j in range(3)]
            mt=[int(((data['k']==j)&(data['basis']==1)&(data['a']!=data['b'])).sum()) for j in range(3)]
            result['synthetic_decoy_source']={'file':str(simulation),'sha256':hashlib.sha256(simulation.read_bytes()).hexdigest(),
                                            'note':'Independent metadata tests, not measured decoy counts from the CSV IR stream.'}
            reference=PAAccumulator([.6,.2,0],[.75,.125,.125])
            def acc_reset():
                command([30],r'QKD_FUNC_ACC_RESET seq={seq}');reference.reset()
            def acc_add(errors,leak,at):
                command([31,*nk,*nt,*errors,leak,at],r'QKD_FUNC_ACC_ADDED seq={seq}')
                reference.add(nk,nt,errors,leak,at)
            def acc_check(label,at):
                _,reply=command([32,at],r'QKD_FUNC_ACC_DECISION seq={seq} action=(\d+) ell=(\d+) split=(\d+) emit_n=(\d+)')
                action,ell,split,emit_n=map(int,reply.groups())
                expected,expected_ell,_,reason=reference.decide(at)
                assert action=={'wait':0,'emit':1,'abort':2}[expected]
                assert ell==(expected_ell//64*64 if expected=='emit' else 0) and bool(split)==reference._split
                result['control_checks'].append({'case':label,'action':expected,'ell_rounded':ell,'split':bool(split),
                                                 'reason':reason,'hardware_match':True,'synthetic_metadata':True})
                persist();print('ACCUMULATOR_MATCH',label,expected,ell,flush=True)
            leak=int(sum(nk)*.15)
            acc_reset();acc_check('empty_wait',0)
            acc_add(mt,leak,0);acc_check('finite_positive_wait_for_growth',0)
            acc_check('age_limit_emit',4000)
            command([33],r'QKD_FUNC_ACC_EMITTED seq={seq}');reference.emitted();acc_check('reset_after_emit',4000)
            bad=[int(v*.2) for v in nt]
            acc_reset();acc_add(bad,int(sum(nk)*.5),0);acc_check('asymptotic_abort',0)
            acc_reset();acc_add(mt,leak,0);acc_check('good_snapshot',0)
            acc_add(bad,int(sum(nk)*.5),1);acc_check('channel_degradation_split_emit',1)
            command([33],r'QKD_FUNC_ACC_EMITTED seq={seq}');reference.emitted();acc_check('bad_tail_abort_after_split',1)
            if not args.accumulator_only:
                # Load four independent banks in HOLD, then queue all before collecting.
                command([40],r'QKD_FUNC_MC_RESET seq={seq}')
                selected=[next(b for b in all_blocks if b[0]==group) for group in ['WEAK','MILD','MODERATE','STRONG']]
                contexts=[]
                for ctx,((group,idx,alice,bob),name) in enumerate(zip(selected,['r56','r23','r12','r12'])):
                    positions=pu.order(name,codes[name],128,d.D)
                    reference_result=ev.run_block({'alice':alice,'bob':bob,'q_block':float((alice!=bob).mean())},
                                                  codes[name],12000+ctx,pos_d=positions)
                    sym=reference_result['sym']
                    ch=[sum(int(sym[w*16+k])<<(2*k) for k in range(16)) for w in range(192)]
                    synwords=words(reference_result['syn'].reshape(-1),32)
                    code=m.CODE_ORDER.index(name);cfg=code|(8<<2)|(50<<8)|(1<<16)|(2<<18)|(16<<20)
                    command([41,ctx,cfg,44,len(synwords),0,*ch,*synwords],r'QKD_FUNC_MC_LOADED seq={seq} ctx='+str(ctx))
                    contexts.append({'ctx':ctx,'group':group,'code':name,'model':reference_result,'attempt':0,'cursor':0,'done':False})
                for ctx in range(4):command([42,ctx],r'QKD_FUNC_MC_QUEUED seq={seq} ctx='+str(ctx))
                deadline=time.monotonic()+90
                while not all(c['done'] for c in contexts):
                    assert time.monotonic()<deadline,'multicontext deadline'
                    current,reply=command([43],r'QKD_FUNC_MC_STATUS seq={seq} summary=([0-9a-fA-F]+) rx=(\d+) owner=(\d+)')
                    summary=int(reply.group(1),16);rx=int(reply.group(2));owner=int(reply.group(3));states=[]
                    for ctx in range(4):
                        response=expect(fr'QKD_FUNC_MC_CTX seq={current} ctx={ctx} a=([0-9a-fA-F]+) b=([0-9a-fA-F]+) cycles=(\d+)')
                        states.append((int(response.group(1),16),int(response.group(2),16),int(response.group(3))))
                    if rx:
                        received=[]
                        for k in range(48):
                            response=expect(fr'QKD_FUNC_MC_KEY seq={current} ctx={owner} word={k} value=([0-9a-fA-F]{{16}})')
                            received.append(int(response.group(1),16))
                        c=contexts[owner];assert not c['done']
                        ref=c['model'];trace=ref['trace'][c['attempt']]
                        a,b,cycles=states[owner]
                        assert trace['conv'] and received==words(ref['hard'],64) and b&0xfff==ref['errcnt']
                        assert a&0xfff==trace['iters'] and a>>24==c['attempt']+1
                        c['done']=True
                        result.setdefault('multicontext_checks',[]).append({'ctx':owner,'group':c['group'],'code':c['code'],
                            'outcome':'SUCCESS','hardware_match':True,'attempts':c['attempt']+1,
                            'key_sha256':hashlib.sha256(struct.pack('<48Q',*received)).hexdigest(),'decoder_cycles':cycles})
                    for ctx,c in enumerate(contexts):
                        if not (summary&(1<<(24+ctx))) or c['done']:continue
                        ref=c['model'];trace=ref['trace'][c['attempt']];a,b,cycles=states[ctx]
                        assert not trace['conv'] and a&0xfff==trace['iters'] and (a>>12)&0xfff==trace['usc']
                        assert a>>24==c['attempt']+1 and (b>>24)&3==trace['pp']
                        count=trace['nrev']
                        if count:
                            reveals=ref['revs'][c['cursor']:c['cursor']+count];c['cursor']+=count
                            command([44,ctx,count,*reveals],r'QKD_FUNC_MC_REVEALED seq={seq} ctx='+str(ctx))
                            c['attempt']+=1
                            command([42,ctx],r'QKD_FUNC_MC_QUEUED seq={seq} ctx='+str(ctx))
                        else:
                            command([45,ctx],r'QKD_FUNC_MC_DISCARD seq={seq} ctx='+str(ctx));c['done']=True
                            result.setdefault('multicontext_checks',[]).append({'ctx':ctx,'group':c['group'],'code':c['code'],
                                'outcome':'DISCARD','hardware_match':True,'attempts':c['attempt']+1,'decoder_cycles':cycles})
                    persist()
                command([46],r'QKD_FUNC_MC_DONE seq={seq}')
                result['multicontext_note']='Four loaded HOLD banks, all queued; unique sticky SUCCESS binds one S2MM frame before rearm. No TUSER assumed in DDR. No throughput claim.'
            result['complete']=True
    except Exception as exc:
        result['error']=str(exc);raise
    finally:
        if process is not None and process.poll() is None:process.terminate()
        persist();print('FUNCTIONAL_EVIDENCE',folder,flush=True)
    print('FUNCTIONAL_SESSION_PASS',len(result['records']),flush=True)

if __name__=='__main__':main()
