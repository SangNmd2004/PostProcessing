"""Advance the next missing fixed-size FER stratum after finite-key work releases the board."""
from pathlib import Path
import argparse,json,subprocess,sys,time
from checkpoint_io import write_checkpoint
ROOT=Path(__file__).resolve().parents[2]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--stage',required=True,type=Path);args=ap.parse_args();stage=args.stage.resolve();out=stage/'fer_q05_followup';out.mkdir(parents=True,exist_ok=False)
    state=dict(status='WAITING_FOR_FINITE_SOURCE',complete=False,planned_trials=10000,qber=.05,code='r12',seed_base=4200000)
    def save():write_checkpoint(out/'STATUS.json',state)
    save()
    while True:
        finite=json.loads((stage/'prospective_finite/STATUS.json').read_text())
        if finite.get('complete') or finite.get('status')=='STOPPED_ERROR':break
        time.sleep(5)
    job=json.loads((ROOT/'RUNNING_JOBS.json').read_text());assert job.get('port_released') and job.get('baseline_restored'),job
    state['status']='RUNNING';save()
    argv=[sys.executable,'syn/zc702/run_managed_fer.py','--trials','10000','--qber','.05','--code','r12','--seed-base','4200000'];state['command']=argv;save()
    with (out/'stdout.log').open('wb') as stdout,(out/'stderr.log').open('wb') as stderr:
        p=subprocess.run(argv,cwd=ROOT,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
    state.update(status='VERIFIED_COMPLETE' if p.returncode==0 else 'STOPPED_ERROR',complete=p.returncode==0,returncode=p.returncode,last_job=json.loads((ROOT/'RUNNING_JOBS.json').read_text()));save()
    print('Q05_FOLLOWUP_FINISHED',state['status'],flush=True)
if __name__=='__main__':main()
