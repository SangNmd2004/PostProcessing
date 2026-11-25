"""Generate a new synthetic source sequentially and freeze finite-key decisions before board capture."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,sys,time
import numpy as np
from run_key_stream import Source,ROOT
sys.path.insert(0,str(ROOT/'model'))
from gen_qkd_session import run_session
import dyn_ir as d,ir_model as m,puncture as pu
from pa_accum import PAAccumulator
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--seed',type=int,default=2026110220);args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    generated,meta=run_session('WEAK',1_250_000,seed=args.seed)
    np.savez_compressed(out/'session_weak.npz',**generated);(out/'session_weak.json').write_text(json.dumps(meta,indent=2)+'\n')
    source=Source('weak',out);codes=m.load_codes(128);m.CN_MODE='nms75';ctrl=d.Controller(mode='basic',abort_basic=True)
    acc=PAAccumulator(meta['MU'],meta['P_K']);records=[];decisions=[];block_id=0
    for index in range(1,source.size):
        alice,bob,nk,nt,mt,xl,xh=source.block(index);q=float(np.float32(sum(mt)/sum(nt)));name,r0=ctrl.plan(q,sum(nt))
        row=dict(source_block=index,nk=nk,nt=nt,mt=mt,test_start=xl,test_stop=xh,outcome='EARLY_DISCARD')
        if name is not None:
            block=d.prepare_block(alice,bob,13000+index,pu.order(name,codes[name],128,307));res=d.run_block(block,codes,name,r0,ctrl)
            row.update(code=name,attempts=res['attempts'],leak=res['leak']+64,outcome='VERIFIED_ADDED' if res['success'] else 'WRONG_KEY_TAG_REJECT' if res['undetected'] else 'DISCARD')
            if res['success']:
                acc.add(nk,nt,mt,res['leak']+64,block_id);row['stream_block_id']=block_id;block_id+=1
        records.append(row)
        if (index+1)%25==0:
            action,ell,_,_=acc.decide(block_id);assert action=='wait','Natural emission occurred before declared end; preserve dataset and revise explicit scenario'
            decisions.append(dict(action=action,bits=acc.n,ell=0,split=bool(acc._split),emit_bits=acc.emit_n,at_virtual_seconds=block_id))
        if index%50==0:print('FROZEN_SOURCE_MODEL_PROGRESS',index,'/',source.size,'retained',acc.n,flush=True)
    action,ell,_,_=acc.decide(block_id+3601);assert action=='emit' and not acc._split
    decisions.append(dict(action=action,bits=acc.n,ell=ell//64*64,split=False,emit_bits=acc.emit_n,at_virtual_seconds=block_id+3601))
    plan=dict(source_seed=args.seed,source_sha256=sha(out/'session_weak.npz'),metadata_sha256=sha(out/'session_weak.json'),source_blocks=source.size,
        records=records,decisions=decisions,expected_verified_blocks=block_id,
        frozen_utc=datetime.now(timezone.utc).isoformat(),freeze_monotonic_ns=time.perf_counter_ns(),
        time_contract='Virtual time increments per retained block, then declared idle +3601s; not prediction of optical acquisition first-EMIT distribution or wall time',
        scope='New independent synthetic source, predeclared model output and event schedule, fresh future board observations; functional only',
        source_files_sha256={n:sha(ROOT/n) for n in ['syn/zc702/prepare_finite_source.py','syn/zc702/run_key_stream.py','model/gen_qkd_session.py','model/dyn_ir.py','model/pa_accum.py','model/pa_model.py']})
    (out/'frozen_prediction.json').write_text(json.dumps(plan,indent=2)+'\n');print('FINITE_SOURCE_PREDICTIONS_FROZEN',out,block_id,acc.n,ell//64*64)
if __name__=='__main__':main()
