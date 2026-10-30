"""Run declared board stages serially with per-stage receipts and resumable child datasets."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,subprocess,sys,time
from checkpoint_io import write_checkpoint
ROOT=Path(__file__).resolve().parents[2]
STAGES=[dict(id='paired_ablation_1000',kind='board_ablation',script='run_board_ablation.py',trials=1000,qber=.03,code='r23',seed=1800000),
        dict(id='fer_pilot_q01',kind='fer',script='run_fer_campaign.py',trials=1000,qber=.01,code='r34',seed=2100000),
        dict(id='fer_pilot_q02',kind='fer',script='run_fer_campaign.py',trials=1000,qber=.02,code='r34',seed=2200000),
        dict(id='fer_pilot_q05',kind='fer',script='run_fer_campaign.py',trials=1000,qber=.05,code='r12',seed=2500000),
        dict(id='fer_pilot_q07',kind='fer',script='run_fer_campaign.py',trials=1000,qber=.07,code='r12',seed=2700000),
        dict(id='fer_qualification_q02',kind='fer',script='run_fer_campaign.py',trials=10000,qber=.02,code='r34',seed=3200000)]
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--resume',type=Path);args=ap.parse_args()
def now():return datetime.now(timezone.utc).isoformat()
if args.resume:
    folder=args.resume.resolve();state=json.loads((folder/'result.json').read_text())
    assert state['plan']==STAGES
else:
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');folder=ROOT/'build/zc702/research_stages'/stamp;folder.mkdir(parents=True)
    state=dict(complete=False,started_utc=now(),plan=STAGES,stages=[],scope='synthetic BSC decoder experiments; tag and PA excluded')
    (folder/'frozen_plan.json').write_text(json.dumps({'stages':STAGES,'declared_before_measurements':now(),
       'stop_rule':'Fixed sample sizes. Stop on tool/transport/hardware mismatch; no accuracy-dependent early stopping.',
       'source_sha256':{s['script']:hashlib.sha256((ROOT/'syn/zc702'/s['script']).read_bytes()).hexdigest() for s in STAGES}},indent=2)+'\n')
    (folder/'runner_at_start.py').write_bytes(Path(__file__).read_bytes())
plan=json.loads((folder/'frozen_plan.json').read_text())
for script,h in plan['source_sha256'].items():assert hashlib.sha256((ROOT/'syn/zc702'/script).read_bytes()).hexdigest()==h,'runner changed'
def save():
    write_checkpoint(folder/'result.json',state)
def read_candidate(path,stage):
    try:r=json.loads((path/'result.json').read_text())
    except (OSError,json.JSONDecodeError):return None
    c=r['config'] if stage['kind']=='board_ablation' else r
    n=c['trials'] if stage['kind']=='board_ablation' else c['planned_trials']
    return r if (n,c['qber'],c['code'],c['seed_base'])==(stage['trials'],stage['qber'],stage['code'],stage['seed']) else None
def proof_for(run,stage):
    r=json.loads((run/'result.json').read_text());report=ROOT/'reports'/f"zc702_{stage['kind']}_{r['started_utc']}"
    p=report/'verified_evidence.json'
    if not p.exists():return None
    proof=json.loads(p.read_text())
    return report if r.get('complete') and proof.get('source_result_sha256')==hashlib.sha256((run/'result.json').read_bytes()).hexdigest() else None
child=None
try:
    if 'error' in state:
        state.setdefault('previous_controller_errors',[]).append(dict(error=state.pop('error'),stopped_utc=state.pop('stopped_utc',None)))
    save()
    for stage in STAGES:
        root=ROOT/'build/zc702'/f"{stage['kind']}_runs"
        candidates=[(p,read_candidate(p,stage)) for p in root.glob('*') if p.is_dir()]
        candidates=[(p,r) for p,r in candidates if r is not None]
        assert len(candidates)<=1,'multiple cohorts with identical stage seeds; resolve explicitly'
        existing=candidates[0][0] if candidates else None
        report=proof_for(existing,stage) if existing else None
        prior=next((x for x in state['stages'] if x['id']==stage['id']),None)
        if report:
            item=dict(id=stage['id'],status='VERIFIED_COMPLETE',run=str(existing.relative_to(ROOT)),report=str(report.relative_to(ROOT)),finished_utc=now())
            if prior:prior.update(item)
            else:state['stages'].append(item)
            save();continue
        argv=[sys.executable,str(ROOT/'syn/zc702'/stage['script']),'--trials',str(stage['trials']),
              '--qber',str(stage['qber']),'--code',stage['code'],'--seed-base',str(stage['seed'])]
        if existing:argv+=['--resume',str(existing)]
        item=prior or dict(id=stage['id']);item.update(status='RUNNING',started_utc=now())
        if not prior:state['stages'].append(item)
        stdout=folder/(stage['id']+'.stdout.log');stderr=folder/(stage['id']+'.stderr.log')
        with stdout.open('ab') as sout,stderr.open('ab') as serr:
            child=subprocess.Popen(argv,cwd=ROOT,stdout=sout,stderr=serr,creationflags=subprocess.CREATE_NO_WINDOW)
            item.update(pid=child.pid,stdout=str(stdout.relative_to(ROOT)),stderr=str(stderr.relative_to(ROOT)))
            save();print('RESEARCH_STAGE_STARTED',stage['id'],'PID',child.pid,flush=True)
            while child.poll() is None:
                for path in root.glob('*'):
                    r=read_candidate(path,stage)
                    if r:
                        item['run']=str(path.relative_to(ROOT))
                        item['verified_evaluations']=len(r['batches'])*4 if stage['kind']=='board_ablation' else len(r['records'])
                        item['planned_evaluations']=stage['trials']*(4 if stage['kind']=='board_ablation' else 1)
                        break
                job=dict(status='RUNNING',script='syn/zc702/run_research_stages.py',pid=os.getpid(),
                    plan_directory=str(folder.relative_to(ROOT)),active_stage=stage['id'],child_pid=child.pid,port='COM3',port_released=False,
                    stage_progress=item,started_utc=state['started_utc'])
                write_checkpoint(ROOT/'RUNNING_JOBS.json',job);save();time.sleep(2)
            assert child.returncode==0,f"{stage['id']} failed; see {stderr}"
        run=ROOT/item['run'];report=proof_for(run,stage);assert report,'postverification receipt missing'
        item.update(status='VERIFIED_COMPLETE',report=str(report.relative_to(ROOT)),finished_utc=now());save()
        print('RESEARCH_STAGE_VERIFIED',stage['id'],report,flush=True)
    state.update(complete=True,finished_utc=now());save()
    (ROOT/'RUNNING_JOBS.json').write_text(json.dumps(dict(status='VERIFIED_COMPLETE',script='syn/zc702/run_research_stages.py',
        plan_directory=str(folder.relative_to(ROOT)),pid=os.getpid(),port='COM3',port_released=True,report='reports/RESEARCH_STAGES_LATEST.json'),indent=2)+'\n')
    (ROOT/'reports/RESEARCH_STAGES_LATEST.json').write_text(json.dumps(state,indent=2)+'\n')
    print('ALL_DECLARED_RESEARCH_STAGES_PASS',folder,flush=True)
except BaseException as exc:
    if child is not None and child.poll() is None:child.terminate();child.wait(timeout=20)
    state.update(complete=False,error=repr(exc),stopped_utc=now());save()
    (ROOT/'RUNNING_JOBS.json').write_text(json.dumps(dict(status='STOPPED_ERROR',plan_directory=str(folder.relative_to(ROOT)),
        pid=os.getpid(),port='COM3',port_released=True,error=repr(exc)),indent=2)+'\n')
    raise
