"""Run original raw verifiers with only report destinations redirected here."""
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
if len(sys.argv)>1 and sys.argv[1]=='--child':
    name,kind,run=sys.argv[2:5];original=ROOT/'syn/zc702'/name
    source=original.read_text(encoding='utf-8')
    # Suppress the original completion hook which edits the canonical tracker.
    if name=='verify_experiment_run.py':
        marker="if args.kind=='fer' and len(result['records'])>=10000:"
        assert source.count(marker)==1
        source=source.replace(marker,'if False: # Review: canonical tracker writes disabled')
    import re
    source,n=re.subn(r"out=ROOT/'reports'/[^;\n]+", lambda _: "out=Path("+repr((OUT/kind).as_posix())+ ")",source)
    assert n>=1
    sys.argv=[str(original)]+(['fer'] if name=='verify_experiment_run.py' else [])+[str(ROOT/run)]
    exec(compile(source,str(original),'exec'),{'__name__':'__main__','__file__':str(original)})
else:
    cases=[('verify_experiment_run.py','fer_q02','build/zc702/fer_runs/20261027T032458Z'),
           ('report_wrong_codeword_test.py','wrong_codeword','build/zc702/wrong_codeword_runs/20261027T044256Z'),
           ('report_schedule_validation.py','schedule','build/zc702/schedule_validation_runs/20261027T044317Z')]
    records=[]
    for name,kind,run in cases:
        p=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',name,kind,run],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
        (OUT/(kind+'.stdout.log')).write_text(p.stdout,encoding='utf-8')
        (OUT/(kind+'.stderr.log')).write_text(p.stderr,encoding='utf-8')
        records.append(dict(verifier=name,verifier_sha256=hashlib.sha256((ROOT/'syn/zc702'/name).read_bytes()).hexdigest(),
                            run=run,returncode=p.returncode,scope='Original checks; output redirected; tracker completion hook disabled'))
        print(kind,p.returncode,flush=True)
    (OUT/'RAW_REPLAY_RECEIPT.json').write_text(json.dumps(records,indent=2)+'\n')
    raise SystemExit(0 if all(r['returncode']==0 for r in records) else 1)
