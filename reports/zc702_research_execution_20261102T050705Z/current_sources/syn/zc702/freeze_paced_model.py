"""Freeze measured K1 slot/gap demands and predictions before new arrival tests."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,random,statistics,sys,time
from verify_paced_board import verify,ROOT
sys.path.insert(0,str(ROOT/'model'))
from paced_component_model import simulate
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('training',type=Path);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result,measures,rows=verify(args.training.resolve());selected=[m for m in measures if m['k']==1 and m['rtt']==1000 and m['interval']==0 and m['policy'] in [0,1]]
    assert len(selected)>=6
    seqs={m['run_seq'] for m in selected};jobs=[r for r in rows if r['run_seq'] in seqs];assert all(r['outcome']==0 for r in jobs)
    service=[statistics.median(r['complete']-r['dispatch'] for r in jobs if r['slot']==slot) for slot in range(4)]
    gaps=[]
    for policy in [0,1]:
        values=[]
        for m in selected:
            if m['policy']!=policy:continue
            batch=[r for r in jobs if r['run_seq']==m['run_seq']]
            values += [max(0,b['dispatch']-a['complete']) for a,b in zip(batch,batch[1:])]
        gaps.append(statistics.median(values))
    proxy=[2765-next(r['leak'] for r in jobs if r['slot']==slot) for slot in range(4)]
    params=dict(slot_service_us=service,profile_gap_us=gaps,slot_IR_proxy_bits=proxy)
    e=simulate(params,128,0,0);t=simulate(params,128,0,1)
    ye=e['IR_proxy_bits']/128;yt=t['IR_proxy_bits']/128;mu_e=128e6/e['elapsed_us'];mu_t=128e6/t['elapsed_us']
    crossing=ye*mu_e/yt if ye>yt>0 and mu_t>mu_e and yt*mu_t>ye*mu_e else None
    reference=crossing or mu_e
    cases=[dict(k=1,jobs=128,rtt=1000,interval=max(1,round(1e6/(reference*factor))),capacity=128,policy=p,repeat=r,phase='arrival_held_out',arrival_factor=factor) for factor in [.5,.9,1,1.1,2] for p in [0,1,2] for r in range(2)]
    random.Random(2026110212).shuffle(cases)
    for c in cases:
        prediction=simulate(params,c['jobs'],c['interval'],c['policy']);c['prediction']={k:v for k,v in prediction.items() if k!='rows'}
    config=dict(frozen_before_capture_utc=datetime.now(timezone.utc).isoformat(),freeze_monotonic_ns=time.perf_counter_ns(),fixture_sha256=result['config']['fixture_sha256'],
        training_run=args.training.resolve().relative_to(ROOT).as_posix(),training_result_sha256=sha(args.training/'result.json'),params=params,
        model_sha256=sha(ROOT/'model/paced_component_model.py'),IR_proxy_fluid_crossing_blocks_s=crossing,
        accuracy_criteria=dict(mean_absolute_error_pct_max=10,max_absolute_error_pct_max=20,IR_proxy_bits_error_pct_max=5,denominator='prediction',scope='engineering tolerance; not confidence bounds'),
        scope='K1 DDR IR; held-out arrival schedules on repeated training inputs; fixed f_adj; no PA/secret-yield crossover claim',cases=cases)
    (out/'frozen_validation.json').write_text(json.dumps(config,indent=2)+'\n');(out/'model_at_freeze.py').write_bytes((ROOT/'model/paced_component_model.py').read_bytes())
    print('PACED_MODEL_FROZEN',out,'IR_proxy_crossing',crossing,'params',params)
if __name__=='__main__':main()
