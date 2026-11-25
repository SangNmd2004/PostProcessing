"""Reconstruct DDR-paced rows from raw UART and TX; derive outcomes/leak from input bytes."""
from pathlib import Path
import argparse,csv,hashlib,json,re,struct,sys,zlib
import numpy as np
from checkpoint_io import write_checkpoint
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
import dyn_ir as d,ir_model as ir,puncture as pu
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def unpack(raw):return list(struct.unpack('<'+'I'*(len(raw)//4),raw))
def verify(run):
    result=json.loads((run/'result.json').read_text());assert result['complete'] and result['baseline_restored'] and not result.get('error')
    build=ROOT/result['build_manifest']['elf'];assert sha(build)==result['build_manifest']['elf_sha256']
    for n,h in result['build_manifest']['source_sha256'].items():
        snapshot=build.parent/'source_snapshot'/n;assert sha(snapshot if snapshot.exists() else ROOT/n)==h,n
    for n,h in result['build_manifest']['generated_sha256'].items():assert sha(build.parent/n)==h,n
    for n,h in result['baseline_manifest']['files'].items():assert sha(ROOT/n)==h,n
    assert 'ZC702_PROGRAM_MMIO_PASS' in (run/'capture/xsct.log').read_text(errors='replace')
    assert 'ZC702_PROGRAM_MMIO_PASS' in (run/'baseline_restore/xsct.log').read_text(errors='replace')
    assert 'QKD_UART_READY version=1 max_words=4096' in (run/'baseline_restore/uart.log').read_text()
    uart=(run/'capture/uart.log').read_text();assert 'QKD_PACED_BUILD version=1 public=1' in uart
    assert not re.search('FATAL|TIMEOUT|DMA_ERROR|MISMATCH',uart)
    frames=json.loads((run/'capture/tx_manifest.json').read_text());vectors={};pe=None;measurements=[];rows=[];codes=ir.load_codes(128)
    for f in frames:
        raw=(run/'capture'/f['file']).read_bytes();assert sha(run/'capture'/f['file'])==f['sha256'] and f'{zlib.crc32(raw):08x}'==f['crc32']
        w=unpack(raw);seq=f['seq'];op=w[0]
        if op==70:
            assert w[2]==len(w)-3;v=w[3:];cfg,cfg2,pre,attempts,ns,err,nr=v[:7];code=cfg&3
            offset=7+2*attempts;counts=v[7+attempts:7+2*attempts];assert pre+sum(counts)==nr
            golden=np.unpackbits(np.frombuffer(struct.pack('<'+'I'*96,*v[offset+192+ns+nr:]),dtype=np.uint8),bitorder='little')
            positions=pu.order(ir.CODE_ORDER[code],codes[ir.CODE_ORDER[code]],128,307);keep=np.ones(3072,dtype=bool);keep[positions]=False
            slot=w[1];source=result['fixtures']['sources'][slot//2];path=ROOT/result['fixture_directory']/source['file'];assert sha(path)==source['file_sha256']
            data=np.load(path);alice=data['alice'];bob=data['bob'];assert hashlib.sha256(alice.astype('u1').tobytes()+bob.astype('u1').tobytes()).hexdigest()==source['input_sha256']
            channel=np.array([(value>>(2*k))&3 for value in v[offset:offset+192] for k in range(16)])
            assert np.all(channel[positions]==2) and np.array_equal(channel[keep],bob)
            prepared=d.prepare_block(alice,bob,source['seed']+200000,positions)
            syndrome=ir.syndrome(codes[ir.CODE_ORDER[code]],prepared['v'].reshape(1,24,128),128).reshape(-1)
            wanted=[sum(int(syndrome[w*32+k])<<k for k in range(32)) for w in range(len(syndrome)//32)]
            assert v[offset+192:offset+192+ns]==wanted
            converged=bool(v[7+attempts-1]>>31);correct=converged and np.array_equal(golden[keep],alice)
            # Source bytes bind the two policies to identical Alice/Bob inputs.
            ctrl=d.Controller(mode='basic' if slot%2==0 else 'dynamic',f_target=1.3,f_safe=1.7,pe_z=1.5,abort_basic=True)
            name,r0=ctrl.plan(source['q_pe'],source['n_pe']);assert name==ir.CODE_ORDER[code] and r0==pre
            vectors[slot]=dict(code=code,pre=pre,attempts=attempts,leak=[12,8,6,4][code]*128-307+nr,converged=converged,correct=correct,payload_sha256=hashlib.sha256(raw[12:]).hexdigest())
            assert vectors[slot]['payload_sha256']==result['fixtures']['vectors'][slot]['sha256']
        elif op==78:
            assert len(w)==5;pe=w[1:]
            for i,source in enumerate(result['fixtures']['sources']):assert w[2+i*2]==source['n_pe'] and w[1+i*2]==struct.unpack('<I',struct.pack('<f',source['q_pe']))[0]
        elif op==76:
            assert pe is not None and len(vectors)==4
            match=re.search(fr'^QKD_PACED_PASS seq={seq} contexts=(\d+) jobs=(\d+) corrected=(\d+) discarded=(\d+) dropped=(\d+) interval_us=(\d+) policy=(\d+) elapsed_us=(\d+)',uart,re.M);assert match
            k,jobs,conv,discard,drop,interval,policy,elapsed=map(int,match.groups());assert [k,jobs,interval,policy]==[w[1],w[2],w[4],w[6]];assert conv+discard+drop==jobs
            measurements.append(dict(run_seq=seq,k=k,jobs=jobs,rtt=w[3],interval=interval,capacity=w[5],policy=policy,elapsed_us=elapsed,corrected=conv,discarded=discard,dropped=drop))
        elif op==77:
            measurement=measurements[-1];jobs=measurement['jobs'];fields=['id','scheduled','arrived','dispatch','complete','profile','slot','backlog','outcome','attempts','leak','cycles']
            pattern=fr'^QKD_PACED_JOB seq={seq} '+r' '.join(name+r'=(\d+)' for name in fields)
            jobrows=[dict(zip(fields,map(int,m))) for m in re.findall(pattern,uart,re.M)]
            assert [r['id'] for r in jobrows]==list(range(jobs));assert f'QKD_PACED_ROWS_DONE seq={seq} rows={jobs}' in uart
            dropped=sum(r['outcome']==2 for r in jobrows);converged=sum(r['outcome']==0 for r in jobrows);discard=sum(r['outcome']==1 for r in jobrows)
            assert [converged,discard,dropped]==[measurement['corrected'],measurement['discarded'],measurement['dropped']]
            profile=0;active=[];proxy=0;correct=wrong=0
            for r in jobrows:
                assert r['scheduled']==r['id']*measurement['interval'];assert r['scheduled']<=r['arrived']<=r['complete']<=measurement['elapsed_us']
                if r['outcome']==2:
                    assert all(r[name]==0xffffffff for name in ['dispatch','profile','slot','backlog','attempts','leak','cycles']);continue
                assert r['arrived']<=r['dispatch']<=r['complete'];assert r['backlog']<measurement['capacity']
                if measurement['policy']==2:
                    if r['backlog']>=4:profile=1
                    elif r['backlog']<=1:profile=0
                else:profile=measurement['policy']
                assert r['profile']==profile and r['slot']==r['id']%2*2+profile
                v=vectors[r['slot']];assert r['attempts']==v['attempts'] and r['leak']==v['leak'] and r['cycles']>0
                assert (r['outcome']==0)==v['converged']
                if v['correct']:proxy+=max(0,2765-r['leak']);correct+=1
                elif v['converged']:wrong+=1
                active.extend([(r['dispatch'],1),(r['complete'],-1)])
                # Quantization to microseconds can tie arrival/dispatch events.
                definite=sum(o['id']!=r['id'] and o['outcome']!=2 and o['arrived']<r['dispatch']<o['dispatch'] for o in jobrows)
                possible=sum(o['id']!=r['id'] and o['outcome']!=2 and o['arrived']<=r['dispatch']<=o['dispatch'] for o in jobrows)
                assert definite<=r['backlog']<=possible
            in_flight=0
            for _,delta in sorted(active):in_flight+=delta;assert 0<=in_flight<=measurement['k']
            measurement.update(IR_correct_bits=correct*2765,wrong_converged=wrong,IR_retained_proxy_bits=proxy,IR_correct_Mbit_s=correct*2765/measurement['elapsed_us'],
                IR_proxy_Mbit_s=proxy/measurement['elapsed_us'],max_observed_arrival_lateness_us=max(r['arrived']-r['scheduled'] for r in jobrows),
                scope='DDR-paced IR only; proxy subtracts IR leak, excludes tag/PE/PA; no secret yield')
            rows.extend(dict(run_seq=measurement['run_seq'],**r) for r in jobrows)
        else:raise AssertionError(op)
    assert len(measurements)==len(result['config']['cases']) and len(rows)==sum(m['jobs'] for m in measurements)
    for m,case in zip(measurements,result['config']['cases']):assert all(m[k]==case[k] for k in ['k','jobs','rtt','interval','capacity','policy'])
    return result,measurements,rows

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--no-job-update',action='store_true');args=ap.parse_args();run=args.run.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    result,measurements,rows=verify(run)
    for name,items in [('measurements.csv',measurements),('jobs.csv',rows)]:
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:writer=csv.DictWriter(f,fieldnames=list(items[0]));writer.writeheader();writer.writerows(items)
    proof=dict(raw_replay_verified=True,source_result_sha256=sha(run/'result.json'),uart_sha256=sha(run/'capture/uart.log'),tx_manifest_sha256=sha(run/'capture/tx_manifest.json'),
        measurements=len(measurements),jobs=len(rows),drops=sum(m['dropped'] for m in measurements),baseline_restored=True,verifier_sha256=sha(Path(__file__)),
        scope='PUBLIC DDR-paced IR component. Golden KEY checked by firmware bench_check; raw log holds metrics not literal DMA KEY. Two independent inputs replayed, not FER samples. No PA/secret-key throughput/crossover certification.')
    (out/'verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
    if not args.no_job_update:
        job=json.loads((ROOT/'RUNNING_JOBS.json').read_text());assert job['run_directory']==run.relative_to(ROOT).as_posix() and job['port_released'];job.update(status='VERIFIED_COMPLETE',report=(out/'verified_evidence.json').relative_to(ROOT).as_posix());write_checkpoint(ROOT/'RUNNING_JOBS.json',job)
    print('PACED_RAW_REPLAY_PASS',len(measurements),'measurements',len(rows),'jobs')
if __name__=='__main__':main()
