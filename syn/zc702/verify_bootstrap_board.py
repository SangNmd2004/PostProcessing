"""Replay every lab command against independent Python bootstrap/QAS2 models."""
from pathlib import Path
import argparse,hashlib,json,re
from checkpoint_io import write_checkpoint
from qas2_bootstrap import Bootstrap,BootstrapError
from qas2_pc import Session,SessionError
ROOT=Path(__file__).resolve().parents[2]

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path)
    args=ap.parse_args();run=args.run.resolve();result=json.loads((run/'result.json').read_text())
    assert result['complete'] and result['hardware_capture'] and result['baseline_restored'] and not result.get('error')
    manifest=result['build_manifest'];elf=ROOT/manifest['elf'];assert hashlib.sha256(elf.read_bytes()).hexdigest()==manifest['elf_sha256']
    build=elf.parent
    for name,sha in manifest['source_sha256'].items():
        snapshot=build/'source_snapshot'/name
        candidate=snapshot if snapshot.exists() else ROOT/name
        assert hashlib.sha256(candidate.read_bytes()).hexdigest()==sha,name
    uart=(run/'uart.log').read_text();xsct=(run/'xsct.log').read_text(errors='replace')
    assert 'QB_READY kat=PASS fixture=PUBLIC' in uart
    assert 'ZC702_PROGRAM_MMIO_PASS' in xsct and 'ZC702_SMOKE_CPU_STARTED' in xsct
    assert not re.search(r'FATAL|TIMEOUT|MISMATCH',uart)
    restore=run/'baseline_restore'
    assert 'QKD_UART_READY version=1 max_words=4096' in (restore/'uart.log').read_text()
    assert 'ZC702_PROGRAM_MMIO_PASS' in (restore/'xsct.log').read_text(errors='replace')
    assert json.loads((restore/'firmware_manifest.json').read_text())==result['baseline_firmware_manifest']
    for file,sha in result['baseline_firmware_manifest']['files'].items():assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==sha,file
    lines=[line.strip().split() for line in uart.splitlines() if line.startswith('QB ')]
    assert len(lines)==len(result['tx'])
    psk=bytes(range(1,33));aid=bytes(range(1,17));bid=bytes(range(17,33));boot=None;session=Session()
    outcomes={};handshakes=0;echoes=0
    for tx,line in zip(result['tx'],lines):
        observed=(int(line[1]),bytes.fromhex(line[2]) if len(line)==3 else b'')
        op=tx['op'];data=bytes.fromhex(tx['payload_hex'])
        if op=='I':
            assert len(data)==32
            boot=Bootstrap(1,psk,aid,bid,16,nonce_source=lambda n,nonce=data:nonce);session.reset();expected=(0,b'')
        elif op=='R':
            if boot:boot.abort()
            session.reset();expected=(0,b'')
        elif op=='H':
            session.reset()
            try:expected=(0,boot.server_hello(data))
            except BootstrapError:expected=(-1,b'')
        elif op=='F':
            try:
                sf=boot.server_finished(data);session=boot.take_provisioning().open_pc_session()
                expected=(0,sf);handshakes+=1
            except BootstrapError:session.reset();expected=(-1,b'')
        elif op=='D':
            try:
                opcode,payload=session.unwrap(data);expected=(0,session.wrap(opcode^0x8000,payload));echoes+=1
            except SessionError as exc:expected=(int(exc.status),b'')
        else:raise AssertionError('Unknown captured command')
        assert observed==expected,(op,observed[0],expected[0])
        key=f'{op}:{observed[0]}';outcomes[key]=outcomes.get(key,0)+1
    assert handshakes==22 and echoes==21 and len(result['checks'])==149
    report=ROOT/'reports'/('zc702_bootstrap_board_'+result['started_utc']);report.mkdir(exist_ok=True)
    proof=dict(raw_replay_verified=True,hardware_capture=True,raw_commands_verified=len(lines),
               handshakes=handshakes,authenticated_echoes=echoes,runner_checks=149,outcomes=outcomes,
               source_result_sha256=hashlib.sha256((run/'result.json').read_bytes()).hexdigest(),
               uart_sha256=hashlib.sha256((run/'uart.log').read_bytes()).hexdigest(),
               runner_at_execution_sha256=hashlib.sha256((run/'runner_at_execution.py').read_bytes()).hexdigest(),
               baseline_restored=True,scope='Real ARM/UART lab fixture with public PSK, host nonce and plaintext reset/provision; not secure enrollment/entropy/durable accounting or IR-PA authenticated integration')
    (report/'verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
    job_path=ROOT/'RUNNING_JOBS.json'
    if job_path.exists():
        job=json.loads(job_path.read_text())
        if job.get('run_directory')==run.relative_to(ROOT).as_posix():
            job.update(status='VERIFIED_COMPLETE',port_released=True,baseline_restored=True,
                       report=(report/'verified_evidence.json').relative_to(ROOT).as_posix())
            write_checkpoint(job_path,job)
    print('BOOTSTRAP_BOARD_RAW_REPLAY_PASS',report,len(lines),'commands')

if __name__=='__main__':main()
