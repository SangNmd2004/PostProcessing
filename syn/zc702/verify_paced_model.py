"""Compare frozen K1 predictions with held-out arrival measurements, preserving failures."""
from pathlib import Path
import argparse,csv,hashlib,importlib.util,json,statistics,sys
from verify_paced_board import verify,ROOT
sys.path.insert(0,str(ROOT/'model'))
from paced_component_model import simulate
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path);ap.add_argument('--frozen',required=True,type=Path);ap.add_argument('--output',required=True,type=Path);args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result,measures,_=verify(args.run.resolve());frozen=json.loads(args.frozen.read_text())
    assert result['config_source_sha256']==sha(args.frozen) and result['config']==frozen
    model_path=args.frozen.parent/'model_at_freeze.py'
    assert frozen['freeze_monotonic_ns']<result['capture_start_monotonic_ns'] and frozen['model_sha256']==sha(model_path)
    spec=importlib.util.spec_from_file_location('frozen_paced_component',model_path);model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    assert frozen['training_result_sha256']==sha(ROOT/frozen['training_run']/'result.json')
    rows=[]
    for case,observed in zip(frozen['cases'],measures):
        predicted=model.simulate(frozen['params'],case['jobs'],case['interval'],case['policy']);assert case['prediction']=={k:v for k,v in predicted.items() if k!='rows'}
        rows.append(dict(policy=case['policy'],interval_us=case['interval'],repeat=case['repeat'],prediction_us=predicted['elapsed_us'],board_us=observed['elapsed_us'],
            error_pct=100*(observed['elapsed_us']-predicted['elapsed_us'])/predicted['elapsed_us'],predicted_IR_proxy_bits=predicted['IR_proxy_bits'],observed_IR_proxy_bits=observed['IR_retained_proxy_bits'],
            IR_proxy_error_pct=100*(observed['IR_retained_proxy_bits']-predicted['IR_proxy_bits'])/predicted['IR_proxy_bits']))
    errors=[abs(r['error_pct']) for r in rows];proxy=max(abs(r['IR_proxy_error_pct']) for r in rows);criteria=frozen['accuracy_criteria']
    accepted=statistics.mean(errors)<=criteria['mean_absolute_error_pct_max'] and max(errors)<=criteria['max_absolute_error_pct_max'] and proxy<=criteria['IR_proxy_bits_error_pct_max']
    with (out/'prediction_comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    proof=dict(raw_replay_verified=True,frozen_before_capture=True,model_accepted=accepted,measurements=len(rows),mean_absolute_error_pct=statistics.mean(errors),max_absolute_error_pct=max(errors),max_IR_proxy_bits_error_pct=proxy,
        source_result_sha256=sha(args.run/'result.json'),frozen_config_sha256=sha(args.frozen),verifier_sha256=sha(Path(__file__)),scope=frozen['scope'],criteria=criteria)
    (out/'verified_prediction.json').write_text(json.dumps(proof,indent=2)+'\n')
    print('PACED_FROZEN_PREDICTION_COMPARISON',json.dumps(proof),flush=True)
if __name__=='__main__':main()
