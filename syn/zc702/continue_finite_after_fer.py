"""After the serial paced/FER sequence, prepare/freeze and capture one new finite-key source."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,subprocess,sys,time
import serial
from checkpoint_io import write_checkpoint
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
from finite_key_accumulation_model import events_from_board_run,replay_events
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--stage',required=True,type=Path);ap.add_argument('--resume-wait',action='store_true');args=ap.parse_args();stage=args.stage.resolve();out=stage/'prospective_finite'
    if args.resume_wait:
        previous=json.loads((out/'STATUS.json').read_text());assert previous['status']=='WAITING_FOR_SERIAL_FER_SEQUENCE' and not previous['steps'] and not previous.get('run')
        (out/'WAIT_RESTART_BEFORE.json').write_text(json.dumps(previous,indent=2)+'\n')
    else:out.mkdir(parents=True,exist_ok=False)
    (out/'watcher_at_start.py').write_bytes(Path(__file__).read_bytes())
    own=dict(status='WAITING_FOR_SERIAL_FER_SEQUENCE',complete=False,steps=[]);active=None;run=None
    def save():write_checkpoint(out/'STATUS.json',own)
    def status(s,**kw):write_checkpoint(ROOT/'RUNNING_JOBS.json',dict(status=s,pid=os.getpid(),script='syn/zc702/continue_finite_after_fer.py',stage=stage.relative_to(ROOT).as_posix(),port='COM3',run_directory=run.relative_to(ROOT).as_posix() if run else own.get('run'),**kw))
    def command(label,argv):
        nonlocal active
        own['status']=label;own['steps'].append(dict(label=label,command=argv));save();print('FINITE_FOLLOWUP_STEP',label,flush=True)
        with (out/(label+'.stdout.log')).open('wb') as stdout,(out/(label+'.stderr.log')).open('wb') as stderr:
            active=subprocess.Popen(argv,cwd=ROOT,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
            while active.poll() is None:
                if label=='board_capture':
                    candidates=[]
                    for folder in (ROOT/'build/zc702/key_stream_runs').iterdir():
                        p=folder/'result.json'
                        if not p.exists():continue
                        try:r=json.loads(p.read_text())
                        except (OSError,json.JSONDecodeError):continue
                        source=r.get('sources',{}).get('weak',{}).get('path')
                        if source and Path(source).resolve()==(out/'source/session_weak.npz').resolve():candidates.append((folder,r))
                    assert len(candidates)<=1
                    if candidates:
                        nonlocal_run,r=candidates[0];own['run']=nonlocal_run.relative_to(ROOT).as_posix();save()
                        status('RUNNING',port_released=False,captured_source_blocks=len(r['records']),frozen_prediction=own['frozen_prediction'])
                time.sleep(5)
        assert active.returncode==0,label
    save()
    try:
        while True:
            state=json.loads((stage/'paced_sequence/SEQUENCE_STATUS.json').read_text())
            if state.get('error'):raise RuntimeError('Preceding serial sequence failed; preserve independent evidence')
            if state.get('complete'):break
            time.sleep(5)
        job=json.loads((ROOT/'RUNNING_JOBS.json').read_text());assert job['status']=='VERIFIED_COMPLETE' and job['port_released']
        status('RUNNING_HOST',port_released=True,baseline_restored=True,phase='new_synthetic_source_and_predictions')
        command('prepare_and_freeze',[sys.executable,'syn/zc702/prepare_finite_source.py','--output',str(out/'source'),'--seed','2026110220'])
        frozen=out/'source/frozen_prediction.json';plan=json.loads(frozen.read_text());own['frozen_prediction']=frozen.relative_to(ROOT).as_posix();own['frozen_prediction_sha256']=sha(frozen);own['capture_start_monotonic_ns']=time.perf_counter_ns();save()
        assert plan['freeze_monotonic_ns']<own['capture_start_monotonic_ns']
        status('RUNNING',port_released=False,phase='new_source_finite_key_capture',frozen_prediction=own['frozen_prediction'])
        command('board_capture',[sys.executable,'syn/zc702/run_key_stream.py','--scenario','emit','--source-dir',str(out/'source')]);run=ROOT/own['run']
        status('COMPLETED_PENDING_RAW_VERIFICATION',port_released=True,baseline_restored=True)
        command('independent_raw_verify',[sys.executable,'syn/zc702/report_key_stream.py',str(run)])
        result=json.loads((run/'result.json').read_text());proof_path=ROOT/'reports'/('zc702_key_stream_'+result['started_utc'])/'verified_evidence.json';proof=json.loads(proof_path.read_text())
        assert result['complete'] and proof['raw_replay_verified'] and proof['source_hashes']['result.json']==sha(run/'result.json')
        assert result['sources']['weak']['sha256']==plan['source_sha256'] and sha(frozen)==own['frozen_prediction_sha256']
        actual=[e['reported'] for e in events_from_board_run(run) if e['kind']=='DECIDE'];assert len(actual)==len(plan['decisions'])
        for expected,observed in zip(plan['decisions'],actual):
            for field in ['action','bits','ell','split','emit_bits']:assert expected[field]==observed[field],field
        actual_records={r['source_block']:r for r in result['records'] if r['source_block']!=0}
        for expected in plan['records']:
            observed=actual_records[expected['source_block']];assert expected['outcome']==observed['outcome']
            for field in ['nk','nt','mt','test_start','test_stop']:assert expected[field]==observed[field]
            if observed['added']:assert expected['leak']==observed['leak'] and expected['attempts']==len(observed['attempts'])
        assert plan['expected_verified_blocks']==result['verified_blocks']
        model_rows=replay_events(events_from_board_run(run));assert all(row.get('all_fields_match',True) for row in model_rows)
        baseline=json.loads((ROOT/'build/zc702/uart_firmware/manifest.json').read_text())
        for n,h in baseline['files'].items():assert sha(ROOT/n)==h,n
        with serial.Serial('COM3',115200,timeout=.1):pass
        own.update(status='VERIFIED_COMPLETE',complete=True,run=run.relative_to(ROOT).as_posix(),proof=proof_path.relative_to(ROOT).as_posix(),decisions_verified=len(actual),verified_blocks=result['verified_blocks'],
            emissions=proof['emissions'],frozen_before_capture=True,baseline_restored=True,port_released=True,source_result_sha256=sha(run/'result.json'),
            scope=plan['scope'],time_contract=plan['time_contract']);save()
        status('VERIFIED_COMPLETE',port_released=True,baseline_restored=True,report=(out/'STATUS.json').relative_to(ROOT).as_posix());print('NEW_FINITE_SOURCE_PROSPECTIVE_FUNCTIONAL_PASS',out,flush=True)
    except BaseException as exc:
        own.update(status='STOPPED_ERROR',error=repr(exc));save()
        if active is not None and active.poll() is None:active.terminate();active.wait(timeout=15)
        if own['steps']:
            restored=False
            try:
                from uart_session import UARTSession
                with UARTSession(out/'error_baseline_restore','COM3'):restored=True
            except BaseException as recovery_error:own['recovery_error']=repr(recovery_error);save()
            status('STOPPED_ERROR',port_released=restored,baseline_restored=restored,error=repr(exc))
        raise
if __name__=='__main__':main()
