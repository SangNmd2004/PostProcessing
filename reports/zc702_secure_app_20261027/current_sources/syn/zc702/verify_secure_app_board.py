"""Verify QAS2 MACs, application traces, PL KEY/PA and non-dispatch on rejection."""
from pathlib import Path
import argparse,csv,hashlib,json,re,struct,sys
import numpy as np
from qas2_bootstrap import Bootstrap,BootstrapError
from qas2_pc import Session,SessionError
from checkpoint_io import write_checkpoint
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
import pa_model as pa

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path);args=ap.parse_args()
    run=args.run.resolve();raw=(run/'result.json').read_bytes();result=json.loads(raw)
    assert result['complete'] and result['baseline_restored'] and not result.get('error')
    build=ROOT/result['build_manifest']['elf'];assert hashlib.sha256(build.read_bytes()).hexdigest()==result['build_manifest']['elf_sha256']
    assert hashlib.sha256((build.parent/'secure_main.c').read_bytes()).hexdigest()==result['build_manifest']['generated_sha256']
    for name,sha in result['build_manifest']['source_sha256'].items():
        snapshot=build.parent/'source_snapshot'/name;candidate=snapshot if snapshot.exists() else ROOT/name
        assert hashlib.sha256(candidate.read_bytes()).hexdigest()==sha,name
    uart=(run/'uart.log').read_text();xsct=(run/'xsct.log').read_text(errors='replace')
    assert 'SA_READY kat=PASS fixture=PUBLIC' in uart and 'ZC702_PROGRAM_MMIO_PASS' in xsct
    # Application debug output must be inside MAC-covered replies, not raw UART.
    assert not re.search(r'^QKD_FUNC_',uart,re.MULTILINE)
    assert 'QKD_UART_READY version=1 max_words=4096' in (run/'baseline_restore/uart.log').read_text()
    assert 'ZC702_PROGRAM_MMIO_PASS' in (run/'baseline_restore/xsct.log').read_text(errors='replace')
    for name,sha in result['baseline_manifest']['files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha,name
    observed=[]
    for line in uart.splitlines():
        if line.startswith('QB '):
            parts=line.split();observed.append((int(parts[1]),bytes.fromhex(parts[2]) if len(parts)==3 else b''))
    assert len(observed)==len(result['tx'])
    psk=bytes(range(1,33));aid=bytes(range(1,17));bid=bytes(range(17,33));boot=None;session=Session()
    dispatches=used=active=key_valid=0;current=None;attempt=0;rows=[];actual_key=None;rejects={}
    def keyhash(bits,seed):
        padded=np.pad(bits,(0,(-len(bits))%32));sb=np.unpackbits(np.frombuffer(struct.pack('<120I',*seed),dtype=np.uint8),bitorder='little')
        return list(map(int,np.frombuffer(np.packbits(pa.pa_hash(padded,sb),bitorder='little').tobytes(),dtype='<u8')))
    for tx,(rc,answer) in zip(result['tx'],observed):
        op=tx['op'];data=bytes.fromhex(tx['payload_hex']);assert rc==tx['rc'] and answer.hex()==tx['reply_hex']
        if op=='I':
            boot=Bootstrap(1,psk,aid,bid,16,nonce_source=lambda n,nonce=data:nonce);session.reset();active=key_valid=0;assert (rc,answer)==(0,b'')
        elif op=='R':
            boot.abort();session.reset();active=key_valid=0;assert (rc,answer)==(0,b'')
        elif op=='H':
            active=key_valid=0;session.reset();assert rc==0 and answer==boot.server_hello(data)
        elif op=='F':
            expected=boot.server_finished(data);session=boot.take_provisioning().open_pc_session();assert (rc,answer)==(0,expected)
        elif op=='G':assert (rc,answer)==(0,struct.pack('<5I',dispatches,used,active,key_valid,1))
        elif op=='D':
            try:opcode,payload=session.unwrap(data)
            except SessionError as exc:
                assert rc==int(exc.status) and not answer
                rejects[str(rc)]=rejects.get(str(rc),0)+1;continue
            assert rc==0 and opcode==0x100 and len(payload)%4==0
            words=list(struct.unpack('<'+'I'*(len(payload)//4),payload));cmd=words[0];dispatches+=1
            # Recompute the complete Bob response frame, including seq and MAC.
            assert answer==session.wrap(0x8100,answer[32:-8]);text=answer[32:-8].decode('ascii');seq=session.rx_last
            if cmd==10:
                matches=[f for f in result['fixtures'] if f['load']==words];assert len(matches)==1;current=matches[0]
                campaign=ROOT/'build/zc702/uart_csv_nms_gs'/current['record']['file']
                assert hashlib.sha256(campaign.read_bytes()).hexdigest()==current['record']['sha256']
                assert text.strip()==f'QKD_FUNC_LOADED seq={seq}'
                attempt=0;active=1;key_valid=0;actual_key=None
            elif cmd==11:
                expected=current['expected'][attempt];attempt+=1
                m=re.fullmatch(fr'QKD_FUNC_ATTEMPT seq={seq} status=([0-9a-f]+) iters=([0-9a-f]+) errcnt=(\d+) cycles=(\d+) ticks=(\d+)\s*',text)
                assert m;status,iters,err=int(m[1],16),int(m[2],16),int(m[3])
                assert status&0x0fff0033==((1 if expected>>31 else 2)|((expected>>28)&3)<<4|(expected&0x0fff0000)) and iters&4095==expected&4095
                if expected>>31:assert err==current['err'];active=0;key_valid=1
            elif cmd==12:
                assert text.strip()==f'QKD_FUNC_REVEALED seq={seq} count={words[1]}'
                cursor=current['pre']+sum(current['counts'][:attempt-1]);count=current['counts'][attempt-1]
                assert words[1:]==[count,*current['reveals'][cursor:cursor+count]]
            elif cmd==14:
                values=re.findall(fr'QKD_FUNC_KEY seq={seq} word=(\d+) value=([0-9a-f]{{16}})',text)
                assert [int(i) for i,_ in values]==list(range(48));actual_key=[int(v,16) for _,v in values]
                assert actual_key==current['key']
            elif cmd==20:
                assert words==current['pipe'] and actual_key is not None
                bits=np.unpackbits(np.frombuffer(struct.pack('<48Q',*actual_key),dtype=np.uint8),bitorder='little')
                keep=np.ones(3072,dtype=bool);positions=words[2:309];assert len(set(positions))==307;keep[positions]=False
                tag=keyhash(bits[keep],words[309:429])[0];assert tag==words[429]|words[430]<<32
                expected_pa=keyhash(bits[keep],words[431:551])
                values=re.findall(fr'QKD_FUNC_PA seq={seq} word=(\d+) value=([0-9a-f]{{16}})',text)
                assert [int(i) for i,_ in values]==list(range(16));actual_pa=[int(v,16) for _,v in values]
                assert actual_pa==expected_pa==current['pa']
                assert f'QKD_FUNC_PIPE_PASS seq={seq} input_bits=2765 output_bits=1024' in text
                used+=1;key_valid=0
                rows.append(dict(code=current['code'],attempts=attempt,key_SHA256=hashlib.sha256(struct.pack('<48Q',*actual_key)).hexdigest(),
                                 PA_SHA256=hashlib.sha256(struct.pack('<16Q',*actual_pa)).hexdigest(),verification_used=used,
                                 KEY_and_PA_bit_exact=True,scope='Public fixture, per-block PA1024, MAC-only lab channel'))
            elif cmd==73:assert text.strip()==f'QKD_FUNC_BUDGET_STATE seq={seq} used={used} limit=18446 remaining={18446-used}'
            else:raise AssertionError(cmd)
        else:raise AssertionError(op)
    assert [r['code'] for r in rows]==['r12','r23','r34','r56'] and used==4 and len(result['checks'])==78
    report=ROOT/'reports'/('zc702_secure_app_'+result['started_utc']);report.mkdir(exist_ok=True)
    with (report/'blocks.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    proof=dict(raw_replay_verified=True,source_result_sha256=hashlib.sha256(raw).hexdigest(),
               uart_sha256=hashlib.sha256((run/'uart.log').read_bytes()).hexdigest(),commands_verified=len(observed),
               authenticated_dispatches=dispatches,blocks=4,verification_used=4,rejections=rejects,
               KEY_matches_frozen_golden_and_PA_recomputed_from_actual_KEY=True,baseline_restored=True,
               metadata_note='Raw blocks.input_key_words is a mislabeled PA-output list; authoritative KEY/PA are reconstructed from MAC-covered responses; blocks.csv uses correct hashes.',
               scope='Real PL IR/per-block PA behind QAS2 MAC in public-fixture lab ELF; no confidentiality, trusted provisioning, durable accounting or production security certification')
    (report/'verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
    job=json.loads((ROOT/'RUNNING_JOBS.json').read_text())
    if job.get('run_directory')==run.relative_to(ROOT).as_posix():
        job.update(status='VERIFIED_COMPLETE',report=(report/'verified_evidence.json').relative_to(ROOT).as_posix())
        write_checkpoint(ROOT/'RUNNING_JOBS.json',job)
    print('SECURE_APP_RAW_REPLAY_PASS',len(observed),'commands',dispatches,'authenticated application dispatches')

if __name__=='__main__':main()
