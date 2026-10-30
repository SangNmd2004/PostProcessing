"""Wait for the serial FER plan, then test the natural wrong key and held-out scheduling model."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,re,subprocess,sys,time
from checkpoint_io import write_checkpoint
ROOT=Path(__file__).resolve().parents[2]
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--research-plan',type=Path,required=True)
ap.add_argument('--ablation',type=Path,required=True);ap.add_argument('--resume',type=Path)
args=ap.parse_args();upstream=args.research_plan.resolve();ablation=args.ablation.resolve()
stages=[dict(id='natural_wrong_key_tag',script='run_wrong_codeword_test.py',kind='wrong_codeword',marker='WRONG_CODEWORD_EVIDENCE'),
        dict(id='held_out_schedule_model',script='run_schedule_validation.py',kind='schedule_validation',marker='SCHEDULE_VALIDATION_EVIDENCE')]
if args.resume:
    folder=args.resume.resolve();state=json.loads((folder/'result.json').read_text());assert state['plan']==stages
else:
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');folder=ROOT/'build/zc702/research_followups'/stamp;folder.mkdir(parents=True)
    state=dict(complete=False,plan=stages,stages=[],started_utc=datetime.now(timezone.utc).isoformat(),
               upstream=str(upstream.relative_to(ROOT)),ablation=str(ablation.relative_to(ROOT)),
               sources={s['script']:hashlib.sha256((ROOT/'syn/zc702'/s['script']).read_bytes()).hexdigest() for s in stages},
               model_sha256=hashlib.sha256((ROOT/'model/zc702_resource_model.py').read_bytes()).hexdigest())
    (folder/'frozen_plan.json').write_text(json.dumps(state,indent=2)+'\n')
    (folder/'runner_at_start.py').write_bytes(Path(__file__).read_bytes())
def save():
    write_checkpoint(folder/'result.json',state)
def verified(run,kind):
    r=json.loads((run/'result.json').read_text());out=ROOT/'reports'/f"zc702_{kind}_{r['started_utc']}"
    proof=out/'verified_evidence.json'
    return out if r.get('complete') and proof.exists() and json.loads(proof.read_text()).get('source_result_sha256')==hashlib.sha256((run/'result.json').read_bytes()).hexdigest() else None
child=None
try:
    if 'error' in state:state.setdefault('previous_controller_errors',[]).append(state.pop('error'))
    state['status']='WAITING_FOR_UPSTREAM';save()
    while True:
        parent=json.loads((upstream/'result.json').read_text())
        if parent.get('complete'):break
        if parent.get('error'):raise RuntimeError('Upstream stopped: '+parent['error'])
        (ROOT/'FOLLOWUP_JOBS.json').write_text(json.dumps(dict(status='WAITING_FOR_UPSTREAM',pid=os.getpid(),
           followup_directory=str(folder.relative_to(ROOT)),upstream=str(upstream.relative_to(ROOT)),owns_COM3=False),indent=2)+'\n')
        time.sleep(5)
    time.sleep(2) # upstream has closed its child COM handle before writing complete
    for stage in stages:
        assert hashlib.sha256((ROOT/'syn/zc702'/stage['script']).read_bytes()).hexdigest()==state['sources'][stage['script']]
        assert hashlib.sha256((ROOT/'model/zc702_resource_model.py').read_bytes()).hexdigest()==state['model_sha256']
        prior=next((r for r in state['stages'] if r['id']==stage['id']),None)
        if prior and prior.get('run') and verified(ROOT/prior['run'],stage['kind']):continue
        item=prior or dict(id=stage['id']);item.update(status='RUNNING')
        if not prior:state['stages'].append(item)
        stdout=folder/(stage['id']+'.stdout.log');stderr=folder/(stage['id']+'.stderr.log')
        with stdout.open('wb') as sout,stderr.open('wb') as serr:
            child=subprocess.Popen([sys.executable,'-u',str(ROOT/'syn/zc702'/stage['script']),'--ablation',str(ablation)],
                cwd=ROOT,stdout=sout,stderr=serr,creationflags=subprocess.CREATE_NO_WINDOW)
            item.update(pid=child.pid,stdout=str(stdout.relative_to(ROOT)),stderr=str(stderr.relative_to(ROOT)));save()
            print('FOLLOWUP_STARTED',stage['id'],'PID',child.pid,flush=True)
            while child.poll() is None:
                job=dict(status='RUNNING',script='syn/zc702/run_research_followups.py',pid=os.getpid(),child_pid=child.pid,
                         active_stage=stage['id'],followup_directory=str(folder.relative_to(ROOT)),port='COM3',port_released=False)
                write_checkpoint(ROOT/'RUNNING_JOBS.json',job);time.sleep(2)
            text=stdout.read_text(errors='replace');found=re.search(fr'^{stage["marker"]} (.+)$',text,re.MULTILINE)
            if found:item['run']=str(Path(found.group(1).strip()).relative_to(ROOT));save()
            assert child.returncode==0,f"Followup failed: {stage['id']}; see {stderr}"
        assert item.get('run');report=verified(ROOT/item['run'],stage['kind']);assert report
        item.update(status='VERIFIED_COMPLETE',report=str(report.relative_to(ROOT)),finished_utc=datetime.now(timezone.utc).isoformat());save()
        print('FOLLOWUP_VERIFIED',stage['id'],report,flush=True)
    state.update(complete=True,status='VERIFIED_COMPLETE',finished_utc=datetime.now(timezone.utc).isoformat());save()
    (ROOT/'reports/RESEARCH_FOLLOWUPS_LATEST.json').write_text(json.dumps(state,indent=2)+'\n')
    (ROOT/'FOLLOWUP_JOBS.json').write_text(json.dumps(dict(status='VERIFIED_COMPLETE',followup_directory=str(folder.relative_to(ROOT)),owns_COM3=False),indent=2)+'\n')
    (ROOT/'RUNNING_JOBS.json').write_text(json.dumps(dict(status='VERIFIED_COMPLETE',pid=os.getpid(),port='COM3',port_released=True,
        followup_directory=str(folder.relative_to(ROOT)),report='reports/RESEARCH_FOLLOWUPS_LATEST.json'),indent=2)+'\n')
    print('ALL_RESEARCH_FOLLOWUPS_VERIFIED',folder,flush=True)
except BaseException as exc:
    if child is not None and child.poll() is None:child.terminate();child.wait(timeout=20)
    state.update(complete=False,status='STOPPED_ERROR',error=repr(exc));save()
    (ROOT/'FOLLOWUP_JOBS.json').write_text(json.dumps(dict(status='STOPPED_ERROR',followup_directory=str(folder.relative_to(ROOT)),error=repr(exc),owns_COM3=False),indent=2)+'\n')
    raise
