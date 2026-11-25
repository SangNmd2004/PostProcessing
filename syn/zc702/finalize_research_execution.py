"""Seal completed research gates with evidence guards; never promote canonical statuses."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,collections,csv,hashlib,json,re,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read_csv(p):
    with p.open(encoding='utf-8-sig',newline='') as f:r=csv.DictReader(f);return r.fieldnames,list(r)
def write_csv(p,fields,rows):
    with p.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--stage',required=True,type=Path);args=ap.parse_args();stage=args.stage.resolve();assert stage.is_relative_to(ROOT/'reports') and not (stage/'MANIFEST_SHA256.csv').exists()
    job=json.loads((ROOT/'RUNNING_JOBS.json').read_text());assert job.get('port_released') and job.get('baseline_restored'),job
    pre=json.loads((stage/'PREFLIGHT.json').read_text())
    for n,h in pre['baseline_manifest']['files'].items():assert sha(ROOT/n)==h,n
    for n,h in pre['previous_checkpoint'].items():assert sha(ROOT/n)==h,n
    for r in csv.DictReader((stage/'host_checkpoint/MANIFEST_SHA256.csv').open(encoding='utf-8-sig')):assert sha(stage/'host_checkpoint'/r['file'])==r['sha256'],r['file']
    sequence=json.loads((stage/'paced_sequence/SEQUENCE_STATUS.json').read_text());finite=json.loads((stage/'prospective_finite/STATUS.json').read_text());q05=json.loads((stage/'fer_q05_followup/STATUS.json').read_text())
    assert q05['status'] in ['VERIFIED_COMPLETE','STOPPED_ERROR'] and finite['status'] in ['VERIFIED_COMPLETE','STOPPED_ERROR']
    board_proofs=[]
    for relative,run_key in [('paced_sequence/pilot_verified/verified_evidence.json','training_run'),('paced_sequence/arrival_verified/verified_evidence.json','validation_run')]:
        p=stage/relative;proof=json.loads(p.read_text());assert proof['raw_replay_verified'] and proof['source_result_sha256']==sha(ROOT/sequence[run_key]/'result.json');board_proofs.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p)))
    model=json.loads((stage/'paced_sequence/model_snapshot_recheck/verified_prediction.json').read_text());assert model['raw_replay_verified'] and model['frozen_before_capture']
    failed_runs=[]
    for folder in sorted((ROOT/'build/zc702/paced_runs').iterdir()):
        path=folder/'result.json'
        if not path.exists():continue
        raw=json.loads(path.read_text())
        if raw.get('started_utc','')<pre['started_utc'] or raw.get('complete'):continue
        failed_runs.append(dict(run=folder.relative_to(ROOT).as_posix(),result_sha256=sha(path),uart_sha256=sha(folder/'capture/uart.log') if (folder/'capture/uart.log').exists() else None,
            completed_measurements=len(raw.get('runs',[])),error=raw.get('error'),restore_error=raw.get('restore_error'),baseline_restored=raw.get('baseline_restored',False),build=raw['build_manifest']['elf']))
    (stage/'FAILED_RUNS.json').write_text(json.dumps(failed_runs,indent=2)+'\n')
    fer=[]
    candidates=[sequence.get('fer_run'),q05.get('last_job',{}).get('run_directory')]
    for name in candidates:
        if not name:continue
        run=ROOT/name;raw=json.loads((run/'result.json').read_text());proof_path=ROOT/'reports'/('zc702_fer_'+raw['started_utc'])/'verified_evidence.json'
        if not raw.get('complete') or not proof_path.exists():continue
        proof=json.loads(proof_path.read_text());assert proof['raw_replay_verified'] and proof['source_result_sha256']==sha(run/'result.json')
        fer.append(dict(run=name,proof=proof_path.relative_to(ROOT).as_posix(),sha256=sha(proof_path),summary=raw['summary'],qber=raw['qber'],code=raw['code']))
    if finite.get('complete'):
        p=ROOT/finite['proof'];proof=json.loads(p.read_text());assert proof['raw_replay_verified'] and proof['source_hashes']['result.json']==sha(ROOT/finite['run']/'result.json')
        assert finite['frozen_prediction_sha256']==sha(ROOT/finite['frozen_prediction']);board_proofs.append(dict(path=finite['proof'],sha256=sha(p)))
        finite_raw=json.loads((ROOT/finite['run']/'result.json').read_text())
        finite_outcomes=dict(collections.Counter(r['outcome'] for r in finite_raw['records']))
    else:finite_outcomes={}
    subprocess.run([sys.executable,'syn/zc702/export_fer_catalog.py'],check=True,cwd=ROOT)
    fields,rows=read_csv(ROOT/'reports/zc702_work_items.csv');_,original=read_csv(stage/'before/reports/zc702_work_items.csv')
    ids=lambda rs:[(r['id'],r['title'],r['status']) for r in rs]
    assert ids(rows)==ids(original) and len(rows)==35
    report=(stage/'REPORT.md').relative_to(ROOT).as_posix()
    for r in rows:
        if r['id'] in ['P06','PUB01','PUB02','PUB03','PUB04']:r['target_deliverable']=report
        if r['id']=='PUB01':r['limitation']='Existing ET/PP-off K/RTT model retained; new K1 DDR arrival schedules validated on repeated paired pool, not independent-input or full PA/IRQ model'
        if r['id']=='PUB02':
            r['limitation']='Measured DDR IR proxy crossover only; fixed f_adj and two repeated paired inputs; tag/PE/PA excluded; not secret-key-rate crossover'
            r['next_action']='Extend to independent paired cohorts, controller feedback and actual verified-buffer/PA yield before end-to-end crossover claim'
        if r['id']=='PUB03':
            r['limitation']='Split/event host regression fixed; fresh-source frozen functional capture '+('verified' if finite.get('complete') else 'not completed')+'; virtual age schedule is not optical first-EMIT distribution or security proof'
            r['next_action']='Extend prospective source-clock scenarios including split/ABORT and audit adaptive selection/leakage/epsilon assumptions'
        if r['id']=='PUB04':r['limitation']='Conditional collision accounting and boot-lifetime cap; input buffer/output distinction fixed; no durable anti-rollback or full composable proof'
        if r['id'] in ['P08','PUB07']:
            r['target_deliverable']='reports/FER_CATALOG.md';r['next_action']='Complete remaining predeclared strata including q7/r12; retain separate decoder/tag/PA/transport/hardware accounting'
    assert ids(rows)==ids(original);write_csv(ROOT/'reports/zc702_work_items.csv',fields,rows)
    fields,claims=read_csv(ROOT/'reports/zc702_claim_evidence.csv');assert not any(r['claim_id'] in ['C19','C20'] for r in claims)
    claims.append(dict(claim_id='C19',claim='Timer-paced DDR IR profile/queue measurements and frozen K1 arrival predictions',status='PASS_SCOPED_DDR_IR_COMPONENT',evidence=report,limitation='Two paired public inputs repeated; fixed f_adj; no tag/PE/PA or secret yield; new scheduler wave barrier',permitted_statement_or_next_gate=f"42 pilot and30 arrival measurements; prediction mean error {model['mean_absolute_error_pct']:.6g}%, max {model['max_absolute_error_pct']:.6g}%; extend full pipeline"))
    if finite.get('complete'):claims.append(dict(claim_id='C20',claim='Fresh synthetic finite-key source predictions frozen before board capture',status='PASS_SCOPED_FUNCTIONAL_SIMULATED_SOURCE',evidence=report,limitation='Explicit virtual-age schedule; no optical acquisition-time distribution, production authentication or protocol secrecy proof',permitted_statement_or_next_gate=f"{finite['verified_blocks']} verified appends and {finite['decisions_verified']} decisions; raw PA matches; extend split/ABORT and source-clock scenarios"))
    write_csv(ROOT/'reports/zc702_claim_evidence.csv',fields,claims)
    fer_lines=[]
    for item in fer:
        s=item['summary'];fer_lines.append(f"- QBER={item['qber']*100:g}%, {item['code']}: n={s['trials']}, success={s['success']}, discard={s['discard']}, wrong={s['wrong_codeword_ground_truth']}, FER={s['FER']:.8g}, Wilson95={s['FER_Wilson_two_sided_95']}. [Proof]({Path(item['proof']).relative_to('reports').as_posix()}).")
    text=f'''# Kết quả triển khai kế hoạch nghiên cứu ZC702 — 02/11/2026

Đã sửa kế hoạch và triển khai tuần tự trong phạm vi đã cho phép. **35ID/tên/trạng thái giữ nguyên:13 PASS_FUNCTIONAL_BOARD,20 PARTIAL,2 TODO/TODO_RESEARCH.** Tỷ lệ đầu mục không là tỷ lệ công sức hoặc mức an toàn. Baseline PL50MHz/27file giữ nguyên; không rebuild PL, NTT, LDPC dài hay TRNG mô phỏng thành kết quả hardware.

## Kế hoạch và host

Hai kế hoạch gốc đã sửa để tách mục tiêu, model, đo board và production. Bản trước trong before/, bản host đã niêm phong ở host_checkpoint/. Đã sửa split bằng emitted(), event/session replay và hai quyết định cùng bit count; chỉ commit sau PA thành công. 12 regression PASS;92 quyết định split và18 quyết định EMIT cũ được raw-event replay khớp. Đây là retrospective regression.

Budget generator nay chỉ phân tích collision có điều kiện, không tự nhận persistence PASS;16Mbit input chứa5786block trọn, khác PA output. Generator trạng thái không còn coi report simulator là crossover board. Hợp đồng leakage/tag/epsilon được ghi rõ, không giảm term trong baseline để tạo yield tốt hơn.

## DDR-paced IR thực trên board

ELF riêng dùng timer ARM cho scheduled/actual arrival, dispatch/completion, backlog/drop, profile, attempts/leak/cycles. UART chỉ nạp và lấy log ngoài timed loop. C queue được kiểm tra capacity1..128,100 vòng wrap và256 cấu hình reveal-safety. ARM compile với Wall/Wextra/Werror.

Pilot chính42 phép đo/1344job: K1/2/4, EFF/THR/adaptive, RTT0/1ms, arrival100/1000us. Thêm30 lịch arrival mới/3840job K1, dự đoán freeze trước capture. Mean absolute error trên mẫu số prediction={model['mean_absolute_error_pct']:.6f}%, max={model['max_absolute_error_pct']:.6f}%, proxy-bit error lớn nhất={model['max_IR_proxy_bits_error_pct']:.6f}%; model_accepted={model['model_accepted']}. Đây là tolerance kỹ thuật, không CI. [CSV](paced_sequence/model_snapshot_recheck/prediction_comparison.csv), [proof](paced_sequence/model_snapshot_recheck/verified_prediction.json), [đồ thị](paced_sequence/IR_proxy_validation.png), [SVG](paced_sequence/IR_proxy_validation.svg).

Trên metric IR proxy trừ IR leakage, hai lần lặp tại mỗi arrival point cho EFF tốt hơn THR ở746,83 và1344,09block/s, THR vượt ở1492,54/1642,04/2985,07block/s. Đây là finite-batch component proxy, **không phải throughput khóa bí mật**. Chưa có tag/PE/PA trong vòng đo, f_adj giữ1,3/job; cùng hai input paired lặp lại. Chỉ lịch arrival là held-out; không gọi input là chưa từng chạy.

Verifier đọc TX/UART thật, kiểm tra source Alice/Bob/channel/syndrome/golden, plan/code/r0, outcome, attempts/leak, timestamps, in-flight bound và hysteresis. KEY được firmware bench_check đối chiếu golden; raw metric không chứa literal DMA KEY. Negative control sửa leak trong UART trong khi runner JSON không đổi bị verifier từ chối.

## Các lỗi và hồi phục được giữ

Lượt smoke đầu chạy4case rồi restore gặp Already stopped; giữ raw run20261102T051641Z và receipt hồi phục. Helpers JTAG nay chỉ bỏ qua lỗi chính xác đó, các lỗi khác vẫn fail. Smoke chạy lại có raw proof.

Các thử nghiệm full-pilot trước gặp CPU timeout ở K4/adaptive, trước hết RTT1ms rồi RTT0; không tính các cohort đó là complete/PASS. Chẩn đoán CPU có trường hợp không halt được. RTL cho thấy REVEAL AXI write có thể chờ reveal engine trong lúc KEY output chiếm CH read port; một simple RX buffer cần CPU rearm tạo nguy cơ chờ vòng. Nhánh thử mới thu hết lượt đang active trước khi load/reveal lượt kế, rồi queue các context đã chuẩn bị. Không tuyên bố đã chứng minh mọi nguyên nhân phần cứng; hàng rào này loại nguy cơ đã nhận diện và hồi quy K4/RTT0 đạt10lượt/320job, sau đó pilot chính đạt. RTL/baseline không đổi. Failed captures và ELF variants vẫn được giữ dưới build/zc702/paced_runs và paced_test.

## FER qualification mới

Fixed n, synthetic BSC độc lập, seed disjoint; không dừng sớm theo CI. Mỗi vector được board đánh giá một lần. KEY/status được firmware so golden và verifier đối chiếu lại input/source/packet/receipt; không chạy tag/PA trong cohort này. Captured counter trong RUNNING_JOBS không được coi là đã raw-verified.

{chr(10).join(fer_lines) if fer_lines else '- Chưa có cohort mới hoàn tất; đọc trạng thái lỗi được giữ.'}

Catalog được cập nhật nhưng không gộp seed/QBER/code; kết quả một stratum không là FER toàn hệ. Các error/partial run giữ nguyên.

## Finite-key source mới

Status={finite['status']}. {str(finite.get('verified_blocks','N/A'))} block append và {str(finite.get('decisions_verified','N/A'))} quyết định được kiểm chứng nếu STATUS có complete=true. [Trạng thái/proof](prospective_finite/STATUS.json). Source seed2026110220 mới; input/key/counts test-basis theo cùng cửa sổ mô phỏng, prediction được freeze trước board. Raw verifier tái tính tag và PA từ actual KEY/seed, không tin expected/PASS runner.

Outcome của nguồn mới: {finite_outcomes}. Tag sai có chủ đích được tách khỏi discard decoder; không dùng tập nguồn tương quan này như cohort FER BSC độc lập.

Clock được quy định trước: tăng virtual time theo block retained rồi idle+3601s để kiểm tra age gate. Đây là prospective **functional replay** của nguồn đã generate và biết trước; không là dự đoán phân bố first-EMIT của nguồn quang tương lai hoặc wall time. Không đóng PUB03/composable security từ phép khớp này. Nếu STOPPED_ERROR thì giữ lỗi và không thêm claim PASS cho chặng này.

## Gate còn thiếu và checkpoint

Tiếp tục q7/r12 qualification, nguồn/tập input rộng hơn, controller feedback, PA/verified-buffer trong pacing và finite-key source-clock split/ABORT. PE/leak/selection/epsilon cần hợp đồng và review trước claim secret yield. P04/PUB04 production trust, entropy, reboot accounting và rollback vẫn PARTIAL. Không chạy NTT/PL rebuild để thay các gate còn thiếu này.

Baseline27hash khớp; checkpoint secure-accumulator trước và host_checkpoint không bị đổi. Các run thử đã restore qua MMIO/READY, cohort FER dùng chính baseline firmware. COM3 đã đóng và được controller probe lại. [RUNNING_JOBS](../../RUNNING_JOBS.json) là trạng thái live.
'''
    text += '\n## Document encoding correction\n\nThe sealed host checkpoint retained its original hash, including a prose encoding defect (Vietnamese accents replaced by question marks). It is not rewritten. The two live plan documents were rewritten as UTF-8 and their readable copies are preserved in current_sources/. This final report supersedes the defective prose; host receipts and raw replay results remain unchanged.\n'
    for name in ['MO_HINH_TOAN_HOC_VA_KE_HOACH_THUC_NGHIEM.md','KE_HOACH_TONG_THE_VA_HUONG_PHAT_TRIEN.md']:
        plan_text=(ROOT/name).read_text(encoding='utf-8')
        assert sum(ord(c)>127 for c in plan_text)>100 and '?' not in plan_text, name
    # Make links to FER proofs relative to this stage, not reports root.
    for item in fer:text=text.replace(']('+Path(item['proof']).relative_to('reports').as_posix()+')','](../'+Path(item['proof']).relative_to('reports').as_posix()+')')
    (stage/'REPORT.md').write_text(text,encoding='utf-8')
    subprocess.run([sys.executable,'syn/zc702/write_canonical_mapping.py','--output',str(stage)],check=True,cwd=ROOT)
    evidence=dict(completed_gate_proofs_verified=True,all_queued_stages_complete=bool(sequence.get('complete') and finite.get('complete') and q05.get('complete')),host_tests=12,
        board_proofs=board_proofs,model_prediction=model,FER=fer,baseline_files_verified=27,port_released=True,scope='Scoped functional/research evidence; canonical statuses unchanged; no full project/security completion')
    (stage/'verified_evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    pointer=json.loads((ROOT/'reports/RECONCILIATION_CURRENT.json').read_text());pointer.update(physical_board_rerun=True,verified_evidence=(stage/'verified_evidence.json').relative_to(ROOT).as_posix(),verified_evidence_sha256=sha(stage/'verified_evidence.json'))
    (ROOT/'reports/RECONCILIATION_CURRENT.json').write_text(json.dumps(pointer,indent=2)+'\n')
    progress=ROOT/'reports/TIEN_DO_TOAN_BO_DU_AN.md'
    if progress.exists():
        old=stage/'before/reports/TIEN_DO_TOAN_BO_DU_AN.md'
        if not old.exists():old.parent.mkdir(parents=True,exist_ok=True);old.write_bytes(progress.read_bytes())
        content=progress.read_text(encoding='utf-8')
        content=re.sub(r'^Cập nhật:.*$', 'Cập nhật: '+datetime.now(timezone(timedelta(hours=7))).isoformat()+'.',content,count=1,flags=re.M)
        note=f"- [Triển khai nghiên cứu02/11]({stage.name}/REPORT.md): sửa model host;42 pilot +30 arrival measurements raw-verified, K1 prediction mean error={model['mean_absolute_error_pct']:.4f}%; source/FER mới đọc đúng scope trong report.35ID/status không đổi; chưa là secret-key throughput hoặc production security."
        content=content.replace('## Kết quả mới có bằng chứng','## Kết quả mới có bằng chứng\n\n'+note,1)
        by_id={r['id']:r for r in rows}
        def row_text(match):
            item=by_id[match[1]];return '| '+item['id']+' | '+item['status']+' | '+item['next_action'].replace('|','/')+' |'
        content=re.sub(r'^\| ((?:P|PUB|R)\d{2}) \|.*$',row_text,content,flags=re.M);progress.write_text(content,encoding='utf-8')
    snapshot_names=['MO_HINH_TOAN_HOC_VA_KE_HOACH_THUC_NGHIEM.md','KE_HOACH_TONG_THE_VA_HUONG_PHAT_TRIEN.md','GUIDE_BAN_GIAO_AI_TIEP_THEO.md','reports/zc702_work_items.csv','reports/zc702_claim_evidence.csv','reports/RECONCILIATION_CURRENT.json','reports/TIEN_DO_TOAN_BO_DU_AN.md','RUNNING_JOBS.json']
    snapshot_names += [p.relative_to(ROOT).as_posix() for pattern in ['paced*.py','*paced*.py','*finite*.py','run_managed_fer.py','continue_q05_after_finite.py','prepare_research_tasks.py','uart_session.py','program_smoke.tcl','program_bootstrap.tcl','diagnose_paced.tcl','finalize_research_execution.py'] for p in (ROOT/'syn/zc702').glob(pattern)]
    snapshot_names += ['model/finite_key_accumulation_model.py','model/verification_budget_model.py','model/test_research_models.py','model/paced_component_model.py','syn/zc702/tests/paced_queue_test.c','firmware/zc702_uart/paced_benchmark.h','firmware/zc702_uart/paced_queue.h','syn/zc702/run_key_stream.py','syn/zc702/report_key_stream.py','syn/zc702/run_fer_campaign.py','syn/zc702/verify_experiment_run.py']
    for name in sorted(set(snapshot_names)):
        dest=stage/'current_sources'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/name).read_bytes())
    shutil.copytree(ROOT/'build/zc702/paced_test/20261102_safe_wave_v7',stage/'executed_paced_build')
    for name in ['FER_CATALOG.csv','FER_CATALOG.json','FER_CATALOG.md']:(stage/name).write_bytes((ROOT/'reports'/name).read_bytes())
    versions=[]
    for exe in [sys.executable,'C:/msys64/mingw64/bin/gcc.exe','D:/Xilinx/Vitis/2020.2/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe']:
        p=subprocess.run([exe,'--version'],capture_output=True,text=True);versions.append(dict(command=[exe,'--version'],returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
    (stage/'TOOL_VERSIONS.json').write_text(json.dumps(versions,indent=2)+'\n')
    (stage/'CHECKPOINT.json').write_text(json.dumps(dict(status='SCOPED_RESEARCH_GATES_VERIFIED' if evidence['all_queued_stages_complete'] else 'SCOPED_COMPLETED_GATES_WITH_RETAINED_ERRORS',previous_checkpoint_unchanged=True,host_checkpoint_unchanged=True,baseline_files_verified=27,baseline_restored=True,port_released=True,canonical_status_counts=dict(collections.Counter(r['status'] for r in rows)),raw_runs_remain_workspace_dependencies=True),indent=2)+'\n')
    for n,h in pre['previous_checkpoint'].items():assert sha(ROOT/n)==h,n
    for n,h in pre['baseline_manifest']['files'].items():assert sha(ROOT/n)==h,n
    with (stage/'MANIFEST_SHA256.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['file','bytes','sha256']);w.writerows((p.relative_to(stage).as_posix(),p.stat().st_size,sha(p)) for p in sorted(stage.rglob('*')) if p.is_file() and p!=stage/'MANIFEST_SHA256.csv')
    for r in csv.DictReader((stage/'MANIFEST_SHA256.csv').open()):assert sha(stage/r['file'])==r['sha256'] and (stage/r['file']).stat().st_size==int(r['bytes'])
    print('RESEARCH_EXECUTION_CHECKPOINT_SEALED',stage,flush=True)
if __name__=='__main__':main()
