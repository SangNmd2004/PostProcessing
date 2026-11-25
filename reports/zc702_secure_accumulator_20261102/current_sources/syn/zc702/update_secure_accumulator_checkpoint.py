"""Targeted evidence guard; preserve all canonical work IDs, names and statuses."""
from pathlib import Path
import csv,hashlib,json
ROOT=Path(__file__).resolve().parents[2]
STAGE=ROOT/'reports/zc702_secure_accumulator_20261102'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    proof_path=STAGE/'board_verification_attempt2/verified_evidence.json';proof=json.loads(proof_path.read_text())
    run=ROOT/'build/zc702/secure_accumulator_runs/20261102T045046Z';raw=json.loads((run/'result.json').read_text())
    assert raw['complete'] and proof['raw_replay_verified'] and proof['baseline_restored']
    assert proof['source_result_sha256']==sha(run/'result.json') and proof['uart_sha256']==sha(run/'uart.log') and proof['tx_sha256']==sha(run/'tx.jsonl')
    for n,h in raw['build_manifest']['source_sha256'].items():assert sha(ROOT/n)==h,n
    for n,h in raw['baseline_manifest']['files'].items():assert sha(ROOT/n)==h,n
    job=json.loads((ROOT/'RUNNING_JOBS.json').read_text());assert job['status']=='VERIFIED_COMPLETE' and job['port_released'] and job['baseline_restored']
    path=ROOT/'reports/zc702_work_items.csv'
    with path.open(encoding='utf-8-sig',newline='') as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
    before=[(r['id'],r['title'],r['status']) for r in rows];assert len(before)==35
    for r in rows:
        if r['id']=='P04':
            assert r['status']=='PARTIAL'
            r['target_deliverable']='reports/zc702_secure_accumulator_20261102/REPORT.md; reports/zc702_secure_app_20261027/REPORT.md'
            r['limitation']='Raw-replay-verified QAS2 accumulator lab ELF: 172 repeated public r56 appends, normal/split PA, bound synthetic metadata; public trust/reset/G/debug controls; no production or durable security claim'
            r['next_action']='Keep bounded recovery/four-code coverage backlog; finish PE/leak and measured research pipeline before production trust/storage work'
        if r['id']=='PUB04':
            assert r['status']=='PARTIAL'
            r['target_deliverable']='reports/zc702_secure_accumulator_20261102/REPORT.md; reports/zc702_verification_budget_20261027T021157Z/REPORT.md'
            r['limitation']='Shared boot-lifetime cap reaches 175/175 after authenticated lowering; session resets do not refund it; reboot accounting and composable session security remain unproved'
    assert before==[(r['id'],r['title'],r['status']) for r in rows]
    with path.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    claims=ROOT/'reports/zc702_claim_evidence.csv'
    with claims.open(encoding='utf-8-sig',newline='') as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
    assert not any(r['claim_id']=='C18' for r in rows),'Do not rewrite a sealed update'
    rows.append(dict(claim_id='C18',claim='QAS2 gates bound verified accumulator append and normal/split PA',status='PASS_SCOPED_PUBLIC_FIXTURE_BOARD',evidence='reports/zc702_secure_accumulator_20261102/REPORT.md',limitation='Repeated r56/synthetic counts; lab root/reset/G/debug KEY; no production, reboot persistence or independent FER claim',permitted_statement_or_next_gate='888 raw commands; 172 verified appends; 37568/115968 output bits match independent PA; keep P04/PUB04 PARTIAL'))
    with claims.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    (STAGE/'UPDATE_GUARD.json').write_text(json.dumps(dict(raw_replay_verified=True,source_result_sha256=proof['source_result_sha256'],canonical_identifiers_titles_statuses_preserved=before),indent=2)+'\n')
    print('TARGETED_UPDATE_GUARD_PASS 35 unchanged IDs/titles/statuses')
if __name__=='__main__':main()
