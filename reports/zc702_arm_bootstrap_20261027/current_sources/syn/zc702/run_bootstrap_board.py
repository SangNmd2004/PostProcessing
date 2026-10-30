"""LAB-ONLY COM3 test: public-fixture bootstrap ELF, then restore baseline UART ELF."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,random,subprocess,time
import serial
from qas2_bootstrap import Bootstrap
from qas2_pc import Status
from uart_session import UARTSession
from checkpoint_io import write_checkpoint
ROOT=Path(__file__).resolve().parents[2]

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--build',type=Path,required=True)
    ap.add_argument('--port',default='COM3');args=ap.parse_args()
    build=args.build.resolve();manifest=json.loads((build/'manifest.json').read_text())
    for file,sha in manifest['source_sha256'].items():assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==sha,file
    elf=ROOT/manifest['elf'];assert hashlib.sha256(elf.read_bytes()).hexdigest()==manifest['elf_sha256']
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');folder=ROOT/'build/zc702/bootstrap_board_runs'/stamp;folder.mkdir(parents=True)
    (folder/'runner_at_execution.py').write_bytes(Path(__file__).read_bytes())
    result=dict(complete=False,hardware_capture=True,started_utc=stamp,build_manifest=manifest,checks=[],tx=[],
                scope='Real Cortex-A9 fixture test; unchanged 50MHz PL; plaintext lab reset/provision, public PSK and host nonce; not production channel or durable security')
    def save():write_checkpoint(folder/'result.json',result)
    save();uart=None;process=None;programmed=False
    write_checkpoint(ROOT/'RUNNING_JOBS.json',dict(status='RUNNING',pid=os.getpid(),script='syn/zc702/run_bootstrap_board.py',
                     run_directory=folder.relative_to(ROOT).as_posix(),port=args.port,port_released=False))
    try:
        uart=serial.Serial(args.port,115200,timeout=.1,write_timeout=20)
        log=(folder/'uart.log').open('wb');xlog=(folder/'xsct.log').open('wb')
        def line(timeout=20):
            data=bytearray();deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                chunk=uart.read(1)
                if chunk:log.write(chunk);log.flush();data.extend(chunk)
                if chunk==b'\n':return data.decode('ascii',errors='replace').strip()
            raise TimeoutError('UART reply incomplete')
        uart.reset_input_buffer()
        process=subprocess.Popen(['D:/Xilinx/Vitis/2020.2/bin/xsct.bat',str(ROOT/'syn/zc702/program_bootstrap.tcl'),str(elf)],
                                 cwd=ROOT,stdout=xlog,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        programmed=True
        ready=line(120);assert ready=='QB_READY kat=PASS fixture=PUBLIC',ready
        process.wait(timeout=30);xlog.flush();assert process.returncode==0
        assert 'ZC702_PROGRAM_MMIO_PASS' in (folder/'xsct.log').read_text(errors='replace')
        def command(op,data=b''):
            raw=(op+(' '+data.hex() if op!='R' else '')+'\n').encode()
            result['tx'].append(dict(op=op,payload_hex=data.hex()));uart.write(raw)
            answer=line();parts=answer.split();assert len(parts)>=2 and parts[0]=='QB',answer
            return int(parts[1]),bytes.fromhex(parts[2]) if len(parts)==3 else b''
        def check(ok,name):
            assert ok,name;result['checks'].append(name);save()
        psk=bytes(range(1,33));aid=bytes(range(1,17));bid=bytes(range(17,33));rng=random.Random(2026102704)
        def init_pair():
            na=rng.randbytes(32);nb=rng.randbytes(32);assert command('I',nb)==(0,b'')
            return Bootstrap(0,psk,aid,bid,100,lambda n:na),Bootstrap(1,psk,aid,bid,16,lambda n:nb)
        def handshake():
            a,b=init_pair();ch=a.client_hello();rc,sh=command('H',ch)
            check(rc==0 and sh==b.server_hello(ch),'server_hello_exact')
            cf=a.client_finished(sh);rc,sf=command('F',cf)
            check(rc==0 and sf==b.server_finished(cf),'server_finished_exact')
            a.accept_server_finished(sf);return a.take_provisioning().open_pc_session()
        old_frame=None
        for i in range(20):
            alice=handshake();size=[0,1,7,8,31,128,1024,4096,16384][i%9];payload=rng.randbytes(size)
            frame=alice.wrap(0x1234,payload);rc,reply=command('D',frame)
            check(rc==0 and alice.unwrap(reply)==(0x9234,payload),f'authenticated_echo_{i}_bytes_{size}')
            check(command('D',frame)[0]==Status.REPLAY,'data_replay_rejected')
            if old_frame is not None:check(command('D',old_frame)[0]==Status.SESSION,'old_session_rejected')
            old_frame=frame
        for kind,offsets in [('ch',[0,4,5,37,69,104]),('cf',[0,4,5,36,37,68])]:
            for at in offsets:
                a,b=init_pair();ch=a.client_hello()
                if kind=='ch':
                    bad=bytearray(ch);bad[at]^=1;check(command('H',bytes(bad))[0]!=0,'bad_client_hello_rejected')
                else:
                    rc,sh=command('H',ch);assert rc==0;cf=bytearray(a.client_finished(sh));cf[at]^=1
                    check(command('F',bytes(cf))[0]!=0,'bad_client_finished_rejected')
                check(command('D',old_frame)[0]==Status.CLOSED,'failed_handshake_keeps_data_closed')
        alice=handshake();frame=alice.wrap(20,b'public tag-negative fixture');bad=bytearray(frame);bad[-1]^=1
        check(command('D',bytes(bad))[0]==Status.BAD_TAG,'bad_tag_consumes_check')
        rc,reply=command('D',frame);check(rc==0 and alice.unwrap(reply)==(0x8014,b'public tag-negative fixture'),'valid_retry_after_bad_tag')
        check(command('D',reply)[0]==Status.DIRECTION,'reflection_rejected')
        check(command('R')==(0,b''),'reset_command')
        check(command('D',frame)[0]==Status.CLOSED,'reset_closes_data')
        alice=handshake();frame=alice.wrap(1,b'budget');bad=bytearray(frame);bad[-1]^=1
        for _ in range(16):check(command('D',bytes(bad))[0]==Status.BAD_TAG,'failed_mac_charged')
        check(command('D',frame)[0]==Status.EXHAUSTED,'mac_budget_exhausted')
        result['functional_tests_complete']=True
    except BaseException as exc:
        result['error']=repr(exc);raise
    finally:
        if process is not None and process.poll() is None:process.terminate()
        if uart is not None:uart.close()
        if programmed:
            try:
                with UARTSession(folder/'baseline_restore',args.port) as restored:
                    result['baseline_restored']=True
                    result['baseline_firmware_manifest']=restored.manifest
            except BaseException as exc:result['restore_error']=repr(exc)
        result['complete']=bool(result.get('functional_tests_complete') and result.get('baseline_restored') and not result.get('error'))
        save()
        write_checkpoint(ROOT/'RUNNING_JOBS.json',dict(status='COMPLETED_PENDING_RAW_VERIFICATION' if result['complete'] else 'STOPPED_ERROR',
                         pid=os.getpid(),script='syn/zc702/run_bootstrap_board.py',run_directory=folder.relative_to(ROOT).as_posix(),
                         port=args.port,port_released=True,baseline_restored=result.get('baseline_restored',False)))
        print('BOOTSTRAP_BOARD_EVIDENCE',folder,flush=True)
    assert result['complete'],result
    print('BOOTSTRAP_BOARD_TEST_PASS',len(result['checks']),'checks; baseline restored',flush=True)

if __name__=='__main__':main()
