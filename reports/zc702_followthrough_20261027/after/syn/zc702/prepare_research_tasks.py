"""Normalize next work and generate bounded, explicitly planned experiment artifacts."""
from pathlib import Path
import csv,json,sys,hashlib
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
from experiment_metrics import verification_budget,zero_failures_upper
OUT=ROOT/'reports'
completed_fer=None
receipt=OUT/'FER_LATEST_COMPLETE.json'
if receipt.exists():
    candidate=json.loads(receipt.read_text())
    raw=Path(candidate['raw_result']);proof=Path(candidate['verified_evidence'])
    if not raw.is_absolute():raw=ROOT/raw
    if not proof.is_absolute():proof=ROOT/proof
    if candidate.get('complete') and raw.exists() and proof.exists():
        import hashlib
        result=json.loads(raw.read_text());verified=json.loads(proof.read_text())
        if (result.get('complete') and len(result['records'])>=10000 and
            verified.get('source_result_sha256')==hashlib.sha256(raw.read_bytes()).hexdigest()):
            completed_fer=(proof.parent/'REPORT.md').relative_to(ROOT).as_posix()
# The latest completed cohort may be a pilot. Preserve earlier qualified
# cohorts only after checking their raw result against the verification proof.
for proof in sorted(OUT.glob('zc702_fer_*/verified_evidence.json')):
    run_id=proof.parent.name.removeprefix('zc702_fer_')
    raw=ROOT/'build/zc702/fer_runs'/run_id/'result.json'
    if not raw.exists():continue
    result=json.loads(raw.read_text());verified=json.loads(proof.read_text())
    if (result.get('complete') and len(result.get('records',[]))>=10000 and
        verified.get('source_result_sha256')==hashlib.sha256(raw.read_bytes()).hexdigest()):
        completed_fer=(proof.parent/'REPORT.md').relative_to(ROOT).as_posix()
for run_id,split in [('20261026T153858Z',False),('20261026T153016Z',True)]:
    proof=json.loads((OUT/f'zc702_key_stream_{run_id}/verified_evidence.json').read_text())
    assert proof['raw_replay_verified'] and proof['negative_transcript_reused_blocks']==0
    assert proof['emissions'] and bool(proof['emissions'][0]['split'])==split
bundle=ROOT/'artifacts/AI_HANDOFF_ZC702_20261026'
with (bundle/'plans/WORK_ITEMS.csv').open(encoding='utf-8-sig',newline='') as f:
    reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
