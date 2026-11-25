"""Run verified paced gates serially, then one predeclared FER qualification."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,subprocess,sys,time
from checkpoint_io import write_checkpoint
ROOT=Path(__file__).resolve().parents[2]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--stage',required=True,type=Path);args=ap.parse_args();stage=args.stage.resolve();out=stage/'paced_sequence';out.mkdir(parents=True,exist_ok=False)
    state=dict(started_utc=datetime.now(timezone.utc).isoformat(),complete=False,steps=[]);active=None
    def save():write_checkpoint(out/'SEQUENCE_STATUS.json',state)
    def run(label,argv):
        nonlocal active
        step=dict(label=label,command=argv,status='RUNNING',started_utc=datetime.now(timezone.utc).isoformat());state['steps'].append(step);save();print('AUTONOMOUS_STEP',label,flush=True)
        with (out/(label+'.stdout.log')).open('wb') as stdout,(out/(label+'.stderr.log')).open('wb') as stderr:
            active=subprocess.Popen(argv,cwd=ROOT,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
            step['pid']=active.pid;save()
            while active.poll() is None:time.sleep(2)
        step.update(status='COMMAND_COMPLETED' if active.returncode==0 else 'FAILED',returncode=active.returncode,finished_utc=datetime.now(timezone.utc).isoformat());save();assert active.returncode==0,label
    def last_run():return ROOT/json.loads((ROOT/'RUNNING_JOBS.json').read_text())['run_directory']
    py=sys.executable;build='build/zc702/paced_test/20261102_safe_wave_v7';fixtures='build/zc702/paced_fixtures/20261102_training'
    try:
        run('paced_pilot',[py,'syn/zc702/run_paced_board.py','--build',build,'--fixtures',fixtures]);training=last_run();state['training_run']=training.relative_to(ROOT).as_posix();save()
        run('paced_pilot_verify',[py,'syn/zc702/verify_paced_board.py',str(training),'--output',str(out/'pilot_verified')])
        run('freeze_model',[py,'syn/zc702/freeze_paced_model.py',str(training),'--output',str(out/'frozen_model')])
        frozen=out/'frozen_model/frozen_validation.json'
        run('arrival_validation',[py,'syn/zc702/run_paced_board.py','--build',build,'--fixtures',fixtures,'--config',str(frozen)]);validation=last_run();state['validation_run']=validation.relative_to(ROOT).as_posix();save()
        run('arrival_raw_verify',[py,'syn/zc702/verify_paced_board.py',str(validation),'--output',str(out/'arrival_verified')])
        run('arrival_model_compare',[py,'syn/zc702/verify_paced_model.py',str(validation),'--frozen',str(frozen),'--output',str(out/'model_comparison')])
        run('fer_q01_qualification',[py,'syn/zc702/run_managed_fer.py','--trials','10000','--qber','.01','--code','r34','--seed-base','4100000']);state['fer_run']=last_run().relative_to(ROOT).as_posix()
        state['complete']=True
    except BaseException as exc:
        state['error']=repr(exc)
        if active is not None and active.poll() is None:active.terminate();active.wait(timeout=15)
        raise
    finally:
        save();print('AUTONOMOUS_SEQUENCE_EVIDENCE',out,flush=True)
if __name__=='__main__':main()
