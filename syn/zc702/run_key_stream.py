"""Coupled simulated decoy session -> actual PL IR -> verified DDR -> finite-key -> PL PA.

X-basis PE is separate from Z key data. All counters derive from the same source
time windows, with no fabricated scaling. Security proof of adaptive selection is
outside this functional test. Public test keys/seeds are persisted for replay.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,hashlib,json,struct,sys,time,zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
import dyn_ir as d
import ir_model as m
import pa_model as pa
import puncture as pu
from pa_accum import PAAccumulator
from hankel_exact import hankel_hash
from uart_session import UARTSession

def bits_words(bits,width=32):
    pad=(-len(bits))%width
    b=np.pad(np.asarray(bits,dtype=np.uint8),(0,pad))
    return list(map(int,np.frombuffer(np.packbits(b,bitorder='little').tobytes(),dtype='<u4' if width==32 else '<u8')))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class Source:
    def __init__(self,level):
        self.path=ROOT/f'data/sessions/session_{level}.npz';self.meta=json.loads(self.path.with_suffix('.json').read_text())
        data=np.load(self.path);z=data['basis']==0;x=~z
        self.t=data['t'][z];self.a=data['a'][z];self.b=data['b'][z];self.k=data['k'][z]
        self.tx=data['t'][x];self.kx=data['k'][x];self.ex=(data['a'][x]!=data['b'][x]).astype(np.uint8)
        self.level=level;self.size=len(self.t)//d.NKEY
    def block(self,index):
        lo=index*d.NKEY;hi=lo+d.NKEY
        xl=0 if index==0 else int(np.searchsorted(self.tx,self.t[lo-1],side='right'))
        xh=int(np.searchsorted(self.tx,self.t[hi-1],side='right'))
        nk=np.bincount(self.k[lo:hi],minlength=3).astype(int).tolist()
        nt=np.bincount(self.kx[xl:xh],minlength=3).astype(int).tolist()
        mt=np.bincount(self.kx[xl:xh],weights=self.ex[xl:xh],minlength=3).astype(int).tolist()
        if not sum(nt):raise ValueError('missing independent X-basis PE')
        return self.a[lo:hi].astype(np.int64),self.b[lo:hi].astype(np.int64),nk,nt,mt,xl,xh

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',default='COM3');ap.add_argument('--scenario',choices=['smoke','emit','split'],default='emit')
    ap.add_argument('--limit',type=int);ap.add_argument('--bad-blocks',type=int,default=90)
    ap.add_argument('--profile-emit',action='store_true',help='Measure board phases around final EMIT after ingest; no change to data or decisions')
    args=ap.parse_args();stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if args.profile_emit and args.scenario!='emit':ap.error('--profile-emit requires --scenario emit')
    folder=ROOT/'build/zc702/key_stream_runs'/stamp;folder.mkdir(parents=True)
    source=Source('weak');bad=Source('severe')
    result={'complete':False,'hardware_capture':True,'scenario':args.scenario,'started_utc':stamp,'port':args.port,
            'seed_source':'public_test_numpy_PCG64','seed_replay_value':2026102601,
            'source_kind':'simulated_decoy_BB84','physical_optical_data':False,'security_certified':False,
            'sources':{s.level:{'path':str(s.path),'sha256':sha(s.path),'metadata_sha256':sha(s.path.with_suffix('.json'))} for s in [source,bad]},
            'harness_files':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'syn/zc702/uart_session.py',ROOT/'model/hankel_exact.py']},
            'records':[],'decisions':[],'emissions':[],'negative_checks':[]}
    def persist():(folder/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    ref=PAAccumulator(source.meta['MU'],source.meta['P_K']);codes=m.load_codes(128);m.CN_MODE='nms75'
    ctrl=d.Controller(mode='basic',abort_basic=True);host_key=[];block_id=0;total_verified=0
    seedrng=np.random.default_rng(2026102601)
    def seed_words(n):return list(map(int,seedrng.integers(0,2**32,n,dtype=np.uint32)))
    try:
        with UARTSession(folder,args.port) as session:
            command=session.command;expect=session.expect
            result['firmware_manifest']=session.manifest
            command([61],r'QKD_STREAM_RESET seq={seq}');command([0],r'QKD_FUNC_RESET seq={seq}')
            def check_state(expected_bits):
                _,st=command([67],r'QKD_STREAM_STATE seq={seq} bits=(\d+) next_id=(\d+) pending=(\d+) out_bits=(\d+) rejected=(\d+) retired=(\d+) aborted=(\d+)')
                assert int(st.group(1))==expected_bits
                return list(map(int,st.groups()))
            def check_wiped():
                _,check=command([69],r'QKD_STREAM_WIPE_CHECK seq={seq} key_crc=([0-9a-fA-F]+) work_crc=([0-9a-fA-F]+) seed_crc=([0-9a-fA-F]+) output_crc=([0-9a-fA-F]+)')
                sizes=[2000000,2000000,4000260,2000000]
                assert [int(x,16) for x in check.groups()]==[zlib.crc32(bytes(size)) for size in sizes]
                result.setdefault('wipe_checks',[]).append({'all_buffers_zero_crc':True,'sizes_bytes':sizes})
            def readback_buffer(expected_key):
                expected_words=bits_words(expected_key);got=[]
                for offset in range(0,len(expected_words),128):
                    count=min(128,len(expected_words)-offset);seq,_=command([68,offset,count])
                    for k in range(offset,offset+count):
                        got.append(int(expect(fr'QKD_STREAM_BUFFER seq={seq} word={k} value=([0-9a-fA-F]{{8}})').group(1),16))
                assert got==expected_words,'retained tail differs'
                result.setdefault('buffer_readbacks',[]).append({'bits':len(expected_key),'all_words_match':True})
            def ingest(src,index,inject_bad_tag=False):
                nonlocal block_id,total_verified
                alice,bob,nk,nt,mt,xl,xh=src.block(index)
                q=float(np.float32(sum(mt)/sum(nt)));qword=struct.unpack('<I',struct.pack('<f',q))[0]
                _,p=command([1,0,qword,sum(nt)],r'QKD_FUNC_PLAN seq={seq} accept=(\d+) profile=(\d+) code=(\d+) r0=(\d+)')
                accept,profile,code,r0=map(int,p.groups());name,reference_pre=ctrl.plan(q,sum(nt))
                assert accept==int(name is not None)
                row={'source':src.level,'source_block':index,'key_start':index*d.NKEY,'test_start':xl,'test_stop':xh,
                     'source_first_pulse':int(src.t[index*d.NKEY]),'source_last_pulse':int(src.t[(index+1)*d.NKEY-1]),
                     'replay_time_seconds':block_id,
                     'nk':nk,'nt':nt,'mt':mt,'q_pe':q,'attempts':[],'outcome':'EARLY_DISCARD','added':False}
                if not accept:
                    result['records'].append(row);persist();return
                assert profile==0 and code==m.CODE_ORDER.index(name) and r0==reference_pre==0
                positions=pu.order(name,codes[name],128,d.D)
                prepared=d.prepare_block(alice,bob,13000+index,positions);keypos=prepared['key_pos'];v=prepared['v']
                types=np.zeros((1,d.N),dtype=np.int64);types[0,positions]=m.T_PUNCT
                bits=prepared['ch_bit'].reshape(1,d.N).copy();sym=np.where(types[0]==m.T_PUNCT,2,bits[0])
                syn=m.syndrome(codes[name],v.reshape(1,m.NCOL,128),128)
                ch=[sum(int(sym[w*16+k])<<(2*k) for k in range(16)) for w in range(192)]
                sy=bits_words(syn.reshape(-1));cfg=code|(8<<2)|(50<<8)|(1<<16)|(2<<18)|(16<<20)
                command([10,cfg,44,len(sy),0,*ch,*sy],r'QKD_FUNC_LOADED seq={seq}')
                revealed=0;attempt=0
                while True:
                    attempt+=1;assert attempt<=5
                    model=m.decode_attempt(types,bits,syn,codes[name],128,50,8,1,2,16,12);types=model['ch_type']
                    conv=bool(model['conv'][0])
                    _,actual=command([11],r'QKD_FUNC_ATTEMPT seq={seq} status=([0-9a-fA-F]+) iters=([0-9a-fA-F]+) errcnt=(\d+) cycles=(\d+) ticks=(\d+)')
                    st,it=int(actual.group(1),16),int(actual.group(2),16);err=int(actual.group(3))
                    wanted=(1 if conv else 2)|((int(model['decodes'][0])-1)<<4)|(int(model['n_usc'][0])<<16)
                    assert st&0x0fff0033==wanted and it&0xfff==int(model['iters'][0]) and it>>16&255==attempt
                    row['attempts'].append({'status':st,'iters':it,'cycles':int(actual.group(4)),'ticks':int(actual.group(5))})
                    if conv:break
                    if revealed==d.D:
                        command([13],r'QKD_FUNC_DISCARD seq={seq}');row['outcome']='DISCARD'
                        result['records'].append(row);persist();return
                    _,rr=command([2,int(model['n_usc'][0]),d.D-revealed],r'QKD_FUNC_REVEAL_PLAN seq={seq} count=(\d+)')
                    count=int(rr.group(1));assert count==ctrl.next_reveal(int(model['n_usc'][0]),d.D-revealed)
                    chosen=positions[revealed:revealed+count];values=[int(p)|(int(v[p])<<16) for p in chosen]
                    command([12,count,*values],r'QKD_FUNC_REVEALED seq={seq} count='+str(count))
                    types[0,chosen]=m.T_SHORT;bits[0,chosen]=v[chosen];revealed+=count
                # Read actual DMA KEY for independent end-to-end reference and provenance.
                keyseq,_=command([14]);received=[]
                for k in range(48):received.append(int(expect(fr'QKD_FUNC_KEY seq={keyseq} word={k} value=([0-9a-fA-F]{{16}})').group(1),16))
                assert received==bits_words(model['hard'][0],64)
                residual=int((model['hard'][0][keypos]!=alice).sum())
                assert err==int((model['hard'][0][keypos]!=bob).sum())
                padded=np.pad(alice,(0,2784-d.NKEY)).astype(np.uint8);sw=seed_words(120)
                sb=np.unpackbits(np.frombuffer(struct.pack('<120I',*sw),dtype=np.uint8),bitorder='little')
                tag=bits_words(pa.pa_hash(padded,sb),64)[0]
                if inject_bad_tag:tag^=1
                values=[60,block_id,*nk,*nt,*mt,block_id,*sw,tag&0xffffffff,tag>>32]
                seq,_=command(values)
                if inject_bad_tag or residual:
                    rr=expect(fr'QKD_STREAM_TAG_REJECT seq={seq} bits=(\d+)');assert int(rr.group(1))==sum(map(len,host_key))
                    row['outcome']='INJECTED_TAG_REJECT' if inject_bad_tag else 'WRONG_KEY_TAG_REJECT'
                    result['negative_checks'].append({'case':row['outcome'],'counts_unchanged':True})
                    result['records'].append(row);persist();return
                reply=expect(fr'QKD_STREAM_ADDED seq={seq} block={block_id} bits=(\d+) leak=(\d+)')
                leak=m.CODE_MB[name]*128-d.D+revealed+64
                assert int(reply.group(2))==leak
                host_key.append(alice.astype(np.uint8));ref.add(nk,nt,mt,leak,block_id)
                assert int(reply.group(1))==ref.n==sum(map(len,host_key))
                row.update(outcome='VERIFIED_ADDED',added=True,stream_block_id=block_id,code=name,revealed=revealed,leak=leak,
                           key_sha256=hashlib.sha256(np.packbits(alice,bitorder='little').tobytes()).hexdigest())
                block_id+=1;total_verified+=1;result['records'].append(row);persist()
                if total_verified%10==0:print('STREAM_PROGRESS',total_verified,'verified bits',ref.n,src.level,index,flush=True)
            def decide(at):
                nonlocal host_key
                _,answer=command([62,at],r'QKD_STREAM_DECISION seq={seq} action=(\d+) bits=(\d+) ell=(\d+) split=(\d+) emit_bits=(\d+) seed_words=(\d+)')
                action,n,ell,split,emit,ns=map(int,answer.groups());expected,refell,_,reason=ref.decide(at)
                assert action=={'wait':0,'emit':1,'abort':2}[expected] and n==ref.n
                assert ell==(refell//64*64 if expected=='emit' else 0) and bool(split)==ref._split
                result['decisions'].append(dict(action=expected,bits=n,ell=ell,split=bool(split),emit_bits=emit,reason=reason,at_virtual_seconds=at))
                persist()
                if expected=='abort':
                    host_key=[];ref.reset();assert check_state(0)[0]==0;check_wiped()
                    return expected
                if expected!='emit':return expected
                assert emit==ref.emit_n and emit<=n and ell<=emit
                # Verify incomplete seed cannot release output, then supply the full public seed once.
                _,reject=command([64],r'QKD_STREAM_REJECT seq={seq} reason=INCOMPLETE_SEED bits=(\d+)')
                assert int(reject.group(1))==n
                result['negative_checks'].append({'case':'INCOMPLETE_SEED','output_withheld':True})
                seed=seed_words(ns);all_key=np.concatenate(host_key);input_bits=all_key[:emit]
                padded=np.pad(input_bits,(0,(-emit)%32));seed_bits=np.unpackbits(np.frombuffer(struct.pack('<'+'I'*ns,*seed),dtype=np.uint8),bitorder='little')
                np.savez_compressed(folder/f'emit_{len(result["emissions"])}_reference.npz',key=input_bits,seed=seed_bits,ell=ell)
                print('NTT_REFERENCE_START input',emit,'output',ell,flush=True)
                expected_bits=hankel_hash(padded,seed_bits,ell);expected_words=bits_words(expected_bits,64)
                for offset in range(0,ns,4000):
                    part=seed[offset:offset+4000]
                    command([63,ns,offset,len(part),*part],r'QKD_STREAM_SEED seq={seq} loaded='+str(offset+len(part)))
                _,done=command([64],r'QKD_STREAM_EMITTED seq={seq} output_bits=(\d+) input_bits=(\d+) tail_bits=(\d+) passes=(\d+)')
                assert list(map(int,done.groups()))==[ell,emit,n-emit,(ell+1023)//1024]
                received=[]
                for offset in range(0,ell//64,128):
                    count=min(128,ell//64-offset);seq,_=command([65,offset,count])
                    for k in range(offset,offset+count):received.append(int(expect(fr'QKD_STREAM_WORD seq={seq} word={k} value=([0-9a-fA-F]{{16}})').group(1),16))
                assert received==expected_words,'PL PA output mismatch against exact integer NTT'
                output=struct.pack('<'+'Q'*len(received),*received)
                (folder/f'emit_{len(result["emissions"])}_output.bin').write_bytes(output)
                result['emissions'].append({'input_bits':emit,'ell':ell,'split':bool(split),'passes':(ell+1023)//1024,
                    'all_output_words_match':True,'output_sha256':hashlib.sha256(output).hexdigest(),'tail_bits':n-emit})
                tail=all_key[emit:];host_key=[tail] if len(tail) else [];ref.emitted()
                assert ref.n==n-emit
                command([66],r'QKD_STREAM_OUTPUT_CLEARED seq={seq}');check_state(ref.n)
                if len(tail):readback_buffer(tail)
                else:check_wiped()
                print('PL_PA_FINITE_EMIT_PASS',emit,'->',ell,'tail',ref.n,flush=True);persist();return expected
            ingest(source,0,inject_bad_tag=True);check_state(0)
            count=min(source.size,args.limit) if args.limit else source.size
            # Never retain block 0 after its negative-test public transcript.
            for index in range(1,count):
                ingest(source,index)
                if (index+1)%25==0:assert decide(block_id)=='wait','unexpected automatic emit; preserve receipt'
            if args.scenario=='smoke':
                assert decide(block_id)=='wait';check_state(ref.n)
                command([61],r'QKD_STREAM_RESET seq={seq}');assert check_state(0)[0]==0
                check_wiped()
            elif args.scenario=='emit':
                if args.profile_emit:
                    import profile_protocol
                    result['profile_timer']=profile_protocol.enable(session)
                    result['profile_scope']='Final decision/seed/PA/output only; ingest unprofiled; host NTT reference outside board command spans'
                assert decide(block_id+3601)=='emit'
                assert ref.n==0 and result['emissions'][-1]['tail_bits']==0
                if args.profile_emit:
                    result['profile_snapshots']=profile_protocol.collect(session)
                    profile_protocol.disable(session);persist()
            else:
                assert decide(block_id)=='wait'
                emitted=False
                last_bad=-1
                for index in range(min(bad.size,args.bad_blocks)):
                    ingest(bad,index)
                    last_bad=index
                    action=decide(block_id)
                    if action=='emit':
                        assert result['emissions'][-1]['split'];emitted=True;break
                assert emitted,'split not reached in supplied dataset'
                action=decide(block_id)
                for index in range(last_bad+1,min(bad.size,args.bad_blocks)):
                    if action=='abort':break
                    ingest(bad,index);action=decide(block_id)
                    assert action!='emit','unexpected second emit; preserve receipt'
                assert action=='abort','bad retained tail did not reach abort gate'
            result.update(complete=True,verified_blocks=total_verified,remaining_bits=ref.n)
    except BaseException as exc:
        result['error']=repr(exc);raise
    finally:persist();print('KEY_STREAM_EVIDENCE',folder,flush=True)
    print('KEY_STREAM_PASS',args.scenario,total_verified,flush=True)

if __name__=='__main__':main()
