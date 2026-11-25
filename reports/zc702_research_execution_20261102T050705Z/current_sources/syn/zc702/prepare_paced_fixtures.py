"""Freeze paired EFF/THR public BSC inputs and independent test-basis PE counts."""
from pathlib import Path
import argparse,hashlib,json,struct,sys
import numpy as np
from generate_uart_campaign import encode
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
import dyn_ir as d,ir_model as m,puncture as pu
def words(b):return list(struct.unpack('<'+'I'*(len(b)//4),b))
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path);ap.add_argument('--seed',type=int,default=2026110210);args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    codes=m.load_codes(128);m.CN_MODE='nms75';rows=[];sources=[]
    for index in range(2):
        rng=np.random.default_rng(args.seed+index);alice=rng.integers(0,2,2765,dtype=np.int64);bob=alice^(rng.random(2765)<.02)
        pe_rng=np.random.default_rng(args.seed+100000+index);npe=10000;pe_errors=int(pe_rng.binomial(npe,.02));qpe=float(np.float32(pe_errors/npe))
        source=dict(index=index,seed=args.seed+index,n_pe=npe,pe_errors=pe_errors,q_pe=qpe,input_sha256=hashlib.sha256(alice.astype('u1').tobytes()+bob.astype('u1').tobytes()).hexdigest())
        np.savez_compressed(out/f'input_{index}.npz',alice=alice,bob=bob);source['file']=f'input_{index}.npz';source['file_sha256']=hashlib.sha256((out/source['file']).read_bytes()).hexdigest();sources.append(source)
        for profile in [0,1]:
            ctrl=d.Controller(mode='basic' if profile==0 else 'dynamic',f_target=1.3,f_safe=1.7,pe_z=1.5,abort_basic=True)
            name,r0=ctrl.plan(qpe,npe);assert name is not None
            blk=d.prepare_block(alice,bob,args.seed+200000+index,pu.order(name,codes[name],128,307));res=d.run_block(blk,codes,name,r0,ctrl,True)
            sym=res['sym'];sb=res['syn'].reshape(-1);hard=res['hard']
            ch=[sum(int(sym[w*16+k])<<(2*k) for k in range(16)) for w in range(192)]
            syn=[sum(int(sb[w*32+k])<<k for k in range(32)) for w in range(len(sb)//32)]
            expected=[int(t['conv'])<<31|t['pp']<<28|t['usc']<<16|t['iters'] for t in res['trace']]
            key=[sum(int(hard[w*64+k])<<k for k in range(64)) for w in range(48)]
            cfg=m.CODE_ORDER.index(name)|(8<<2)|(50<<8)|(1<<16)|(2<<18)|(16<<20)
            payload=encode(cfg,44,r0,expected,[t['nrev'] for t in res['trace']],res['errcnt'],ch,syn,res['revs'],key)
            slot=index*2+profile;(out/f'vector_{slot}.bin').write_bytes(payload)
            row=dict(slot=slot,input_index=index,profile=profile,code=name,r0=r0,attempts=res['attempts'],revealed=res['revealed'],leak_ir=res['leak'],outcome='correct' if res['success'] else 'wrong' if res['undetected'] else 'discard',file=f'vector_{slot}.bin',sha256=hashlib.sha256(payload).hexdigest())
            rows.append(row);print('PAIRED_FIXTURE',row,flush=True)
    files=['syn/zc702/prepare_paced_fixtures.py','model/dyn_ir.py','model/ir_model.py','model/codes.json','model/puncture.py','model/punct.json','syn/zc702/generate_uart_campaign.py']
    config=dict(seed=args.seed,qber=.02,sources=sources,vectors=rows,planning='fixed f_adj=1.3 per job; independent synthetic X-basis PE; no controller feedback update',
        independent_FER_trials=2,scope='PUBLIC paired pool for repeated DDR timing, no secret-yield/FER qualification',source_sha256={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files})
    (out/'fixtures.json').write_text(json.dumps(config,indent=2)+'\n');print('PACED_FIXTURES_FROZEN',out)
if __name__=='__main__':main()
