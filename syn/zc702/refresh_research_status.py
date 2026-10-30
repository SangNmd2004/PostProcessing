"""Refresh research tables from complete, hash-matched raw evidence only."""
from pathlib import Path
import csv
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'reports'


def latest_verified(kind):
    found = None
    for proof_path in sorted(OUT.glob(f'zc702_{kind}_*/verified_evidence.json')):
        run_id = proof_path.parent.name.removeprefix(f'zc702_{kind}_')
        raw = ROOT / f'build/zc702/{kind}_runs' / run_id / 'result.json'
        if not raw.exists():
            continue
        raw_data = raw.read_bytes()
        proof = json.loads(proof_path.read_text())
        if (json.loads(raw_data).get('complete') and proof.get('raw_replay_verified') and
                proof.get('source_result_sha256') == hashlib.sha256(raw_data).hexdigest()):
            found = (proof_path.parent.relative_to(ROOT).as_posix() + '/REPORT.md', proof)
    return found


def main():
    for script in ('export_fer_catalog.py', 'prepare_research_tasks.py'):
        subprocess.run([sys.executable, str(ROOT / 'syn/zc702' / script)], cwd=ROOT, check=True)
    path = OUT / 'zc702_claim_evidence.csv'
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    ablation = latest_verified('board_ablation')
    schedule = latest_verified('schedule_validation')
    wrong = latest_verified('wrong_codeword')
    for row in rows:
        if row['claim_id'] == 'C10' and ablation:
            row.update(status='MEASURED_PAIRED_BOARD_ABLATION', evidence=ablation[0],
                       limitation='1000 paired BSC q=3% inputs x4 configurations; one wrong codeword shared by three GS configurations; no tag/PA in ablation',
                       permitted_statement_or_next_gate='GS and NMS reduce paired attempts/f on this workload; ET/PP tradeoff measured jointly; no significant FER improvement claim; dynamic/switch/context factors pending')
        if row['claim_id'] == 'C08':
            row['limitation'] = 'Qualification-size and pilot cohorts listed separately; no tag/PA; QBER 7% pilot FER=0.005; no all-QBER FER claim'
        if row['claim_id'] == 'C05' and schedule:
            report, proof = schedule
            accepted = proof['latency_model_accepted']
            row.update(status='VALIDATED_SCOPED_HELD_OUT' if accepted else 'HELD_OUT_MODEL_NOT_ACCEPTED', evidence=report,
                       limitation='ET=PP=0, four selected repeated vectors; trace known from golden; DDR IR only; no production arrival/tag/PA',
                       permitted_statement_or_next_gate=f'Mean abs relative-to-prediction error {proof["mean_absolute_error_pct"]:.6g}%; max {proof["max_absolute_error_pct"]:.6g}%; accepted={accepted}; do not fit again on this held-out set')
    if wrong:
        item = dict(claim_id='C17', claim='Natural wrong codeword rejected by genuine Alice tag at both entry points',
                    status='PASS_ONE_NATURAL_WRONG_KEY_FIXTURE', evidence=wrong[0],
                    limitation='One public BSC fixture, op20/op60; not independent FER samples or whole-protocol security proof',
                    permitted_statement_or_next_gate='Actual DMA KEY differs by 11 bits; both paths withhold output/append and charge verification budget; retain NOT_TESTED tag labels on FER cohorts')
        previous = next((row for row in rows if row['claim_id'] == 'C17'), None)
        if previous is None:
            rows.append(item)
        else:
            previous.update(item)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    subprocess.run([sys.executable, str(ROOT / 'syn/zc702/report_project_progress.py')], cwd=ROOT, check=True)
    print('RESEARCH_STATUS_REFRESHED', flush=True)


if __name__ == '__main__':
    main()
