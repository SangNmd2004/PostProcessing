"""Catalog completed, postverified FER cohorts separately; never pool duplicated seeds or regimes."""
from pathlib import Path
import csv,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
from experiment_metrics import wilson_interval
rows=[];incomplete=[]
for run in sorted((ROOT/'build/zc702/fer_runs').glob('*')):
    path=run/'result.json'
    if not path.exists():continue
    try:r=json.loads(path.read_text())
    except json.JSONDecodeError:continue
    proof_path=ROOT/'reports'/('zc702_fer_'+r['started_utc'])/'verified_evidence.json'
    if not r.get('complete') or not proof_path.exists():
        incomplete.append(dict(run=run.relative_to(ROOT).as_posix(),verified_records=len(r['records']),planned=r['planned_trials'],error=r.get('error','')));continue
    proof=json.loads(proof_path.read_text())
    if proof.get('source_result_sha256')!=hashlib.sha256(path.read_bytes()).hexdigest():
        incomplete.append(dict(run=run.relative_to(ROOT).as_posix(),verified_records=len(r['records']),planned=r['planned_trials'],error='result SHA differs from postverification proof'));continue
    n=len(r['records']);discard=sum(x['outcome']=='DISCARD' for x in r['records']);wrong=sum(x['outcome']=='WRONG_CODEWORD' for x in r['records'])
    assert n==r['planned_trials'] and len({x['trial_id'] for x in r['records']})==n
    interval=wilson_interval(discard+wrong,n)
    firmware=[]
    for name in r['attempt_sessions']:
        mf=Path(name)/'firmware_manifest.json'
        if mf.exists():
            for file,h in json.loads(mf.read_text())['files'].items():
                if file.endswith('qkd_uart.elf'):firmware.append(h)
    rows.append(dict(run_id=r['started_utc'],qber=r['qber'],code=r['code'],cn=r['cn'],puncturing=r['puncturing'],n=n,
        success=n-discard-wrong,discard=discard,wrong_codeword=wrong,FER=(discard+wrong)/n,
        Wilson95_low=interval[0],Wilson95_high=interval[1],seed_start=r['seed_base'],seed_stop_exclusive=r['seed_base']+n,
        role='qualification_sample_size' if n>=10000 else 'pilot' if n>=1000 else 'bringup_or_resume_check',
        tag_PA_applied=False,previous_session_errors=len(r.get('previous_session_errors',[])),
        firmware_elf_SHA256=';'.join(sorted(set(firmware))),
        raw_result=path.relative_to(ROOT).as_posix(),report=proof_path.with_name('REPORT.md').relative_to(ROOT).as_posix(),
        source_result_sha256=proof['source_result_sha256']))
def write(path,values):
    if not values:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(values[0]));w.writeheader();w.writerows(values)
out=ROOT/'reports';write(out/'FER_CATALOG.csv',rows)
write(out/'FER_INCOMPLETE_RUNS.csv',incomplete)
overlaps=[]
for i,a in enumerate(rows):
    for b in rows[i+1:]:
        if (a['qber'],a['code'],a['cn'],a['puncturing'])==(b['qber'],b['code'],b['cn'],b['puncturing']):
            if max(a['seed_start'],b['seed_start'])<min(a['seed_stop_exclusive'],b['seed_stop_exclusive']):overlaps.append([a['run_id'],b['run_id']])
summary={'complete_postverified_cohorts':len(rows),'qualification_size_cohorts':sum(r['n']>=10000 for r in rows),
         'incomplete_or_not_postverified':len(incomplete),'overlapping_seed_ranges_same_stratum':overlaps,
         'no_automatic_pooling':True,'runs':rows}
(out/'FER_CATALOG.json').write_text(json.dumps(summary,indent=2)+'\n')
text=['# Danh mục FER được kiểm chứng trên ZC702','',
      'Mỗi dòng là một cohort đã complete và proof SHA khớp raw result. Không tự cộng pilot/qualification hoặc các cấu hình trên cùng input. '
      'Các khoảng Wilson95 là pointwise; đủ 10.000 mẫu không đồng nghĩa tự đạt FER mục tiêu. Tag/PA không chạy trong các phép đo decoder này.','',
      '| QBER % | Code | n | Success | Discard | Wrong | FER % | Wilson95 % | Vai trò | Báo cáo |',
      '|---:|---|---:|---:|---:|---:|---:|---|---|---|']
for r in rows:
    link=Path(r['report']).relative_to('reports').as_posix()
    text.append(f"| {r['qber']*100:g} | {r['code']} | {r['n']} | {r['success']} | {r['discard']} | {r['wrong_codeword']} | {r['FER']*100:.5f} | [{r['Wilson95_low']*100:.5f}, {r['Wilson95_high']*100:.5f}] | {r['role']} | [{r['run_id']}]({link}) |")
text+=['',f'Cohort complete/postverified: {len(rows)}; cohort n≥10.000: {summary["qualification_size_cohorts"]}; '
       f'run incomplete hoặc chưa postverify: {len(incomplete)}. Ranges seed trùng trong cùng stratum: {overlaps}.','',
       'Một wrong codeword là hội tụ khác Alice theo ground truth. Nó không tự được gọi là lỗi tag đã bắt; '
       'ca verification thật trên wrong-key fixture có báo cáo riêng nếu đã chạy. '
       'Bring-up/resume cohorts nhỏ giữ để kiểm toán, không dùng để khẳng định FER≈10⁻³.','']
(out/'FER_CATALOG.md').write_text('\n'.join(text),encoding='utf-8')
print('FER_CATALOG_EXPORTED',len(rows),'complete cohorts',summary['qualification_size_cohorts'],'n>=10000',flush=True)
