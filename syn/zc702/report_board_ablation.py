"""Verify paired ablation TX/RX and golden input provenance; hardware compares every status and KEY."""
from pathlib import Path
import argparse,collections,csv,hashlib,json,math,re,statistics,struct,sys,zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
import ir_model as m
import puncture as pu
from experiment_metrics import wilson_interval
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path)
args=ap.parse_args();folder=args.run.resolve();result=json.loads((folder/'result.json').read_text())
assert result['complete'] and result['hardware_capture'] and not result.get('error')
config=result['config'];n=config['trials'];base=m.load_codes(128)[config['code']];settings={s['name']:s for s in config['configurations']}
gs=pu.order(config['code'],base,128,307);sessions={};rows=[];by_trial=collections.defaultdict(dict)
def load_session(name):
    if name in sessions:return sessions[name]
    path=ROOT/name;uart=(path/'uart.log').read_text();xsct=(path/'xsct.log').read_text(errors='replace')
    assert 'ZC702_PROGRAM_MMIO_PASS' in xsct and 'ZC702_SMOKE_CPU_STARTED' in xsct
    assert not re.search(r'FATAL|TIMEOUT|DMA_ERROR|MISMATCH',uart)
    packets={}
    for packet in json.loads((path/'tx_manifest.json').read_text()):
        data=(path/packet['file']).read_bytes()
        assert hashlib.sha256(data).hexdigest()==packet['sha256'] and f'{zlib.crc32(data):08x}'==packet['crc32']
        packets[packet['seq']]=struct.unpack('<'+'I'*(len(data)//4),data)
    sessions[name]=(packets,uart);return packets,uart
assert len(result['batches'])==len(config['randomized_batch_order'])
for index,batch in enumerate(result['batches']):
    spec=config['randomized_batch_order'][index];name=batch['configuration'];s=settings[name]
    assert batch['batch_index']==index and batch['offset']==spec['offset'] and config['configurations'][spec['configuration']]['name']==name
    packets,uart=load_session(batch['session']);assert packets[batch['run_seq']]==(71,1,4,0)
    expected_conv=expected_attempts=0
    for slot,row in enumerate(batch['rows']):
        trial=row['trial'];assert trial==batch['offset']+slot and name not in by_trial[trial]
        values=packets[batch['load_seqs'][slot]];assert values[:2]==(70,slot) and values[2]==len(values)-3
        payload=values[3:];raw=struct.pack('<'+'I'*len(payload),*payload)
        assert hashlib.sha256(raw).hexdigest()==row['payload_sha256'] and row['hardware_match']
        cfg,cfg2,pre,attempts,ns,err,nrev=payload[:7];pp=s['PP']
        wanted_cfg=m.CODE_ORDER.index(config['code'])|(8<<2)|(50<<8)|(pp[0]<<16)|(pp[1]<<18)|(pp[2]<<20)
        assert cfg==wanted_cfg and cfg2==s['ET']|(32 if s['cn']=='nms75' else 0) and pre==0
        rng=np.random.default_rng(config['seed_base']+trial)
        alice=rng.integers(0,2,2765,dtype=np.int64);bob=alice^(rng.random(2765)<config['qber']).astype(np.int64)
        assert row['seed']==config['seed_base']+trial
        h=hashlib.sha256(alice.astype(np.uint8).tobytes()+bob.astype(np.uint8).tobytes()).hexdigest();assert h==row['input_sha256']
        positions=gs if s['positions']=='gs' else np.random.default_rng(config['seed_base']+20000000+trial).choice(3072,307,replace=False)
        keep=np.setdiff1d(np.arange(3072),positions);symbols=np.full(3072,2,dtype=np.int64);symbols[keep]=bob
        channel=payload[7+2*attempts:7+2*attempts+192]
        expected=[sum(int(symbols[w*16+k])<<(2*k) for k in range(16)) for w in range(192)]
        assert list(channel)==expected
        truth=np.zeros(3072,dtype=np.int64);truth[keep]=alice
        truth[positions]=np.random.default_rng(config['seed_base']+10000000+trial).integers(0,2,307)
        syn=m.syndrome(base,truth.reshape(1,24,128),128).reshape(-1)
        actual_syn=payload[7+2*attempts+192:7+2*attempts+192+ns]
        assert list(actual_syn)==[sum(int(syn[w*32+k])<<k for k in range(32)) for w in range(ns)]
        reveals=payload[7+2*attempts+192+ns:-96]
        assert nrev==len(reveals)==sum(payload[7+attempts:7+2*attempts])==row['revealed']
        assert list(reveals)==[int(pos)|(int(truth[pos])<<16) for pos in positions[:nrev]]
        hard=np.unpackbits(np.frombuffer(struct.pack('<96I',*payload[-96:]),dtype=np.uint8),bitorder='little')
        converged=payload[7+attempts-1]>>31;residual=int((hard[keep]!=alice).sum())
        outcome='DISCARD' if not converged else 'WRONG_CODEWORD' if residual else 'SUCCESS'
        assert outcome==row['outcome'] and row['attempts']==attempts and row['residual_errors']==residual
        if converged:assert err==int((hard[keep]!=bob).sum())
        actual=float((alice!=bob).mean());assert actual==row['actual_qber'] and int((alice!=bob).sum())==row['errors_in']
        assert row['leak_ir']==m.CODE_MB[config['code']]*128-307+nrev
        if outcome=='SUCCESS':assert abs(row['f_ir']-row['leak_ir']/(2765*m.h2(actual)))<1e-12
        expected_conv+=int(bool(converged));expected_attempts+=attempts
        by_trial[trial][name]=row;rows.append(dict(row,batch_index=index,batch_elapsed_us=batch['elapsed_us']))
    match=re.search(fr'^QKD_BENCH_PASS seq={batch["run_seq"]} contexts=(\d+) jobs=(\d+) corrected=(\d+) discarded=(\d+) attempts=(\d+) rtt_us=(\d+) elapsed_us=(\d+) busy_cycles=(\d+)',uart,re.MULTILINE);assert match
    assert list(map(int,match.groups()))==[1,4,expected_conv,4-expected_conv,expected_attempts,0,batch['elapsed_us'],batch['busy_cycles']]
assert set(by_trial)==set(range(n)) and len(rows)==4*n
for trial,group in by_trial.items():
    assert set(group)==set(settings) and len({r['input_sha256'] for r in group.values()})==1
assert len({group[next(iter(settings))]['input_sha256'] for group in by_trial.values()})==n
out=ROOT/'reports'/('zc702_board_ablation_'+result['started_utc']);out.mkdir(parents=True,exist_ok=True)
def write(name,data):
    with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
        fields=list(dict.fromkeys(k for r in data for k in r));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
write('trials.csv',rows);summary=[]
for name in settings:
    selected=[r for r in rows if r['configuration']==name];ok=[r for r in selected if r['outcome']=='SUCCESS']
    discarded=sum(r['outcome']=='DISCARD' for r in selected);wrong=sum(r['outcome']=='WRONG_CODEWORD' for r in selected)
    batches=[b for b in result['batches'] if b['configuration']==name];elapsed=sum(b['elapsed_us'] for b in batches)
    interval=wilson_interval(discarded+wrong,n)
    summary.append(dict(configuration=name,trials=n,success=len(ok),discard=discarded,wrong_codeword=wrong,
        FER=(discarded+wrong)/n,FER_Wilson95_low=interval[0],FER_Wilson95_high=interval[1],
        mean_attempts_all=statistics.mean(r['attempts'] for r in selected),
        mean_f_ir_success=statistics.mean(r['f_ir'] for r in ok) if ok else '',
        DDR_IR_elapsed_us=elapsed,DDR_IR_corrected_Mbit_s=len(ok)*2765/elapsed,
        PL_decode_active_us=sum(b['busy_cycles'] for b in batches)/50,
        scope='K1 DDR batches of four; includes PS/DMA/golden checks; no UART/tag/PA inside timing'))
write('summary.csv',summary);contrasts=[];names=list(settings)
common=[g for g in by_trial.values() if all(r['outcome']=='SUCCESS' for r in g.values())]
for a,b in zip(names,names[1:]):
    delta=[g[b]['attempts']-g[a]['attempts'] for g in by_trial.values()]
    mean=statistics.mean(delta);half=1.959963984540054*statistics.stdev(delta)/math.sqrt(n)
    fdelta=[g[b]['f_ir']-g[a]['f_ir'] for g in common]
    fixed=sum(g[a]['outcome']!='SUCCESS' and g[b]['outcome']=='SUCCESS' for g in by_trial.values())
    worse=sum(g[a]['outcome']=='SUCCESS' and g[b]['outcome']!='SUCCESS' for g in by_trial.values());discord=fixed+worse
    p=min(1.,2*sum(math.comb(discord,k) for k in range(min(fixed,worse)+1))/2**discord) if discord else 1.
    contrasts.append(dict(from_configuration=a,to_configuration=b,paired_inputs=n,mean_delta_attempts=mean,
        normal_approx95_low=mean-half,normal_approx95_high=mean+half,common_success=len(common),
        mean_delta_f_common_success=statistics.mean(fdelta) if fdelta else '',failures_fixed=fixed,failures_introduced=worse,mcnemar_exact_p=p))
write('paired_contrasts.csv',contrasts)
proof={'raw_replay_verified':True,'paired_input_hashes_verified':True,'independent_input_pairs':n,'configuration_evaluations':4*n,
       'batch_receipts_verified':len(result['batches']),'sessions':len(sessions),'common_success':len(common),
       'KEY_comparison':'Every converged KEY compared in firmware against golden; raw log contains batch PASS, not literal DMA KEY words',
       'tag_PA_applied':False,'source_result_sha256':hashlib.sha256((folder/'result.json').read_bytes()).hexdigest()}
(out/'verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
text=['# Ablation ghép cặp bốn tầng trên ZC702','',
      f'{n} input Alice/Bob độc lập theo BSC q={config["qber"]}, code={config["code"]}; cùng input và RNG bit D ở cả bốn cấu hình. '
      'Độ dài 3072, D=307, r0=0, reveal step77, 50 iterations. K=1, batch4, RTT=0, PL 50MHz. Thứ tự cấu hình random theo seed trước khi chạy.','',
      '| Cấu hình | Success | Discard | Wrong | Attempts TB | f IR trên success | DDR IR Mbit/s |',
      '|---|---:|---:|---:|---:|---:|---:|']
for r in summary:text.append(f"| {r['configuration']} | {r['success']} | {r['discard']} | {r['wrong_codeword']} | {r['mean_attempts_all']:.3f} | {r['mean_f_ir_success']} | {r['DDR_IR_corrected_Mbit_s']:.3f} |")
text+=['','Ba tầng đầu tắt ET và PP; tầng thứ tư bật ET=12/PP=(1,2,16). Điều này khác ablation model-only trước đó giữ ET/PP bật ở cả ba cấu hình. '
       'Không gộp hai tập thành một ablation. Dynamic profile, switching và đa context vẫn cần các tầng riêng trên dữ liệu ghép cặp.','',
       'Firmware so toàn bộ status/iters/USC/PP và KEY với golden trong vòng đo. Verifier độc lập đối chiếu packet CRC/SHA, '
       'input pairs/CH/syndrome/reveal, ground truth của golden và raw batch receipt; raw log không in lại KEY DMA của từng trial. '
       'f IR không gồm tag; FER gồm decoder discard hoặc converged wrong codeword. Không chạy tag hoặc PA trong phép thử này.','',
       'Thông lượng DDR gồm PS/DMA và kiểm tra golden, loại UART và PA; không phải secret-key throughput. '
       'Không tính ba/bốn cấu hình trên cùng input thành mẫu FER độc lập gộp. Wilson95 là pointwise theo cấu hình; '
       'paired_contrasts.csv có chênh lệch attempts và f trên common-success, tránh so các tập success khác nhau. '
       'CI attempts dùng xấp xỉ chuẩn, McNemar dùng kiểm định nhị thức chính xác; không ép kết luận FER từ ít sự kiện lỗi.','']
(out/'REPORT.md').write_text('\n'.join(text),encoding='utf-8')
print('BOARD_ABLATION_RAW_REPLAY_PASS',out,'pairs',n,'evaluations',4*n,flush=True)
