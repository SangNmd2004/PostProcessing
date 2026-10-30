"""Replay a naturally observed wrong codeword and verify Alice's genuine tag rejects it on both paths."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,struct,subprocess,sys,zlib
import numpy as np
from uart_session import ROOT,UARTSession
sys.path.insert(0,str(ROOT/'model'))
import ir_model as m
import puncture as pu
import pa_model as pa
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--ablation',type=Path,required=True);ap.add_argument('--port',default='COM3')
args=ap.parse_args();source=args.ablation.resolve();ablation=json.loads((source/'result.json').read_text());assert ablation['complete']
proof=ROOT/'reports'/('zc702_board_ablation_'+ablation['started_utc'])/'verified_evidence.json'
assert json.loads(proof.read_text())['source_result_sha256']==hashlib.sha256((source/'result.json').read_bytes()).hexdigest()
matches=[(b,slot,r) for b in ablation['batches'] if b['configuration']=='NMS_GS_ET_PP' for slot,r in enumerate(b['rows']) if r['outcome']=='WRONG_CODEWORD']
assert matches,'No natural wrong-codeword fixture available; do not fabricate one'
batch,slot,row=matches[0];sessionfolder=ROOT/batch['session']
frames={r['seq']:r for r in json.loads((sessionfolder/'tx_manifest.json').read_text())}
packet=frames[batch['load_seqs'][slot]];data=(sessionfolder/packet['file']).read_bytes();assert hashlib.sha256(data).hexdigest()==packet['sha256']
w=struct.unpack('<'+'I'*(len(data)//4),data);v=w[3:];assert hashlib.sha256(struct.pack('<'+'I'*len(v),*v)).hexdigest()==row['payload_sha256']
cfg,cfg2,pre,attempts,ns,err,nrev=v[:7];at=7+2*attempts
expected=v[7:7+attempts];counts=v[7+attempts:7+2*attempts];ch=v[at:at+192];at+=192;syn=v[at:at+ns];at+=ns;revs=v[at:at+nrev]
expected_key=[v[i]|v[i+1]<<32 for i in range(len(v)-96,len(v),2)]
rng=np.random.default_rng(row['seed']);alice=rng.integers(0,2,2765,dtype=np.int64)
bob=alice^(rng.random(2765)<ablation['config']['qber']).astype(np.int64)
assert hashlib.sha256(alice.astype(np.uint8).tobytes()+bob.astype(np.uint8).tobytes()).hexdigest()==row['input_sha256']
name=m.CODE_ORDER[cfg&3];positions=list(map(int,pu.order(name,m.load_codes(128)[name],128,307)))
keep=np.ones(3072,dtype=bool);keep[positions]=False
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');folder=ROOT/'build/zc702/wrong_codeword_runs'/stamp;folder.mkdir(parents=True)
result=dict(complete=False,hardware_capture=True,started_utc=stamp,source_ablation=str(source.relative_to(ROOT)),
    source_result_sha256=hashlib.sha256((source/'result.json').read_bytes()).hexdigest(),fixture=row,records=[],
    scope='Natural wrong-key fixture; genuine Alice tags; public test seeds and synthetic rejected metadata; no secret output')
(folder/'runner_at_start.py').write_bytes(Path(__file__).read_bytes())
def save():(folder/'result.json').write_text(json.dumps(result,indent=2)+'\n')
def hash_words(bits,seed):
    padded=np.pad(bits,(0,(-len(bits))%32))
    seedbits=np.unpackbits(np.frombuffer(struct.pack('<120I',*seed),dtype=np.uint8),bitorder='little')
    return list(map(int,np.frombuffer(np.packbits(pa.pa_hash(padded,seedbits),bitorder='little').tobytes(),dtype='<u8')))
try:
    with UARTSession(folder,args.port) as session:
        result['firmware_manifest']=session.manifest;command=session.command
        command([61],r'QKD_STREAM_RESET seq={seq}')
        command([73],r'QKD_FUNC_BUDGET_STATE seq={seq} used=0 limit=18446 remaining=18446')
        for test,op in enumerate([20,60]):
            command([10,cfg,cfg2,ns,pre,*ch,*syn,*revs[:pre]],r'QKD_FUNC_LOADED seq={seq}');cursor=pre
            for index,e in enumerate(expected):
                _,reply=command([11],r'QKD_FUNC_ATTEMPT seq={seq} status=([0-9a-fA-F]+) iters=([0-9a-fA-F]+) errcnt=(\d+) cycles=(\d+) ticks=(\d+)')
                status,iters=int(reply.group(1),16),int(reply.group(2),16)
                assert status&0x0fff0033==((1 if e>>31 else 2)|((e>>28)&3)<<4|(e&0x0fff0000)) and iters&4095==e&4095
                if e>>31:assert int(reply.group(3))==err;break
                count=counts[index];command([12,count,*revs[cursor:cursor+count]],r'QKD_FUNC_REVEALED seq={seq} count='+str(count));cursor+=count
            seq,_=command([14]);actual=[]
            for k in range(48):actual.append(int(session.expect(fr'QKD_FUNC_KEY seq={seq} word={k} value=([0-9a-fA-F]{{16}})').group(1),16))
            assert actual==expected_key
            bits=np.unpackbits(np.frombuffer(struct.pack('<48Q',*actual),dtype=np.uint8),bitorder='little')[keep]
            residual=int((bits!=alice).sum());assert residual==row['residual_errors']>0
            seed=list(map(int,np.random.default_rng(2026102704+test).integers(0,2**32,120,dtype=np.uint32)))
            alice_tag=hash_words(alice,seed)[0];wrong_tag=hash_words(bits,seed)[0];assert alice_tag!=wrong_tag
            if op==20:
                pa_seed=list(map(int,np.random.default_rng(2026102714).integers(0,2**32,120,dtype=np.uint32)))
                expected_pa=[v for word in hash_words(alice,pa_seed) for v in [word&0xffffffff,word>>32]]
                values=[20,cfg&3,*positions,*seed,alice_tag&0xffffffff,alice_tag>>32,*pa_seed,*expected_pa]
                seq,_=command(values,r'QKD_FUNC_TAG_REJECT seq={seq} pa_emitted=0')
            else:
                # These metadata counts must never enter the accumulator: rejection is before append.
                values=[60,0,2765,0,0,100,20,0,1,0,0,0,*seed,alice_tag&0xffffffff,alice_tag>>32]
                seq,_=command(values,r'QKD_STREAM_TAG_REJECT seq={seq} bits=0')
            command([73],fr'QKD_FUNC_BUDGET_STATE seq={{seq}} used={test+1} limit=18446 remaining={18445-test}')
            command([67],fr'QKD_STREAM_STATE seq={{seq}} bits=0 next_id=0 pending=0 out_bits=0 rejected={test} retired=0 aborted=0')
            result['records'].append(dict(op=op,verification_seq=seq,residual_errors=residual,alice_tag=f'{alice_tag:016x}',
                actual_wrong_key_tag=f'{wrong_tag:016x}',wrong_key_sha256=hashlib.sha256(struct.pack('<48Q',*actual)).hexdigest(),output_withheld=True));save()
        command([61],r'QKD_STREAM_RESET seq={seq}')
        _,reply=command([69],r'QKD_STREAM_WIPE_CHECK seq={seq} key_crc=([0-9a-fA-F]+) work_crc=([0-9a-fA-F]+) seed_crc=([0-9a-fA-F]+) output_crc=([0-9a-fA-F]+)')
        assert [int(x,16) for x in reply.groups()]==[zlib.crc32(bytes(n)) for n in [2000000,2000000,4000260,2000000]]
        command([73],r'QKD_FUNC_BUDGET_STATE seq={seq} used=2 limit=18446 remaining=18444')
        result['complete']=True
except BaseException as exc:result['error']=repr(exc);raise
finally:save();print('WRONG_CODEWORD_EVIDENCE',folder,flush=True)
subprocess.run([sys.executable,str(ROOT/'syn/zc702/report_wrong_codeword_test.py'),str(folder)],check=True)
print('NATURAL_WRONG_CODEWORD_TAG_GATE_PASS',folder,flush=True)
