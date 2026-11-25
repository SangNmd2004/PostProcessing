"""Single-owner fixed-size FER cohort, with honest live job state and verified completion."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,subprocess,sys,time
import serial
from checkpoint_io import write_checkpoint
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--trials',type=int,default=10000);ap.add_argument('--qber',type=float,default=.01);ap.add_argument('--code',default='r34');ap.add_argument('--seed-base',type=int,default=4100000);ap.add_argument('--port',default='COM3');args=ap.parse_args()
    job=json.loads((ROOT/'RUNNING_JOBS.json').read_text());assert job.get('port_released') and job['status']!='COMPLETED_PENDING_RAW_VERIFICATION',job
    for folder in (ROOT/'build/zc702/fer_runs').iterdir():
        if not (folder/'result.json').exists():continue
        old=json.loads((folder/'result.json').read_text())
        if (old['qber'],old['code'])==(args.qber,args.code):assert max(old['seed_base'],args.seed_base)>=min(old['seed_base']+old['planned_trials'],args.seed_base+args.trials),'Seed ranges overlap'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'build/zc702/managed_fer'/stamp;out.mkdir(parents=True,exist_ok=False)
    argv=[sys.executable,str(ROOT/'syn/zc702/run_fer_campaign.py'),'--trials',str(args.trials),'--qber',str(args.qber),'--code',args.code,'--seed-base',str(args.seed_base),'--port',args.port]
    names=['syn/zc702/run_managed_fer.py','syn/zc702/run_fer_campaign.py','syn/zc702/verify_experiment_run.py','syn/zc702/uart_session.py','syn/zc702/program_smoke.tcl']
    plan=dict(trials=args.trials,qber=args.qber,code=args.code,seed_base=args.seed_base,command=argv,declared_before_run_utc=datetime.now(timezone.utc).isoformat(),
        stop_rule='Fixed sample size; never stop for favorable CI. Tool/transport/hardware errors stop and retain incomplete evidence.',source_sha256={n:sha(ROOT/n) for n in names})
    (out/'frozen_plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    for n in names:
        dest=out/'source_snapshot'/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/n).read_bytes())
    child=None;run=None;proof=None
    def status(s,**kw):write_checkpoint(ROOT/'RUNNING_JOBS.json',dict(status=s,pid=os.getpid(),child_pid=child.pid if child else None,script='syn/zc702/run_managed_fer.py',controller=out.relative_to(ROOT).as_posix(),port=args.port,run_directory=run.relative_to(ROOT).as_posix() if run else None,**kw))
    try:
        status('STARTING',port_released=False,verified_trials=0)
        with (out/'stdout.log').open('wb') as stdout,(out/'stderr.log').open('wb') as stderr:
            env=os.environ.copy();env['QKD_DISABLE_COMPLETION_HOOK']='1'
            child=subprocess.Popen(argv,cwd=ROOT,stdout=stdout,stderr=stderr,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
            while child.poll() is None:
                candidates=[]
                for folder in (ROOT/'build/zc702/fer_runs').iterdir():
                    p=folder/'result.json'
                    if not p.exists():continue
                    try:r=json.loads(p.read_text())
                    except (OSError,json.JSONDecodeError):continue
                    if (r['seed_base'],r['qber'],r['code'],r['planned_trials'])==(args.seed_base,args.qber,args.code,args.trials):candidates.append((folder,r))
                assert len(candidates)<=1
                if candidates:
                    run,r=candidates[0];count=len(r['records']);status('RUNNING' if count<args.trials else 'COMPLETED_PENDING_RAW_VERIFICATION',port_released=False,captured_trials=count,planned_trials=args.trials)
                time.sleep(5)
        assert child.returncode==0,'FER child failed; see logs'
        assert run is not None
        r=json.loads((run/'result.json').read_text());report=ROOT/'reports'/('zc702_fer_'+r['started_utc']);proof_path=report/'verified_evidence.json';proof=json.loads(proof_path.read_text())
        assert r['complete'] and proof['raw_replay_verified'] and proof['source_result_sha256']==sha(run/'result.json') and len(r['records'])==args.trials
        baseline=json.loads((ROOT/'build/zc702/uart_firmware/manifest.json').read_text())
        for n,h in baseline['files'].items():assert sha(ROOT/n)==h,n
        with serial.Serial(args.port,115200,timeout=.1):pass
        receipt=dict(status='VERIFIED_COMPLETE',proof=proof_path.relative_to(ROOT).as_posix(),source_result_sha256=sha(run/'result.json'),port_released=True,baseline_files_verified=len(baseline['files']),baseline_was_firmware_under_test=True,baseline_restored=True)
        (out/'verified_completion.json').write_text(json.dumps(receipt,indent=2)+'\n')
        status('VERIFIED_COMPLETE',port_released=True,baseline_restored=True,verified_trials=args.trials,report=receipt['proof'])
        print('MANAGED_FER_VERIFIED',run,flush=True)
    except BaseException as exc:
        if child is not None and child.poll() is None:child.terminate();child.wait(timeout=15)
        restored=False
        try:
            from uart_session import UARTSession
            with UARTSession(out/'error_baseline_restore',args.port):restored=True
        except BaseException as recovery_error:
            (out/'recovery_error.txt').write_text(repr(recovery_error))
        status('STOPPED_ERROR',port_released=restored,baseline_restored=restored,error=repr(exc));raise
if __name__=='__main__':main()
