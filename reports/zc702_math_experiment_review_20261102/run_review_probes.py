"""Read-only model review; output stays here. No serial/JTAG or report generators."""
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'model'))
import finite_key_accumulation_model as fm
import verification_budget_model as vb
from pa_accum import PAAccumulator

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    commands=[]
    for name in ['zc702_resource_model.py','efficiency_throughput_crossover.py']:
        argv=[sys.executable,str(ROOT/'model'/name)];p=subprocess.run(argv,capture_output=True,text=True)
        commands.append(dict(command=argv,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));assert p.returncode==0
    records=[dict(nk=[2570,190,5],nt=[2607,135,4],mt=[0,0,0] if i<90 else [1300,100,3],leak=269,replay_time_seconds=i) for i in range(92)]
    observed=fm.simulate_accumulation_trajectory(records,[.6,.2,0],[.75,.125,.125])
    ref=PAAccumulator([.6,.2,0],[.75,.125,.125]);expected=[]
    for rec in records:
        ref.add(rec['nk'],rec['nt'],rec['mt'],rec['leak'],rec['replay_time_seconds'])
        action,_,_,_=ref.decide(rec['replay_time_seconds']);expected.append(dict(bits=ref.n,action=action,split=ref._split,emit_n=ref.emit_n))
        if action=='emit':ref.emitted()
        elif action=='abort':ref.reset()
    assert observed[-1]['bits']==2765 and expected[-1]['bits']==5530
    pins=['MO_HINH_TOAN_HOC_VA_KE_HOACH_THUC_NGHIEM.md','reports/publication_plan_20261026/EXPERIMENT_PLAN.md',
          'reports/publication_plan_20261026/CROSSOVER_MODEL_SPEC.md','reports/publication_plan_20261026/RESOURCE_MODEL_DERIVATION.md',
          'model/finite_key_accumulation_model.py','model/verification_budget_model.py','model/efficiency_throughput_crossover.py',
          'model/zc702_resource_model.py','model/pa_model.py','reports/zc702_work_items.csv','reports/RECONCILIATION_CURRENT.json','RUNNING_JOBS.json']
    verified=[]
    for report,raw in [('reports/zc702_schedule_validation_20261027T044317Z/verified_evidence.json','build/zc702/schedule_validation_runs/20261027T044317Z/result.json'),
                       ('reports/zc702_board_ablation_20261027T024201Z/verified_evidence.json','build/zc702/board_ablation_runs/20261027T024201Z/result.json'),
                       ('reports/zc702_secure_accumulator_20261102/board_verification_attempt2/verified_evidence.json','build/zc702/secure_accumulator_runs/20261102T045046Z/result.json')]:
        proof=json.loads((ROOT/report).read_text());assert proof['raw_replay_verified'] and sha(ROOT/raw)==proof['source_result_sha256'];verified.append(dict(proof=report,raw=raw,sha256=sha(ROOT/raw)))
    checks=dict(command=[sys.executable,str(Path(__file__))],model_self_checks=commands,
        split_probe=dict(records=len(records),split_indices=[i for i,r in enumerate(expected) if r['split']],current_model_last=observed[-1],tail_preserving_reference_last=expected[-1]),
        buffer_budget=dict(current_analysis=vb.analyze_accumulation_session(),whole_blocks_that_fit=16000000//2765,bits_that_fit=(16000000//2765)*2765,next_block_bits=(16000000//2765+1)*2765),
        uart_8n1=dict(baud=115200,max_binary_payload_bits_per_second=92160,max_hex_binary_equivalent_bits_per_second=46080),
        zero_failures_10000=dict(wilson_two_sided95_upper=1.959963984540054**2/(10000+1.959963984540054**2),exact_one_sided95_upper=1-.05**(1/10000)),
        existing_proof_result_hashes_verified=verified,hardware_opened=False,source_sha256=sha(Path(__file__)),input_sha256={n:sha(ROOT/n) for n in pins})
    (OUT/'REVIEW_RECEIPT.json').write_text(json.dumps(checks,indent=2)+'\n')
    (OUT/'split_probe_records.json').write_text(json.dumps(records,indent=2)+'\n')
    print('REVIEW_PROBES_COMPLETE: 2 self-checks pass; split-tail defect reproduced; 3 existing proof/result hash pairs verified; no board access')
if __name__=='__main__':main()
