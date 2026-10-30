"""Real PL IR/PA fixture commands behind QAS2 MAC, separate lab ELF and baseline restore."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,random,re,struct,subprocess,sys,time
import numpy as np
import serial
from qas2_bootstrap import Bootstrap
from qas2_pc import Status
from uart_session import UARTSession
from checkpoint_io import write_checkpoint
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
import ir_model as ir
import puncture as pu
import pa_model as pa

def fixtures():
    directory=ROOT/'build/zc702/uart_csv_nms_gs';campaign=json.loads((directory/'campaign.json').read_text())
    result=[];rng=np.random.default_rng(2026102705);codes=ir.load_codes(128)
    for code in ir.CODE_ORDER:
        candidates=[r for r in campaign['records'] if r['code']==code and r['model_outcome']=='SUCCESS']
        record=next((r for r in candidates if 1<r['attempts']<=3),candidates[0])
        raw=(directory/record['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==record['sha256']
        v=list(struct.unpack('<'+'I'*(len(raw)//4),raw));cfg,cfg2,pre,att,ns,err,nrev=v[:7];at=7+2*att
        expected=v[7:7+att];counts=v[7+att:7+2*att];ch=v[at:at+192];at+=192;syn=v[at:at+ns];at+=ns
        reveals=v[at:at+nrev];at+=nrev;key=[v[i]|v[i+1]<<32 for i in range(at,len(v),2)]
        positions=list(map(int,pu.order(code,codes[code],128,307)));keep=np.ones(3072,dtype=bool);keep[positions]=False
        bits=np.unpackbits(np.frombuffer(struct.pack('<48Q',*key),dtype=np.uint8),bitorder='little');x=np.pad(bits[keep],(0,19))
        seeds=[list(map(int,rng.integers(0,2**32,120,dtype=np.uint32))) for _ in range(2)];outputs=[]
        for seed in seeds:
            sb=np.unpackbits(np.frombuffer(struct.pack('<120I',*seed),dtype=np.uint8),bitorder='little')
            outputs.append(list(map(int,np.frombuffer(np.packbits(pa.pa_hash(x,sb),bitorder='little').tobytes(),dtype='<u8'))))
        tag=outputs[0][0];expected32=[part for word in outputs[1] for part in [word&0xffffffff,word>>32]]
        result.append(dict(code=code,record=record,load=[10,cfg,cfg2,ns,pre,*ch,*syn,*reveals[:pre]],
                           expected=expected,counts=counts,reveals=reveals,pre=pre,err=err,key=key,pa=outputs[1],
                           pipe=[20,cfg&3,*positions,*seeds[0],tag&0xffffffff,tag>>32,*seeds[1],*expected32]))
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--build',required=True,type=Path);ap.add_argument('--port',default='COM3')
    args=ap.parse_args();build=args.build.resolve();manifest=json.loads((build/'manifest.json').read_text())
    for name,sha in manifest['source_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha,name
    elf=ROOT/manifest['elf'];assert hashlib.sha256(elf.read_bytes()).hexdigest()==manifest['elf_sha256']
    selected=fixtures();stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');folder=ROOT/'build/zc702/secure_app_runs'/stamp;folder.mkdir(parents=True)
    (folder/'runner_at_execution.py').write_bytes(Path(__file__).read_bytes())
    result=dict(complete=False,hardware_capture=True,started_utc=stamp,build_manifest=manifest,fixtures=selected,tx=[],checks=[],blocks=[],
        scope='Real PL IR/PA with MAC-gated lab dispatcher; public root/test data/seeds and host nonce; plaintext lab reset/provision and debug KEY; not confidential or production secure channel')
    def save():write_checkpoint(folder/'result.json',result)
    save();write_checkpoint(ROOT/'RUNNING_JOBS.json',dict(status='RUNNING',pid=os.getpid(),port=args.port,port_released=False,script='syn/zc702/run_secure_app_board.py',run_directory=folder.relative_to(ROOT).as_posix()))
    uart=None;process=None;programmed=False
    try:
        uart=serial.Serial(args.port,115200,timeout=.1,write_timeout=20);log=(folder/'uart.log').open('wb');xlog=(folder/'xsct.log').open('wb')
        def line(timeout=20):
            data=bytearray();deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                chunk=uart.read(1)
                if chunk:log.write(chunk);log.flush();data.extend(chunk)
                if chunk==b'\n':return data.decode('ascii',errors='replace').strip()
            raise TimeoutError('UART response')
        uart.reset_input_buffer();process=subprocess.Popen(['D:/Xilinx/Vitis/2020.2/bin/xsct.bat',str(ROOT/'syn/zc702/program_bootstrap.tcl'),str(elf)],cwd=ROOT,stdout=xlog,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);programmed=True
        assert line(120)=='SA_READY kat=PASS fixture=PUBLIC'
        process.wait(timeout=30);xlog.flush();assert process.returncode==0 and 'ZC702_PROGRAM_MMIO_PASS' in (folder/'xsct.log').read_text(errors='replace')
        def command(op,payload=b''):
            result['tx'].append(dict(op=op,payload_hex=payload.hex()))
            uart.write((op+(' '+payload.hex() if op!='R' else '')+'\n').encode())
            parts=line().split();assert parts[0]=='QB'
            rc=int(parts[1]);data=bytes.fromhex(parts[2]) if len(parts)==3 else b''
            result['tx'][-1].update(rc=rc,reply_hex=data.hex());save();return rc,data
        def check(value,label):assert value,label;result['checks'].append(label);save()
        def diag():
            rc,data=command('G');assert rc==0;return struct.unpack('<5I',data)
        rng=random.Random(2026102705);old_frame=None;verified=0
        for f in selected:
            nonce_a=rng.randbytes(32);nonce_b=rng.randbytes(32);psk=bytes(range(1,33));aid=bytes(range(1,17));bid=bytes(range(17,33))
            a=Bootstrap(0,psk,aid,bid,100,lambda n:nonce_a);b=Bootstrap(1,psk,aid,bid,16,lambda n:nonce_b)
            assert command('I',nonce_b)==(0,b'');ch=a.client_hello();rc,sh=command('H',ch);assert rc==0 and sh==b.server_hello(ch)
            cf=a.client_finished(sh);rc,sf=command('F',cf);assert rc==0 and sf==b.server_finished(cf);a.accept_server_finished(sf)
            alice=a.take_provisioning().open_pc_session();start=diag();check(start[1]==verified and start[2:]==(0,0,1),'new_session_wiped_staging_no_budget_refund')
            def send(values,tamper=False,replay=False):
                payload=struct.pack('<'+'I'*len(values),*values);seq=alice.tx_next;packet=alice.wrap(0x100,payload)
                if tamper:
                    before=diag();bad=bytearray(packet);bad[-1]^=1
                    check(command('D',bytes(bad))[0]==Status.BAD_TAG,'bad_mac_rejected')
                    check(diag()==before,'bad_mac_no_dispatch_or_state_change')
                rc,answer=command('D',packet);assert rc==0,(f['code'],values[0],rc)
                opcode,text=alice.unwrap(answer);assert opcode==0x8100
                if replay:
                    before=diag();check(command('D',packet)[0]==Status.REPLAY,'replay_rejected');check(diag()==before,'replay_no_dispatch_or_state_change')
                return seq,text.decode('ascii'),packet
            if old_frame is not None:
                before=diag();check(command('D',old_frame)[0]==Status.SESSION,'old_sid_rejected');check(diag()==before,'old_sid_no_dispatch')
            seq,text,old_frame=send(f['load'],tamper=True,replay=True);check(f'QKD_FUNC_LOADED seq={seq}' in text,'authenticated_load')
            cursor=f['pre']
            for index,expected in enumerate(f['expected']):
                seq,text,_=send([11],tamper=index==0)
                found=re.search(r'status=([0-9a-fA-F]+) iters=([0-9a-fA-F]+) errcnt=(\d+)',text);assert found,text
                status,iters,err=int(found[1],16),int(found[2],16),int(found[3])
                check(status&0x0fff0033==((1 if expected>>31 else 2)|((expected>>28)&3)<<4|(expected&0x0fff0000)) and iters&4095==expected&4095,'decode_trace_matches')
                if expected>>31:check(err==f['err'],'error_count_matches');break
                count=f['counts'][index];seq,text,_=send([12,count,*f['reveals'][cursor:cursor+count]]);cursor+=count
                check(f'count={count}' in text,'authenticated_reveal')
            seq,text,_=send([14]);actual=[int(v,16) for v in re.findall(r'value=([0-9a-fA-F]{16})',text)]
            check(actual==f['key'],'actual_PL_key_matches')
            seq,text,_=send(f['pipe'],tamper=True);actual=[int(v,16) for v in re.findall(r'value=([0-9a-fA-F]{16})',text)]
            check(actual==f['pa'] and 'QKD_FUNC_PIPE_PASS' in text,'actual_PL_PA_matches')
            verified+=1;end=diag();check(end[1]==verified and end[3]==0 and end[4]==1,'verification_charged_once')
            seq,text,_=send([73]);check(f'used={verified} limit=18446' in text,'authenticated_budget_query')
            result['blocks'].append(dict(code=f['code'],input_key_words=actual,verification_used=verified,key_match=True,pa_match=True));save()
            print('SECURE_APP_BLOCK_PASS',f['code'],'attempts',len(f['expected']),flush=True)
        before=diag();check(command('D',struct.pack('<I',10))[0]==Status.FORMAT,'plaintext_app_command_rejected');check(diag()==before,'plaintext_no_dispatch')
        assert command('R')==(0,b'');check(command('D',old_frame)[0]==Status.CLOSED,'reset_closes_authenticated_application')
        check(diag()[1]==verified,'reset_does_not_refund_verification')
        result['functional_tests_complete']=True
    except BaseException as exc:result['error']=repr(exc);raise
    finally:
        if process is not None and process.poll() is None:process.terminate()
        if uart is not None:uart.close()
        if programmed:
            try:
                with UARTSession(folder/'baseline_restore',args.port) as restored:result['baseline_restored']=True;result['baseline_manifest']=restored.manifest
            except BaseException as exc:result['restore_error']=repr(exc)
        result['complete']=bool(result.get('functional_tests_complete') and result.get('baseline_restored') and not result.get('error'));save()
        write_checkpoint(ROOT/'RUNNING_JOBS.json',dict(status='COMPLETED_PENDING_RAW_VERIFICATION' if result['complete'] else 'STOPPED_ERROR',script='syn/zc702/run_secure_app_board.py',run_directory=folder.relative_to(ROOT).as_posix(),port=args.port,port_released=True,baseline_restored=result.get('baseline_restored',False)))
        print('SECURE_APP_EVIDENCE',folder,flush=True)
    assert result['complete'];print('SECURE_APP_BOARD_PASS',len(result['checks']),'checks',flush=True)

if __name__=='__main__':main()