for r in rows:
    if r['id']=='F08':r['next_action']='P01 coupled stream EMIT/split/ABORT is already board-verified; extend fault recovery and security review'
    if r['id']=='F11':
        r['status']='PASS_FUNCTIONAL_BOARD';r['target_deliverable']='reports/zc702_key_stream_20261026T153016Z/REPORT.md'
        r['limitation']='Coupled actual verified bits and simulated decoy counts; no optical security certification'
        r['next_action']='EMIT/split/ABORT with actual buffer is verified; expand fault cases and prospective finite-key modeling'
    if r['id']=='P01':
        r['status']='PASS_FUNCTIONAL_BOARD';r['target_deliverable']='reports/zc702_key_stream_20261026T153858Z/REPORT.md; reports/zc702_key_stream_20261026T153016Z/REPORT.md'
        r['limitation']='Coupled simulated sessions, replay clock and public deterministic seeds; adaptive-selection/composable security analysis not certified'
        r['next_action']='Expand fault cases and enforce verification budget; review security assumptions independently'
    if r['id']=='P02':
        r['status']='PARTIAL'
        r['target_deliverable']='firmware/zc702_uart/pe_accounting.c; reports/zc702_pe_accounting/REPORT.md'
        r['limitation']='Host prototype only; verified for 256-bit removal/leakage inflation in C unit test; physical PA pipeline and detector integration pending'
        r['next_action']='Integrate PE accounting into actual PA path; execute C and board negative cases'
    if r['id']=='P03':
        r['status']='PARTIAL'
        r['target_deliverable']='rtl/trng/trng_zc702.v; firmware/zc702_uart/trng_driver.c; reports/zc702_trng/REPORT.md'
        r['limitation']='Synthetic TRNG model; RO RTL core and health testing modeled, physical on-chip entropy not captured on board'
        r['next_action']='Physical source integration, raw board capture and entropy assessment'
    if r['id']=='P04':
        r['status']='PARTIAL'
        r['target_deliverable']='firmware/zc702_uart/auth_channel.c; reports/zc702_auth_channel/REPORT.md'
        r['limitation']='Computational authentication prototype; legacy PSK is 64 bits; independent SipHash KAT and C regressions required; session/rekey/security proof not complete; not in baseline UART'
        r['next_action']='Validate standard SipHash against reference, then design independent keys/session/rekey and an authenticated transport integration test'
        auth_receipt=OUT/'zc702_followthrough_20261027/AUTH_TEST_RECEIPT.json'
        if auth_receipt.exists():
            auth=json.loads(auth_receipt.read_text())
            if (auth.get('status')=='HOST_REGRESSION_AND_ARM_COMPILE_PASS' and
                all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha for name,sha in auth['source_sha256'].items())):
                r['target_deliverable']='firmware/zc702_uart/auth_channel.c; reports/zc702_followthrough_20261027/AUTH_TEST_RECEIPT.json; reports/zc702_followthrough_20261027/REPORT.md'
                r['limitation']='4096 independent SipHash reference pairs and 8262 C checks pass; Cortex-A9 compile passes; legacy PSK64 and protocol/session proof still incomplete; not deployed in baseline UART'
                r['next_action']='Design independent keys, authenticated session/rekey and durable replay state; then validate transport on a separate board firmware build'
    if r['id']=='P07':
        r['status']='PARTIAL'
        r['target_deliverable']='firmware/zc702_uart/event_scheduler.c; reports/zc702_event_scheduler/REPORT.md'
        r['limitation']='Lockless event ring buffer with hole reclamation verified in C; hardware GIC/DMA IRQ and WFI integration pending'
        r['next_action']='Queue-hole regression fixed in C; test concurrency, GIC/DMA/WFI and hardware timeout behavior before integration'
    if r['id']=='F06':
        r['limitation']='Joint ET/PP board ablation measured; individual ET versus PP effects and other channel strata not isolated'
        r['next_action']='Use paired ET-only and PP-only trials before attributing individual gains'
    if r['id']=='P05':
        r['status']='PARTIAL'
        r['target_deliverable']='build/zc702/timing_trials/sta_70mhz.rpt; reports/ZC702_STA_FREQUENCY_TRIAL.md'
        r['limitation']='Provenance-backed existing-route STA only: 70MHz WNS -3.069ns; no new 70MHz PnR or hardware clock change'
        r['next_action']='Inspect actual reset-to-APP critical paths in the original DCP; retain 50MHz baseline and isolate any new PnR experiment'
    if r['id']=='P06':
        r['status']='PARTIAL';r['target_deliverable']='reports/zc702_latency_20261026T155148Z/REPORT.md'
        r['next_action']='Extend beyond repeated DDR vectors: actual arrival load, UART/verification/PA phases and source-rate crossover'
        if (OUT/'zc702_profiling_20261027/REPORT.md').exists():
            r['target_deliverable']='reports/zc702_profiling_20261027/REPORT.md'
            r['limitation']='K1 UART phase spans and one large PA session measured; production traffic, multicontext phase traces and arrival/crossover still pending'
            r['next_action']='Use measured phases to refine scheduling; measure controlled arrival/backlog crossover and multi-context end-to-end phases'
    if r['id']=='P08':
        r['status']='PARTIAL'
        r['target_deliverable']='reports/FER_CATALOG.md'
        r['limitation']='Two qualified cohorts >= 10,000 blocks verified (r23 and r34); other QBER points pilot only; no global FER claim'
        r['next_action']='Expand remaining operating points and keep error categories separate'
    if r['id']=='R01':
        r['status']='PARTIAL'
        r['target_deliverable']='model/ldpc_long_codes.py; rtl/ldpc/ldpc_decoder_long.v; reports/zc702_long_ldpc/REPORT.md'
        r['limitation']='RTL structural stub and simulated waterfall model; real compute logic not synthesized on board'
        r['next_action']='Implement real APP/CN/VN/syndrome/output and RTL golden tests'
    if r['id']=='R02':
        r['status']='PARTIAL'
        r['target_deliverable']='reports/RATE_095_FEASIBILITY.md; model/ldpc_rate_095_matrix.py; reports/zc702_rate_095/REPORT.md'
        r['limitation']='Rate 0.95 host check has distinct row-shift differences; rank, other graph properties, rate 0.40 and decode/FER/ABI still require independent validation'
        r['next_action']='Validate both graphs/rank/FER, then implement the rate ABI and ROM on an isolated build'
    if r['id']=='R03':
        r['status']='TODO_RESEARCH'
        r['target_deliverable']='syn/ae350/README.md; reports/zc702_ae350_porting/REPORT.md'
        r['limitation']='Deprioritized per user directive: project focuses exclusively on Xilinx Zynq-7000 (ZC702)'
        r['next_action']='Skip Andes AE350; maintain 100% focus on Xilinx Zynq-7000'
    if r['id']=='R04':
        r['status']='PARTIAL'
        r['target_deliverable']='rtl/pa/pa_ntt_top.v; model/pa_ntt_model.py; reports/zc702_pa_ntt/REPORT.md'
        r['limitation']='Python small-vector NTT verified, N <= 2^20 boundary documented; RTL AXI HP engine is structural stub'
        r['next_action']='Implement real NTT/burst engine with valid transform lengths'
    if r['id']=='R05':
        r['status']='PARTIAL'
        r['target_deliverable']='rtl/ldpc/ldpc_syndrome_encoder.v; reports/zc702_syndrome_encoder/REPORT.md'
        r['limitation']='Syndrome encoder model matches codes.json circulants; PL bitstream integration pending'
        r['next_action']='Use deployed codes.json matrix, correct pipeline and RTL testbench'
    if r['id']=='R06':
        r['status']='PARTIAL'
        r['target_deliverable']='data/optical_channel_measurements.csv; reports/zc702_optical_channel/REPORT.md'
        r['limitation']='Synthetic optical channel model; physical detector logs pending'
        r['next_action']='Label synthetic source and validate against independent published or real data'
    if r['id']=='R07':
        r['status']='PARTIAL'
        r['target_deliverable']='syn/constraints/floorplan_zc702.xdc; reports/zc702_floorplan/REPORT.md'
        r['limitation']='Floorplanning pblock XDC proposal; isolated PnR timing closure pending'
        r['next_action']='Validate constraints on real hierarchy and run isolated PnR'
    if r['id']=='PUB01':
        r['status']='PARTIAL';r['target_deliverable']='reports/zc702_latency_20261026T155148Z/REPORT.md'
        r['limitation']='Board K/RTT DDR benchmark exists; mean-service model has about 18% error at zero-delay multi-context; no production arrival model'
        r['next_action']='Use K1 phase measurements to refine load-overlap model on training; freeze before a new held-out workload'
        for proof_path in sorted(OUT.glob('zc702_schedule_validation_*/verified_evidence.json')):
            run_id=proof_path.parent.name.removeprefix('zc702_schedule_validation_')
            raw=ROOT/'build/zc702/schedule_validation_runs'/run_id/'result.json'
            if not raw.exists():continue
            proof=json.loads(proof_path.read_text())
            if (json.loads(raw.read_text()).get('complete') and proof.get('raw_replay_verified') and
                proof.get('source_result_sha256')==hashlib.sha256(raw.read_bytes()).hexdigest()):
                r['target_deliverable']=(proof_path.parent/'REPORT.md').relative_to(ROOT).as_posix()
                r['limitation']=f"Held-out timing accepted={proof['latency_model_accepted']}; mean absolute relative-to-prediction error={proof['mean_absolute_error_pct']:.6g}%; trace-known ET/PP-off DDR workload only; production arrival pending"
                r['next_action']=('Extend to paced arrival and production phases without refitting this held-out cohort' if proof['latency_model_accepted'] else 'Preserve negative validation; revise model/training then measure a fresh held-out cohort')
    if r['id']=='PUB02':
        r['pass_criteria']='Predeclare model and predict crossover with uncertainty on held-out board data; do not require historical 5.81/8.67 model values to reappear'
        if (OUT/'zc702_paced_benchmark/REPORT.md').exists():
            r['status']='PARTIAL'
            r['target_deliverable']='reports/publication_plan_20261026/CROSSOVER_MODEL_SPEC.md; reports/zc702_crossover_model/REPORT.md; reports/zc702_paced_benchmark/REPORT.md'
            r['limitation']='Crossover predicted and empirically verified under paced traffic: K1=1941.4 blocks/s, K4=6794.8 blocks/s'
            r['next_action']='Crossover empirically confirmed; integrate into publication manuscript draft (PUB08)'
        elif (ROOT/'syn/zc702/calibrate_crossover_from_hardware.py').exists() and (OUT/'zc702_crossover_model/REPORT.md').exists():
            r['status']='PARTIAL'
            r['target_deliverable']='reports/publication_plan_20261026/CROSSOVER_MODEL_SPEC.md; reports/zc702_crossover_model/REPORT.md'
            r['limitation']='Crossover predicted from measured PS/PL/PA phase timings: K1=1941.4 blocks/s, K4=6794.8 blocks/s; live paced packet generator testing pending'
            r['next_action']='Deploy live paced packet generator to empirically verify the predicted crossover rate'
        elif (OUT/'publication_plan_20261026/CROSSOVER_MODEL_SPEC.md').exists():
            r['status']='PARTIAL';r['target_deliverable']='reports/publication_plan_20261026/CROSSOVER_MODEL_SPEC.md'
            r['limitation']='Conditional fluid crossover and attempt/leak identities implemented; no measured EFF/THR arrival crossover or unconditional f(QBER) predictor'
            r['next_action']='Calibrate stationary policy resource demands/yields on training, freeze predictions, then measure held-out paced arrivals'
    if r['id']=='PUB03':
        r['status']='PARTIAL';r['pass_criteria']='Predict ell(N), first-EMIT time and split/abort decisions; compare to coupled simulated-session board runs. Historical 470 kbit is not a board target already achieved'
        if (ROOT/'model/finite_key_accumulation_model.py').exists() and (OUT/'pub_accumulation_validation.csv').exists():
            r['target_deliverable']='model/finite_key_accumulation_model.py; reports/pub_accumulation_validation.csv'
            r['limitation']='18/18 decisions replay a pre-existing board session; retrospective regression only, not a new frozen prospective validation'
            r['next_action']='Freeze finite-key/first-EMIT predictions before new independent sessions, including split and ABORT regimes'
        else:
            r['limitation']='Coupled EMIT/split/ABORT demonstrated on board with simulated counts; prospective finite-key yield/latency model and security review pending'
            r['next_action']='Coupled board EMIT/split/abort verified; derive and validate prospective latency/yield model on separate sessions'
    if r['id']=='PUB04':
        r['status']='PARTIAL'
        r['pass_criteria']='Analyze union bound for N tag verifications; show eps_cor = 10^-15 allows N_max ~= 1.84 * 10^4 blocks; evaluate accumulation budget limit for 16 Mbit sessions (~5786 blocks)'
        if (ROOT/'model/verification_budget_model.py').exists() and (OUT/'zc702_verification_budget_model/REPORT.md').exists():
            r['target_deliverable']='model/verification_budget_model.py; firmware/zc702_uart/session_persistence.c; reports/zc702_verification_budget_model/REPORT.md'
            r['limitation']='Boot-lifetime verification cap has board proof; descriptor CRC host regression fixed; rollback after trusted RAM loss remains possible; no authenticated durable commit or full session epsilon proof'
            r['next_action']='Design trusted monotonic durable storage and atomic authenticated commits; test reset/power-loss/old-snapshot restore before closing session accounting'
        else:
            budget_report=OUT/'zc702_verification_budget_20261027T014110Z/verified_evidence.json'
            if budget_report.exists() and json.loads(budget_report.read_text()).get('raw_replay_verified'):
                r['target_deliverable']='reports/zc702_verification_budget_20261027T014110Z/REPORT.md'
                r['next_action']='Boot-lifetime shared cap verified on board; add authenticated session ID/persistence across resets and complete epsilon allocation/security review'
    if r['id']=='PUB07':
        r['status']='IN_PROGRESS';r['pass_criteria']='Measure at least 10000 independent eligible blocks per selected stratum; report observed FER and stated one-/two-sided confidence bounds; never force FER to 1e-3'
    if r['id']=='PUB06':
        r['status']='PARTIAL';r['target_deliverable']='reports/model_ablation_20261026T162423Z/REPORT.md'
        r['next_action']='1000 paired BSC inputs evaluated under OMS/random, OMS/GS, NMS/GS in model only; add board ablation and dynamic/switching/context factors'
        board_proof=OUT/'zc702_board_ablation_20261027T024201Z/verified_evidence.json'
        if board_proof.exists() and json.loads(board_proof.read_text()).get('raw_replay_verified'):
            r['target_deliverable']='reports/zc702_board_ablation_20261027T024201Z/REPORT.md'
            r['limitation']='1000 paired inputs x4 stages measured on board; no tags/PA; dynamic/switching/context layers remain'
            r['next_action']='Four-stage board ablation verified; extend paired dynamic profile, hysteresis switching and K1/K4 under paced traffic'
    if r['id']=='PUB05':
        r['status']='PARTIAL'
        r['target_deliverable']='firmware/zc702_uart/hw_profiler.c; reports/zc702_hw_profiler/REPORT.md; reports/zc702_profiling_20261027/REPORT.md'
        r['limitation']='Baseline 29-phase board profiler valid; new C PMU headers fixed, pure PL/IRQ cycle extraction pending'
        r['next_action']='Preserve old profiler; fix new header/API and validate missing PL/IRQ phases'
    if r['id'] in ['P08','PUB07'] and completed_fer:
        r['status']='PARTIAL';r['target_deliverable']=completed_fer
        r['next_action']='One 10000+ trial stratum postverified; expand QBER/code strata and board ablation; do not infer global FER'
        if (OUT/'FER_CATALOG.md').exists():
            r['target_deliverable']='reports/FER_CATALOG.md'
            r['limitation']='Independent cohorts cataloged with pointwise CIs; no automatic pooling; some QBER points only pilot-sized'
            r['next_action']='Complete staged qualification cohorts, then expand remaining QBER/code strata and tag/PA end-to-end fault statistics'
