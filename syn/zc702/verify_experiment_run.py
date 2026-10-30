"""Independent request/log checks for DDR latency or independent-BSC FER runs."""
from pathlib import Path
import argparse,collections,csv,hashlib,json,re,struct,sys,zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
import ir_model as m
import puncture as pu
from experiment_metrics import wilson_interval,zero_failures_upper
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('kind',choices=['latency','fer']);ap.add_argument('run',type=Path)
args=ap.parse_args();folder=args.run.resolve();result=json.loads((folder/'result.json').read_text())
assert result['complete'] and result['hardware_capture']
def frames(session):
    uart=(session/'uart.log').read_text();xsct=(session/'xsct.log').read_text(errors='replace')
    assert 'ZC702_PROGRAM_MMIO_PASS' in xsct and 'ZC702_SMOKE_CPU_STARTED' in xsct
    assert not re.search(r'FATAL|TIMEOUT|DMA_ERROR|MISMATCH',uart)
    requests=json.loads((session/'tx_manifest.json').read_text())
    for r in requests:
        data=(session/r['file']).read_bytes()
        assert hashlib.sha256(data).hexdigest()==r['sha256'] and f'{zlib.crc32(data):08x}'==r['crc32']
        yield r['seq'],struct.unpack('<'+'I'*(len(data)//4),data),uart
def receipt(uart,seq):
    match=re.search(fr'QKD_BENCH_PASS seq={seq} contexts=(\d+) jobs=(\d+) corrected=(\d+) discarded=(\d+) attempts=(\d+) rtt_us=(\d+) elapsed_us=(\d+) busy_cycles=(\d+)',uart)
    assert match,(seq,'missing receipt')
    return list(map(int,match.groups()))
if args.kind=='latency':
    raw=[]
    for seq,w,uart in frames(folder):
        if w[0]!=71:continue
        k,n,conv,discard,att,rtt,elapsed,busy=receipt(uart,seq)
        assert [k,n,rtt]==[w[1],w[2],w[3]] and conv==n and discard==0
        raw.append((k,n,att,rtt,elapsed,busy))
    assert len(raw)==len(result['records'])==36
    for values,row in zip(raw,result['records']):
        assert tuple(row[k] for k in ['contexts','jobs','attempts','rtt_us','elapsed_us','decoder_busy_cycles'])==values
    assert all(r['contexts']==1 and r['rtt_us']==0 for r in result['records'][:3])
    assert result['model']['frozen_before_validation']
    proof={'raw_receipts_verified':len(raw),'physical_block_evaluations':sum(r['jobs'] for r in result['records']),
           'scope':'DDR IR replay only; repeated vectors, no independent FER or secret-key throughput'}
    out=ROOT/'reports'/('zc702_latency_'+result['started_utc'])
else:
    records=result['records'];assert len(records)==result['planned_trials']
    assert [r['trial_id'] for r in records]==list(range(len(records)))
    assert len({r['packet_sha256'] for r in records})==len(records)
    base=m.load_codes(128)[result['code']];positions=pu.order(result['code'],base,128,307)
    keep=np.ones(3072,dtype=bool);keep[positions]=False;cursor=0;cache={}
    for dirname in result['attempt_sessions']:
        for seq,w,uart in frames(Path(dirname)):
            if w[0]==70:
                assert w[2]==len(w)-3;cache[w[1]]=w[3:]
            if w[0]!=71:continue
            assert set(cache)==set(range(4)) and list(w[1:])==[4,4,0]
            batch=records[cursor:cursor+4];assert len(batch)==4
            expected_conv=0;expected_attempts=0
            for index,row in enumerate(batch):
                payload=cache[index];raw=struct.pack('<'+'I'*len(payload),*payload)
                assert hashlib.sha256(raw).hexdigest()==row['packet_sha256']
                cfg,cfg2,pre,attempts,ns,err,nr=payload[:7]
                assert cfg&3==m.CODE_ORDER.index(result['code']) and cfg2==44 and pre==0 and attempts==row['attempts']
                initial=7+2*attempts;ch=payload[initial:initial+192];sy=payload[initial+192:initial+192+ns]
                sym=np.array([(value>>(2*k))&3 for value in ch for k in range(16)],dtype=np.uint8)
                rng=np.random.default_rng(row['seed']);alice=rng.integers(0,2,2765,dtype=np.int64)
                bob=alice^(rng.random(2765)<result['qber']).astype(np.int64)
                assert np.all(sym[positions]==2) and np.array_equal(sym[keep],bob)
                assert int((alice!=bob).sum())==row['errors_in']
                truth=np.zeros(3072,dtype=np.int64);truth[keep]=alice
                truth[positions]=np.random.default_rng(result['seed_base']+10000000+row['trial_id']).integers(0,2,307)
                syn=m.syndrome(base,truth.reshape(1,24,128),128).reshape(-1)
                wanted=[sum(int(syn[t*32+k])<<k for k in range(32)) for t in range(len(syn)//32)]
                assert list(sy)==wanted
                converged=payload[7+attempts-1]>>31
                key_words=payload[-96:];hard=np.unpackbits(np.frombuffer(struct.pack('<96I',*key_words),dtype=np.uint8),bitorder='little')
                residual=int((hard[keep]!=alice).sum())
                outcome='DISCARD' if not converged else 'WRONG_CODEWORD' if residual else 'SUCCESS'
                assert row['outcome']==outcome
                expected_conv+=bool(converged);expected_attempts+=attempts
            k,n,conv,discard,att,rtt,elapsed,busy=receipt(uart,seq)
            assert [k,n,conv,discard,att,rtt]==[4,4,expected_conv,4-expected_conv,expected_attempts,0]
            cursor+=4;cache={}
    assert cursor==len(records)
    errors=sum(r['outcome']!='SUCCESS' for r in records)
    assert result['summary']['FER']==errors/len(records)
    proof={'raw_receipts_verified':cursor//4,'independent_synthetic_trials':cursor,'FER':errors/cursor,
           'wilson_two_sided_95':wilson_interval(errors,cursor),
           'exact_zero_event_one_sided_95_upper':zero_failures_upper(cursor) if not errors else None,
           'scope':'IR component; no tag or PA in this measurement'}
    out=ROOT/'reports'/('zc702_fer_'+result['started_utc'])
proof['source_result_sha256']=hashlib.sha256((folder/'result.json').read_bytes()).hexdigest()
out.mkdir(exist_ok=True,parents=True);(out/'verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
if args.kind=='fer' and len(result['records'])>=10000:
    # Completion hook for the long-running campaign. It marks one stratum done,
    # never claims that every QBER/policy or the whole project is complete.
    report=(out/'REPORT.md').relative_to(ROOT).as_posix()
    point=f"{len(result['records'])} independent BSC trials; q={result['qber']}; code={result['code']}; NMS+GS"
    status_file=ROOT/'reports/zc702_acceptance_status.csv'
    if status_file.exists():
        with status_file.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);fields=reader.fieldnames;statuses=list(reader)
        for row in statuses:
            if row['id']=='P08':row.update(status='PARTIAL',scope=point,evidence=report,
                limitation='One stratum postverified; other QBER/configurations and tag/PA error rates not covered',
                remaining_gate='Extend predeclared independent strata; preserve per-point confidence intervals')
        with status_file.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(statuses)
    work_file=ROOT/'reports/zc702_work_items.csv'
    if work_file.exists():
        with work_file.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);fields=reader.fieldnames;work=list(reader)
        for row in work:
            if row['id'] in ['P08','PUB07']:
                row.update(status='PARTIAL',target_deliverable=report,
                    next_action='One 10000+ trial stratum postverified; expand QBER/code strata and board ablation; do not infer global FER')
        with work_file.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(work)
    job_file=ROOT/'RUNNING_JOBS.json'
    if job_file.exists():
        job=json.loads(job_file.read_text(encoding='utf-8-sig'))
        if job.get('run_directory')==folder.relative_to(ROOT).as_posix():
            job.update(status='VERIFIED_COMPLETE',verified_trials=len(result['records']),port_released=True,report=report)
            job_file.write_text(json.dumps(job,indent=2)+'\n')
print('EXPERIMENT_RAW_VERIFY_PASS',args.kind,out,flush=True)
