"""Read-only board-evidence/checkpoint audit; never connects to COM3 or JTAG."""
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
import argparse
import csv
import hashlib
import json
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / 'build/zc702/research_stages/20261027T024200Z'
FOLLOW = ROOT / 'build/zc702/research_followups/20261027T032212Z'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    for attempt in range(20):
        try:
            data = path.read_bytes()
            return json.loads(data), data
        except (PermissionError, json.JSONDecodeError):
            if attempt == 19:
                raise
            time.sleep(.05)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    snapshot = out / 'checkpoint'
    snapshot.mkdir(exist_ok=True)
    checks = []

    def check(name, fn):
        try:
            detail = fn()
            checks.append(dict(check=name, status='PASS', detail=detail))
        except Exception as exc:
            checks.append(dict(check=name, status='FAIL', error=repr(exc)))

    state = {}
    def capture():
        for key, path in [('main', MAIN/'result.json'), ('follow', FOLLOW/'result.json'),
                          ('jobs', ROOT/'RUNNING_JOBS.json'), ('follow_jobs', ROOT/'FOLLOWUP_JOBS.json')]:
            value, raw = read_json(path)
            state[key] = value
            (snapshot / f'{key}.json').write_bytes(raw)
        return 'Four separately timestamped live-state snapshots; not a global atomic snapshot'
    check('capture_live_controller_state', capture)

    def hardware():
        expected = {'qkd_zc702.bit':'0e98876a2f884e19a69b3ced2d58109845520961a2112f2b698306f07db49f19',
                    'qkd_zc702.xsa':'15e15d7c1e4a89ba344a207ef4bc12895ebff4a03061c60440aab79ad1a6b665'}
        for file, sha in expected.items():
            assert digest(ROOT/'build/zc702'/file) == sha, file
        manifest, raw = read_json(ROOT/'build/zc702/uart_firmware/manifest.json')
        for file, sha in manifest['files'].items():
            assert digest(ROOT/file) == sha, file
        (snapshot/'firmware_manifest.json').write_bytes(raw)
        return dict(baseline_clock_mhz=50, firmware_files_verified=len(manifest['files']),
                    physical_board_rerun=False)
    check('baseline_bit_xsa_firmware_hashes', hardware)

    def guards():
        frozen, raw = read_json(MAIN/'frozen_plan.json')
        (snapshot/'main_frozen_plan.json').write_bytes(raw)
        assert state['main']['plan'] == frozen['stages']
        for name, sha in frozen['source_sha256'].items():
            assert digest(ROOT/'syn/zc702'/name) == sha, name
        follow = state['follow']
        for name, sha in follow['sources'].items():
            assert digest(ROOT/'syn/zc702'/name) == sha, name
        assert digest(ROOT/'model/zc702_resource_model.py') == follow['model_sha256']
        return dict(main_plan_and_leaf_sources_unchanged=True, followup_sources_and_model_unchanged=True)
    check('frozen_plan_and_source_guards', guards)

    def proofs():
        verified = []
        for kind in ['fer', 'board_ablation', 'wrong_codeword', 'schedule_validation']:
            for path in sorted((ROOT/'reports').glob(f'zc702_{kind}_*/verified_evidence.json')):
                run_id = path.parent.name.removeprefix(f'zc702_{kind}_')
                raw = ROOT/f'build/zc702/{kind}_runs'/run_id/'result.json'
                proof = json.loads(path.read_text())
                result, data = read_json(raw)
                assert result.get('complete'), str(raw)
                assert proof['source_result_sha256'] == hashlib.sha256(data).hexdigest(), str(path)
                verified.append(dict(kind=kind, run_id=run_id, raw_sha256=proof['source_result_sha256']))
        assert any(x['run_id']=='20261026T160934Z' for x in verified)
        assert any(x['run_id']=='20261027T024201Z' for x in verified)
        return verified
    check('completed_research_raw_proof_hashes', proofs)

    def journal():
        path = ROOT/'build/zc702/fer_runs/20261027T032458Z'
        value, data = read_json(path/'result.json')
        rows = value['records']
        n = len(rows)
        assert n % 4 == 0 and n <= 10000
        assert (value['qber'], value['code'], value['planned_trials'], value['seed_base']) == (.02,'r34',10000,3200000)
        assert [r['trial_id'] for r in rows] == list(range(n))
        assert [r['seed'] for r in rows] == list(range(3200000,3200000+n))
        assert all(r['hardware_match'] for r in rows)
        lines = (path/'verified_batches.jsonl').read_bytes().splitlines(keepends=True)
        assert len(lines) >= n//4
        prefix = lines[:n//4]
        recovered = [r for line in prefix for r in json.loads(line)]
        assert recovered == rows
        for file, sha in value['model_sha256'].items():
            assert digest(ROOT/file) == sha, file
        closed=sessions=[Path(p) for p in value['attempt_sessions']]
        if not value['complete']:closed=sessions[:-1]
        recoveries=[]
        for index,session in enumerate(closed):
            manifest=session/'tx_manifest.json'
            assert manifest.exists(), f'Closed session manifest missing: {session}'
            for packet in json.loads(manifest.read_text()):
                assert digest(session/packet['file'])==packet['sha256']
            recovery=session/'MANIFEST_RECOVERY.json'
            if recovery.exists():
                receipt=json.loads(recovery.read_text())
                assert digest(manifest)==receipt['recovered_manifest_sha256']
                assert digest(session/'uart.log')==receipt['source_uart_sha256']
                assert digest(session/'xsct.log')==receipt['source_xsct_sha256']
                (snapshot/f'closed_session_{index}_MANIFEST_RECOVERY.json').write_bytes(recovery.read_bytes())
                (snapshot/f'closed_session_{index}_tx_manifest.json').write_bytes(manifest.read_bytes())
                recoveries.append(receipt)
        (snapshot/'fer_result_partial_or_complete.json').write_bytes(data)
        (snapshot/'fer_journal_verified_prefix.jsonl').write_bytes(b''.join(prefix))
        return dict(records=n, planned=10000, complete=value['complete'],
                    unique_seeds=True, contiguous_trial_ids=True, journal_prefix_matches=True,
                    independent_raw_postverification='PENDING_UNTIL_CAMPAIGN_COMPLETE' if not value['complete'] else 'SEE_COMPLETED_PROOF_CHECK',
                    closed_sessions_with_manifests=len(closed),manifest_recoveries=recoveries,
                    outcomes=dict(Counter(r['outcome'] for r in rows)),
                    raw_result_sha256=hashlib.sha256(data).hexdigest(),
                    journal_scope='Only prefix covered by captured result; live tail deliberately excluded')
    check('active_fer_seed_records_journal', journal)

    def progress():
        with (ROOT/'reports/zc702_work_items.csv').open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        expected = {f'{p}{i:02d}' for p,n in [('F',12),('P',8),('PUB',8),('R',7)] for i in range(1,n+1)}
        assert len(rows)==35 and {r['id'] for r in rows}==expected
        with (ROOT/'reports/zc702_claim_evidence.csv').open(encoding='utf-8-sig', newline='') as f:
            claims={r['claim_id']:r for r in csv.DictReader(f)}
        assert claims['C09']['status']=='NOT_ACHIEVED'
        assert claims['C10']['status']=='MEASURED_PAIRED_BOARD_ABLATION'
        assert claims['C12']['status']=='NOT_SUPPORTED'
        assert claims['C13']['status']=='NOT_IMPLEMENTED'
        assert claims['C06']['status']=='NOT_YET_DEMONSTRATED'
        planned_missing=[]
        for row in rows:
            for file in row['target_deliverable'].split(';'):
                if not (ROOT/file.strip()).exists():
                    assert row['status']!='PASS_FUNCTIONAL_BOARD', (row['id'],file)
                    planned_missing.append(dict(id=row['id'],status=row['status'],planned_target=file.strip(),
                                                counts_as_evidence=False))
        return dict(total=len(rows), status_counts=dict(Counter(r['status'] for r in rows)),
                    core_claim_boundaries_preserved=True,uncreated_planned_targets=planned_missing)
    check('work_item_ids_paths_and_claim_boundaries', progress)

    def processes():
        cmd="Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | Select-Object ProcessId,CreationDate,CommandLine | ConvertTo-Json -Compress"
        p=subprocess.run(['powershell.exe','-NoProfile','-Command',cmd],capture_output=True,text=True,check=True,
                         creationflags=subprocess.CREATE_NO_WINDOW)
        entries=json.loads(p.stdout or '[]')
        if isinstance(entries,dict):entries=[entries]
        by_id={r['ProcessId']:r for r in entries}
        job=state['jobs'];follow=state['follow_jobs'];verified=[]
        if job['status']=='RUNNING':
            assert job['pid'] in by_id, 'running owner is absent'
            expected_script=job.get('script','').replace('syn/zc702/','')
            assert expected_script and expected_script in by_id[job['pid']]['CommandLine']
            child=job.get('child_pid')
            if child:
                assert child in by_id, 'running child is absent'
                assert str(ROOT).lower() in by_id[child]['CommandLine'].lower()
                verified.append(by_id[child])
            verified.append(by_id[job['pid']])
        if follow['status']=='WAITING_FOR_UPSTREAM':
            assert not follow['owns_COM3']
            assert follow['pid'] in by_id and 'run_research_followups.py' in by_id[follow['pid']]['CommandLine']
            verified.append(by_id[follow['pid']])
        assert not state['main'].get('error'), state['main'].get('error')
        assert not state['follow'].get('error'), state['follow'].get('error')
        return dict(process_identity_receipts=verified,
                    scope='CIM process identity and controller declarations; not an OS handle-level exclusive-port audit')
    check('live_process_identity_and_no_current_controller_error', processes)

    result=dict(verified_at=datetime.now(timezone(timedelta(hours=7))).isoformat(),
                overall='PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL', checks=checks,
                scope='Checkpoint/integrity/progress audit only; no new hardware run and no protocol-security certification')
    (out/'AUDIT.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=['# Kiểm chứng checkpoint bàn giao','',result['verified_at'],'',
           f'Kết quả: **{result["overall"]}**. Chỉ kiểm tra checkpoint/integrity/progress; không chạy lại board.', '',
           '| Kiểm tra | Kết quả |', '|---|---|']
    lines += [f'| {c["check"]} | {c["status"]} |' for c in checks]
    for c in checks:
        if c['status']=='FAIL':lines += ['',f'`{c["check"]}`: `{c["error"]}`']
    lines += ['','Chi tiết, số record và hash: [AUDIT.json](AUDIT.json). '
              'Checkpoint là snapshot, không được gọi dữ liệu partial là campaign hoàn tất. '
              'Đọc RUNNING_JOBS/FOLLOWUP_JOBS và kiểm tra process lại trước khi dùng COM3.','']
    (out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print('HANDOFF_AUDIT',result['overall'],str(out),flush=True)
    raise SystemExit(0 if result['overall']=='PASS' else 1)


if __name__=='__main__':
    main()