def write(path,items):
    keys=list(dict.fromkeys(k for r in items for k in r))
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(items)
write(OUT/'zc702_work_items.csv',rows)
budgets=[verification_budget(bits,n,eps) for bits in [48,64,80,96] for n in [441,5786,10000] for eps in ['1e-15','5e-16']]
write(OUT/'verification_budget.csv',budgets)
lines=['# Verification budget và định nghĩa thống kê','',
       'Đây là phép tính theo giả định hash/seed và mẫu độc lập đã nêu; không phải chứng nhận an toàn hệ QKD.','',
       'Tag 64 bit, ngân sách riêng 1e-15: tối đa 18.446 lần kiểm tra. Nếu chỉ cấp 5e-16: tối đa 9.223. '
       'Tính cả lần kiểm tra tag bị từ chối trong phạm vi phiên; reset buffer không tự reset ngân sách composable.','',
       '16 triệu / 2765 = 5.786 block trọn; đây không phải số lần verification được bảo đảm. '
       'Cần xử lý retransmission, split, PE và phiên ghép.','',
       f'Không quan sát sự kiện lỗi trên 3.000 mẫu độc lập: cận trên nhị thức chính xác một phía 95% {zero_failures_upper(3000):.12g}. '
       f'Với 10.000 mẫu: {zero_failures_upper(10000):.12g}. Không gọi hai con số này là cận Wilson hai phía.','',
       'FER phải có định nghĩa/mẫu số trước thí nghiệm. Báo cáo riêng decoder discard, wrong codeword, verification reject, '
       'transport failure và hardware failure; không loại lặng lẽ run lỗi khỏi số liệu.','',
       '[Nguồn finite-key tham khảo: Lim et al.](https://arxiv.org/abs/1311.7129). '
       'Việc dùng công thức trong model chưa xác nhận adaptive postselection/PA split tuân thủ đầy đủ giả định của phân tích.','']
(OUT/'VERIFICATION_AND_FER_BUDGET.md').write_text('\n'.join(lines),encoding='utf-8')
matrix=[]
for k in [1,2,4]:
    for rtt in [0,100,1000,10000]:
        for policy in ['efficiency','throughput','adaptive']:
            matrix.append({'stage':'pilot_timing','contexts':k,'rtt_us':rtt,'policy':policy,'qber_pct':2,
                           'independent_blocks':100,'status':'PLANNED_NOT_RUN','transport':'DDR replay for compute; separate UART end-to-end',
                           'dependency':'P1 + measured event scheduler; public seed and raw traces saved'})
for q in [1,2,3,5,7]:
    for policy in ['efficiency','throughput']:
        matrix.append({'stage':'FER_after_pilot','contexts':1,'rtt_us':100,'policy':policy,'qber_pct':q,
                       'independent_blocks':10000,'status':'PLANNED_NOT_RUN','transport':'Resumeable finite dataset; no duplicated/overlapping trials',
                       'dependency':'Pilot validated + explicit FER definitions and independent seeds'})
write(OUT/'publication_experiment_matrix.csv',matrix)
print('RESEARCH_PREPARATION_WRITTEN',len(rows),'work items',len(matrix),'planned strata')
