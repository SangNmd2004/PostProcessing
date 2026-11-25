"""Seal only after every serial child has finished and baseline/port are verified free."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[2]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--stage',required=True,type=Path);args=ap.parse_args();stage=args.stage.resolve()
    out=ROOT/'build/zc702/research_finalizers'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out.mkdir(parents=True,exist_ok=False)
    while True:
        q05=json.loads((stage/'fer_q05_followup/STATUS.json').read_text());finite=json.loads((stage/'prospective_finite/STATUS.json').read_text())
        if q05['status'] in ['VERIFIED_COMPLETE','STOPPED_ERROR'] and finite['status'] in ['VERIFIED_COMPLETE','STOPPED_ERROR']:break
        time.sleep(5)
    with (out/'stdout.log').open('wb') as stdout,(out/'stderr.log').open('wb') as stderr:
        p=subprocess.run([sys.executable,'syn/zc702/finalize_research_execution.py','--stage',str(stage)],cwd=ROOT,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
    (out/'RESULT.json').write_text(json.dumps(dict(returncode=p.returncode,stage=stage.relative_to(ROOT).as_posix()),indent=2)+'\n')
    assert p.returncode==0,'Checkpoint sealing failed; see '+str(out)
    print('AUTONOMOUS_RESEARCH_SEALED',stage,flush=True)
if __name__=='__main__':main()
