"""Replay raw TX/UART, QAS2, frozen vector KEY, verification tags and emitted PA.

Runner checks/labels/expected PA are not used as acceptance evidence.
"""
from pathlib import Path
import argparse, csv, hashlib, json, re, struct, sys, zlib
import numpy as np
from qas2_bootstrap import Bootstrap
from qas2_pc import Session, SessionError
from checkpoint_io import write_checkpoint
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
import puncture, ir_model, pa_model
from pa_accum import PAAccumulator
from hankel_exact import hankel_hash

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def words(data,width=32):return list(struct.unpack('<'+('I' if width==32 else 'Q')*(len(data)//(width//8)),data))
def bits(data):return np.unpackbits(np.frombuffer(data,dtype=np.uint8),bitorder='little')
def packed(w,width=32):return struct.pack('<'+('I' if width==32 else 'Q')*len(w),*w)
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    run=args.run.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result=json.loads((run/'result.json').read_text());assert result['complete'] and result['baseline_restored'] and not result.get('error')
    manifest=result['build_manifest'];elf=ROOT/manifest['elf'];assert sha(elf)==manifest['elf_sha256']
    assert sha(elf.parent/'secure_main.c')==manifest['generated_sha256']
    for n,h in manifest['generated_files_sha256'].items():assert sha(elf.parent/n)==h,n
    for n,h in manifest['source_sha256'].items():
        candidate=elf.parent/'source_snapshot'/n
        assert sha(candidate if candidate.exists() else ROOT/n)==h,n
    for n,h in result['baseline_manifest']['files'].items():assert sha(ROOT/n)==h,n
    assert 'ZC702_PROGRAM_MMIO_PASS' in (run/'xsct.log').read_text(errors='replace')
    assert 'QKD_UART_READY version=1 max_words=4096' in (run/'baseline_restore/uart.log').read_text()
    assert 'ZC702_PROGRAM_MMIO_PASS' in (run/'baseline_restore/xsct.log').read_text(errors='replace')
    uart=(run/'uart.log').read_text();assert uart.startswith('SA_READY kat=PASS fixture=PUBLIC\n')
    assert all(l.startswith(('SA_READY ','QB ')) for l in uart.splitlines()),'application UART leak'
    rx=[]
    for l in uart.splitlines()[1:]:
        p=l.split();assert p[0]=='QB' and len(p) in [2,3];rx.append((int(p[1]),bytes.fromhex(p[2]) if len(p)==3 else b''))
    tx=[json.loads(l) for l in (run/'tx.jsonl').read_text().splitlines()];assert len(tx)==len(rx)==result['commands']
    # Derive the input, attempts and golden KEY from frozen .bin bytes, not runner fields.
    frozen=[];codes=ir_model.load_codes(128)
    for f in result['fixtures']:
        p=ROOT/'build/zc702/uart_csv_nms_gs'/f['record']['file'];assert sha(p)==f['record']['sha256']
        w=words(p.read_bytes());cfg,cfg2,pre,att,ns,err,nr=w[:7];cursor=7+2*att
        load=[10,cfg,cfg2,ns,pre,*w[cursor:cursor+192+ns]];cursor+=192+ns
        reveal=w[cursor:cursor+nr];cursor+=nr;load+=reveal[:pre]
        frozen.append(dict(load=load,expected=w[7:7+att],counts=w[7+att:7+2*att],reveals=reveal,pre=pre,
                           key=words(packed(w[cursor:]),64),code=f['code'],err=err))
    session=Session();boot=None
    used=0;limit=18446;dispatches=0;active=valid=0;next_id=0;binding=None;at=0
    current=None;attempt=0;revealed=0;actual=None;buffer=np.array([],dtype=np.uint8)
    ref=PAAccumulator([.6,.2,0],[.75,.125,.125]);pending=None;seed=[];output=None;seen=set();retired=aborted=tag_rejected=0
    rows=[];emissions=[];rejections={};resets=[];policy_rejected=0;append_count=0;tag_failures=0;wipe_count=0;digest_count=0
    def clear():
        nonlocal active,valid,next_id,binding,at,current,attempt,revealed,actual,buffer,ref,pending,seed,output,seen,retired,aborted,tag_rejected
        active=valid=next_id=at=attempt=revealed=retired=aborted=tag_rejected=0;binding=current=actual=pending=output=None
        buffer=np.array([],dtype=np.uint8);ref=PAAccumulator([.6,.2,0],[.75,.125,.125]);seed=[];seen=set()
    def metadata(m):return len(m)==11 and sum(m[1:4])==2765 and all(0<=k<=2765 for k in m[1:4]) and all(0<m[4+k]<=1000000000 and m[7+k]<=m[4+k] for k in range(3)) and m[10]>=at
    def load_ok(w):
        if len(w)<5 or active or valid or binding is not None or pending or output is not None:return False
        ns=[48,32,24,16][w[1]&3]
        return w[3]==ns and w[4]<=307 and len(w)==197+ns+w[4] and all(v&0xfffe0000==0 and v&65535<3072 for v in w[197+ns:])
    def allowed(w):
        if not w:return False
        op=w[0];n=len(w)
        if op==80:return n>=16 and w[1]==next_id and next_id<0xffffffff and metadata(w[1:12]) and load_ok([10,*w[12:]])
        if op==10:return load_ok(w)
        if op==11:return n==1 and active
        if op==12:return n>=2 and active and w[1]<=307 and n==2+w[1] and revealed+w[1]<=307 and all(v&0xfffe0000==0 and v&65535<3072 for v in w[2:])
        if op==14:return n==1 and valid
        if op==60:return n==134 and binding is not None and valid and not active and pending is None and output is None and len(buffer)<=16000000-2765 and w[1:12]==binding
        if op in [61,81,67,69,73,82]:return n==1
        if op==62:return n==2 and not active and not valid and binding is None and pending is None and output is None and w[1]>=at
        if op==63:return n>=5 and pending is not None and w[1]==pending['ns'] and w[2]==len(seed) and w[3]==n-4 and w[3]<=pending['ns']-len(seed)
        if op==64:return n==1 and pending is not None and len(seed)==pending['ns'] and output is None
        if op==65:return n==3 and output is not None and w[1]<=len(output)//64 and 0<w[2]<=128 and w[2]<=len(output)//64-w[1]
        if op==66:return n==1 and output is not None and pending is None
        if op==72:return n==2 and not active and used<=w[1]<=limit
        return False
    for index,(command,(rc,answer)) in enumerate(zip(tx,rx)):
        op=command['op'];data=bytes.fromhex(command['payload_hex'])
        row=dict(index=index,transport=op,application='',outcome='',verification_used=used,bits=len(buffer))
        if op=='I':
            boot=Bootstrap(1,bytes(range(1,33)),bytes(range(1,17)),bytes(range(17,33)),10000,nonce_source=lambda n,nonce=data:nonce)
            session.reset();clear();assert (rc,answer)==(0,b'');resets.append(dict(index=index,used=used,kind='I'))
        elif op=='H':
            clear();session.reset();assert rc==0 and answer==boot.server_hello(data)
        elif op=='F':
            assert rc==0 and answer==boot.server_finished(data);session=boot.take_provisioning().open_pc_session()
        elif op=='R':
            boot.abort();session.reset();clear();assert (rc,answer)==(0,b'');resets.append(dict(index=index,used=used,kind='R'))
        elif op=='G':assert (rc,answer)==(0,struct.pack('<5I',dispatches,used,active,valid,1))
        elif op=='D':
            try:opcode,payload=session.unwrap(data)
            except SessionError as exc:
                assert rc==int(exc.status) and not answer,(index,rc,exc)
                rejections[str(rc)]=rejections.get(str(rc),0)+1;row['outcome']='transport_reject';rows.append(row);continue
            assert rc==0 and answer==session.wrap(0x8100,answer[32:-8])
            text=answer[32:-8].decode('ascii');seq=session.rx_last
            w=words(payload) if len(payload)%4==0 else [];cmd=w[0] if w else -1;row['application']=cmd
            ok=opcode==0x100 and bool(payload) and len(payload)<=16384 and len(payload)%4==0 and allowed(w)
            if not ok:
                assert text==f'QKD_SECURE_REJECT seq={seq} reason=POLICY\r\n',(index,cmd,text)
                policy_rejected+=1;row['outcome']='policy_reject';rows.append(row);continue
            dispatches+=1;row['outcome']='dispatched'
            if cmd in [10,80]:
                if cmd==80:binding=w[1:12];at=binding[10];load=[10,*w[12:]]
                else:load=w
                found=[v for v in frozen if v['load']==load];assert len(found)==1;current=found[0]
                assert text==f'QKD_FUNC_LOADED seq={seq}\r\n';active=1;valid=0;actual=None;attempt=0;revealed=current['pre']
            elif cmd==11:
                m=re.fullmatch(fr'QKD_FUNC_ATTEMPT seq={seq} status=([0-9a-f]+) iters=([0-9a-f]+) errcnt=(\d+) cycles=(\d+) ticks=(\d+)\r\n',text);assert m
                status,iters,err=int(m[1],16),int(m[2],16),int(m[3]);expected=current['expected'][attempt];attempt+=1
                assert status&0x0fff0033==((1 if expected>>31 else 2)|((expected>>28)&3)<<4|(expected&0x0fff0000)) and iters&4095==expected&4095
                if status&1:active=0;valid=1;assert err==current['err']
            elif cmd==12:
                count=current['counts'][attempt-1];assert w==[12,count,*current['reveals'][revealed:revealed+count]];revealed+=count
                assert text==f'QKD_FUNC_REVEALED seq={seq} count={count}\r\n'
            elif cmd==14:
                values=re.findall(fr'QKD_FUNC_KEY seq={seq} word=(\d+) value=([0-9a-f]{{16}})\r\n',text)
                assert [int(i) for i,_ in values]==list(range(48));actual=[int(v,16) for _,v in values];assert actual==current['key']
            elif cmd==60:
                assert actual is not None;valid=0;binding=None;next_id+=1
                if used==limit:
                    assert text==f'QKD_FUNC_VERIFY_LIMIT seq={seq} used={used} limit={limit}\r\n';actual=None
                else:
                    used+=1
                    full=bits(packed(actual,64));mask=np.ones(3072,dtype=bool);mask[puncture.order(current['code'],codes[current['code']],128,307)]=False
                    kept=full[mask];padded=np.pad(kept,(0,19));sb=bits(packed(w[12:132]));tag=words(np.packbits(pa_model.pa_hash(padded,sb),bitorder='little').tobytes(),64)[0]
                    if tag!=w[132]|w[133]<<32:
                        tag_failures+=1;tag_rejected+=1;assert text==f'QKD_STREAM_TAG_REJECT seq={seq} bits={len(buffer)}\r\n'
                    else:
                        leak=ir_model.CODE_MB[current['code']]*128-307+revealed+64
                        buffer=np.concatenate([buffer,kept]);ref.add(w[2:5],w[5:8],w[8:11],leak,w[11]);append_count+=1
                        assert text==f'QKD_STREAM_ADDED seq={seq} block={w[1]} bits={len(buffer)} leak={leak}\r\n'
                    actual=None
            elif cmd==62:
                at=w[1];action,ell,_,reason=ref.decide(at);ell=ell//64*64 if action=='emit' else 0
                # C always reports the pre-ABORT accumulator size, then wipes it.
                emit=ref.emit_n if action!='abort' else len(buffer)
                ns=(emit+31)//32+33+((ell+1023)//1024-1)*32 if action=='emit' else 0
                expected=f'QKD_STREAM_DECISION seq={seq} action={dict(wait=0,emit=1,abort=2)[action]} bits={len(buffer)} ell={ell} split={int(ref._split)} emit_bits={emit} seed_words={ns}\r\n'
                assert text==expected,(index,text,expected)
                if action=='emit':pending=dict(ell=ell,emit=emit,ns=ns,split=ref._split);seed=[]
                elif action=='abort':aborted+=len(buffer);buffer=np.array([],dtype=np.uint8);ref.reset()
            elif cmd==63:
                seed+=w[4:];assert text==f'QKD_STREAM_SEED seq={seq} loaded={len(seed)}\r\n'
            elif cmd==64:
                emit=pending['emit'];ell=pending['ell'];before=len(buffer)
                padded=np.pad(buffer[:emit],(0,(-emit)%32));sb=bits(packed(seed));output=hankel_hash(padded,sb,ell)
                emissions.append(dict(index=index,input_bits=emit,output_bits=ell,tail_bits=before-emit,split=pending['split'],
                    input_sha256=hashlib.sha256(np.packbits(buffer[:emit],bitorder='little').tobytes()).hexdigest(),
                    PA_sha256=hashlib.sha256(np.packbits(output,bitorder='little').tobytes()).hexdigest(),words_verified=0))
                buffer=buffer[emit:].copy();retired+=emit;ref.emitted();pending=None;seed=[];seen=set()
                assert ref.n==len(buffer)
                assert text==f'QKD_STREAM_EMITTED seq={seq} output_bits={ell} input_bits={emit} tail_bits={len(buffer)} passes={(ell+1023)//1024}\r\n'
            elif cmd==65:
                values=re.findall(fr'QKD_STREAM_WORD seq={seq} word=(\d+) value=([0-9a-f]{{16}})\r\n',text);assert [int(i) for i,_ in values]==list(range(w[1],w[1]+w[2]))
                golden=words(np.packbits(output,bitorder='little').tobytes(),64)
                for i,v in values:assert int(v,16)==golden[int(i)];seen.add(int(i))
                emissions[-1]['words_verified']=len(seen)
            elif cmd==66:
                assert len(seen)==len(output)//64;output=None;seen=set();assert text==f'QKD_STREAM_OUTPUT_CLEARED seq={seq}\r\n'
            elif cmd in [61,81]:
                keep=next_id+(binding is not None);clock=at;clear();next_id=keep;at=clock
                assert text==f'QKD_SECURE_ABORT seq={seq} next_id={next_id} used={used}\r\n'
            elif cmd==67:
                assert text==f'QKD_STREAM_STATE seq={seq} bits={len(buffer)} next_id={next_id} pending={int(pending is not None)} out_bits={len(output) if output is not None else 0} rejected={tag_rejected} retired={retired} aborted={aborted}\r\n'
            elif cmd==69:
                assert not len(buffer) and output is None and pending is None
                sizes=[2000000,2000000,4000260,2000000];crcs=[f'{zlib.crc32(bytes(n)):08x}' for n in sizes]
                assert text==f'QKD_STREAM_WIPE_CHECK seq={seq} key_crc={crcs[0]} work_crc={crcs[1]} seed_crc={crcs[2]} output_crc={crcs[3]}\r\n';wipe_count+=1
            elif cmd==82:
                h=hashlib.sha256(np.packbits(buffer,bitorder='little').tobytes()).hexdigest()
                assert text==f'QKD_SECURE_BUFFER seq={seq} bits={len(buffer)} sha256={h}\r\n';digest_count+=1
            elif cmd==72:
                limit=w[1];assert text==f'QKD_FUNC_BUDGET_SET seq={seq} used={used} limit={limit}\r\n'
            elif cmd==73:assert text==f'QKD_FUNC_BUDGET_STATE seq={seq} used={used} limit={limit} remaining={limit-used}\r\n'
            else:raise AssertionError(cmd)
        else:raise AssertionError(op)
        row.update(verification_used=used,bits=len(buffer));rows.append(row)
    assert len(emissions)==2 and [e['split'] for e in emissions]==[False,True]
    assert all(e['words_verified']==e['output_bits']//64 for e in emissions)
    assert used==limit and tag_failures==3 and policy_rejected>=15 and wipe_count>=8 and digest_count==3
    for code in ['-7','-6','-4','-3','-8']:assert rejections.get(code,0)>0
    with (out/'cases.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    proof=dict(raw_replay_verified=True,source_result_sha256=sha(run/'result.json'),uart_sha256=sha(run/'uart.log'),tx_sha256=sha(run/'tx.jsonl'),
        commands_verified=len(tx),authenticated_dispatches=dispatches,policy_rejections=policy_rejected,transport_rejections=rejections,
        verified_appends=append_count,verification_used=used,verification_limit=limit,tag_failures=tag_failures,emissions=emissions,
        reset_budget_checks=resets,wipe_checks=wipe_count,buffer_digest_checks=digest_count,baseline_restored=True,
        scope='Physical PL IR/verify/accumulator PA; repeated PUBLIC r56 and synthetic bound counts. No independent FER trials, optical yield, production authentication or durable security claim.')
    (out/'verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
    job=json.loads((ROOT/'RUNNING_JOBS.json').read_text());assert job['run_directory']==run.relative_to(ROOT).as_posix() and job['port_released']
    job.update(status='VERIFIED_COMPLETE',report=(out/'verified_evidence.json').relative_to(ROOT).as_posix());write_checkpoint(ROOT/'RUNNING_JOBS.json',job)
    print('SECURE_ACCUMULATOR_RAW_REPLAY_PASS',len(tx),'commands',dispatches,'dispatches',append_count,'appends',len(emissions),'emissions')
if __name__=='__main__':main()
