"""Physical PUBLIC-fixture QAS2 accumulator test; always attempt baseline restore."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, random, re, struct, subprocess, time
import serial
from run_secure_app_board import fixtures
from qas2_bootstrap import Bootstrap
from checkpoint_io import write_checkpoint
from uart_session import UARTSession

ROOT=Path(__file__).resolve().parents[2]
def packed(w):return struct.pack('<'+'I'*len(w),*w)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--build',type=Path,required=True);ap.add_argument('--port',default='COM3');args=ap.parse_args()
    build=args.build.resolve();manifest=json.loads((build/'manifest.json').read_text());assert manifest['accumulator']
    for n,h in manifest['source_sha256'].items():assert sha(ROOT/n)==h,n
    for n,h in manifest['generated_files_sha256'].items():assert sha(build/n)==h,n
    assert sha(ROOT/manifest['elf'])==manifest['elf_sha256']
    job=json.loads((ROOT/'RUNNING_JOBS.json').read_text());assert job['status'] not in ['RUNNING','COMPLETED_PENDING_RAW_VERIFICATION'],job
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'build/zc702/secure_accumulator_runs'/stamp;out.mkdir(parents=True,exist_ok=False)
    selected=fixtures();f=selected[-1];rng=random.Random(2026110201)
    result=dict(complete=False,started_utc=stamp,build_manifest=manifest,fixtures=selected,seed=2026110201,
                metadata_kind='synthetic assigned per authenticated fixture block; no optical/FER/security claim',checks=[],commands=0)
    for name in [Path(__file__),ROOT/'syn/zc702/run_secure_app_board.py',ROOT/'syn/zc702/qas2_pc.py',ROOT/'syn/zc702/qas2_bootstrap.py']:
        dest=out/'source_snapshot'/name.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(name.read_bytes())
    def save():write_checkpoint(out/'result.json',result)
    def status(s,**kw):write_checkpoint(ROOT/'RUNNING_JOBS.json',dict(status=s,script='syn/zc702/run_secure_accumulator_board.py',pid=os.getpid(),run_directory=out.relative_to(ROOT).as_posix(),port=args.port,**kw))
    save();status('RUNNING',port_released=False)
    uart=process=log=xlog=txlog=None;programmed=False
    try:
        uart=serial.Serial(args.port,115200,timeout=.1,write_timeout=20)
        log=(out/'uart.log').open('wb');xlog=(out/'xsct.log').open('wb');txlog=(out/'tx.jsonl').open('w',encoding='utf-8')
        def line(timeout=30):
            data=bytearray();deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                chunk=uart.read(1)
                if chunk:log.write(chunk);data.extend(chunk)
                if chunk==b'\n':log.flush();return data.decode('ascii').strip()
            log.flush();raise TimeoutError('UART line')
        uart.reset_input_buffer();process=subprocess.Popen(['D:/Xilinx/Vitis/2020.2/bin/xsct.bat',str(ROOT/'syn/zc702/program_bootstrap.tcl'),str(ROOT/manifest['elf'])],cwd=ROOT,stdout=xlog,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);programmed=True
        assert line(120)=='SA_READY kat=PASS fixture=PUBLIC';process.wait(timeout=30);xlog.flush();assert process.returncode==0
        def command(op,data=b'',label=''):
            txlog.write(json.dumps(dict(op=op,payload_hex=data.hex(),label=label))+'\n');txlog.flush()
            uart.write((op+(' '+data.hex() if op!='R' else '')+'\n').encode())
            parts=line().split();assert parts[0]=='QB';result['commands']+=1
            return int(parts[1]),bytes.fromhex(parts[2]) if len(parts)==3 else b''
        def check(value,label):
            assert value,label;result['checks'].append(label)
        def diag():
            rc,data=command('G');assert rc==0;return struct.unpack('<5I',data)
        alice=None;last_packet=None
        def open_session(limit=10000):
            nonlocal alice
            na=rng.randbytes(32);nb=rng.randbytes(32);psk=bytes(range(1,33));aid=bytes(range(1,17));bid=bytes(range(17,33))
            a=Bootstrap(0,psk,aid,bid,limit,lambda n:na);b=Bootstrap(1,psk,aid,bid,10000,lambda n:nb)
            assert command('I',nb)==(0,b'');ch=a.client_hello();rc,sh=command('H',ch);assert rc==0 and sh==b.server_hello(ch)
            cf=a.client_finished(sh);rc,sf=command('F',cf);assert rc==0 and sf==b.server_finished(cf);a.accept_server_finished(sf);alice=a.take_provisioning().open_pc_session()
        def send(w,label='',reject=False):
            nonlocal last_packet
            packet=alice.wrap(0x100,packed(w));last_packet=packet
            rc,data=command('D',packet,label);assert rc==0,(w[0],rc)
            op,text=alice.unwrap(data);assert op==0x8100;text=text.decode('ascii')
            check(('QKD_SECURE_REJECT' in text)==reject,label or 'application_response')
            return text
        def negative(w,label):
            before=diag();send(w,label,True);check(diag()==before,label+'_no_app_change')
        def state():
            text=send([67]);m=re.search(r'bits=(\d+) next_id=(\d+) pending=(\d+) out_bits=(\d+)',text);assert m;return tuple(map(int,m.groups()))
        def reset(label):
            used=diag()[1];assert command('R')==(0,b'');check(diag()[1]==used,label+'_budget_preserved');open_session();check(state()==(0,0,0,0),label+'_staging_cleared');send([69],label+'_wipe_crc')
        def ingest(index,bad=False,negative_cases=False,nt_bad=False,exhausted=False):
            meta=[index,2570,190,5,2607,135,4,*([1300,100,3] if nt_bad else [0,0,0]),index]
            load=[80,*meta,*f['load'][1:]]
            if negative_cases:
                negative(load[:-1],'short_load');negative(load+[0],'long_load')
                wrong=load.copy();wrong[1]+=1;negative(wrong,'wrong_block_load')
                wrong=load.copy();wrong[8]=2608;negative(wrong,'invalid_metadata_error_counts')
                negative([68,0,1],'debug_buffer_not_allowlisted')
            send(load,'bound_load')
            if negative_cases:negative([60,*meta,*f['pipe'][309:431]],'append_before_decode')
            cursor=f['pre']
            for i,expected in enumerate(f['expected']):
                text=send([11],'ir_attempt');assert 'QKD_FUNC_ATTEMPT' in text
                if expected>>31:break
                count=f['counts'][i];send([12,count,*f['reveals'][cursor:cursor+count]],'ir_reveal');cursor+=count
            text=send([14],'key_read_existing_lab_api');actual=[int(x,16) for x in re.findall(r'value=([0-9a-f]{16})',text)];assert actual==f['key']
            append=[60,*meta,*f['pipe'][309:431]];assert len(append)==134
            if negative_cases:
                negative(append[:-1],'short_append');negative(append+[0],'long_append')
                wrong=append.copy();wrong[1]+=1;negative(wrong,'wrong_block_append')
                wrong=append.copy();wrong[5]+=1;negative(wrong,'changed_metadata_append')
                packet=alice.wrap(0x100,packed(append));corrupt=bytearray(packet);corrupt[-1]^=1;before=diag()
                check(command('D',bytes(corrupt),'bad_mac_append')[0]==-7,'bad_mac_append');check(diag()==before,'bad_mac_no_application_effect')
                check(command('D',packet[:-1],'truncated_frame')[0]==-3,'truncated_frame')
            if bad:append[132]^=1
            text=send(append,'bad_tag' if bad else 'append_verified')
            if bad:assert 'TAG_REJECT' in text
            elif exhausted:assert 'VERIFY_LIMIT' in text
            else:assert 'QKD_STREAM_ADDED' in text
            if negative_cases:
                before=diag();check(command('D',last_packet,'append_replay')[0]==-6,'append_replay');check(diag()==before,'replay_no_application_effect');negative(append,'duplicate_append')
            return text
        def decide(at):
            text=send([62,at],'finite_key_decision');m=re.search(r'action=(\d+) bits=(\d+) ell=(\d+) split=(\d+) emit_bits=(\d+) seed_words=(\d+)',text);assert m;return tuple(map(int,m.groups()))
        def emit(decision):
            action,bits,ell,split,emit_bits,ns=decision;assert action==1
            negative([64],'emit_before_seed')
            seed=[rng.getrandbits(32) for _ in range(ns)]
            negative([63,ns,1,1,seed[0]],'seed_wrong_offset')
            for offset in range(0,ns,4000):
                part=seed[offset:offset+4000];send([63,ns,offset,len(part),*part],'seed_chunk')
            send([64],'emit_complete')
            negative([65,0,129],'oversized_output_read')
            for offset in range(0,ell//64,128):send([65,offset,min(128,ell//64-offset)],'authenticated_output')
            send([82],'tail_digest');send([66],'clear_output')
            return bits-emit_bits
        open_session();send([69],'initial_wipe')
        # Reset before decode, after decode, and after append. Same-boot budget is retained.
        send([80,0,2570,190,5,2607,135,4,0,0,0,0,*f['load'][1:]],'reset_load');reset('reset_active')
        send([80,0,2570,190,5,2607,135,4,0,0,0,0,*f['load'][1:]],'reset_load');send([11]);reset('reset_decoded')
        ingest(0,negative_cases=True);old=last_packet;reset('reset_appended');check(command('D',old,'old_sid')[0]==-4,'old_sid')
        ingest(0,bad=True);send([81],'abort_after_tag_reject');send([69],'abort_wipe')
        reset('before_emit')
        for i in range(40):
            ingest(i)
            if (i+1)%10==0:print('SECURE_ACC_PROGRESS normal_emit',i+1,flush=True)
        normal=decide(3600);check(normal[0]==1 and normal[3]==0,'normal_emit_decision');check(emit(normal)==0,'normal_emit_no_tail')
        reset('reset_output_cleared')
        # Split snapshot frozen before deliberately bad synthetic metadata is appended.
        for i in range(90):
            ingest(i)
            if (i+1)%10==0:print('SECURE_ACC_PROGRESS split_prefix',i+1,flush=True)
        best=decide(90);check(best[0]==0,'best_prefix_wait')
        for i in range(90,130):
            ingest(i,nt_bad=True);decision=decide(i)
            if decision[0]==1:break
        check(decision[0]==1 and decision[3]==1,'split_decision');tail=emit(decision);check(tail>0,'split_retains_tail')
        send([81],'abort_tail');send([69],'abort_tail_wipe');send([82],'empty_digest')
        # Reset while a seed is partially staged (small normal-emission fixture).
        reset('before_pending_reset')
        for i in range(40):ingest(i)
        pending=decide(3600);assert pending[0]==1
        send([63,pending[-1],0,1,rng.getrandbits(32)],'partial_seed');reset('reset_partial_seed')
        # Shared verification cap: rejected tags spend checks; exhausted cap spends no DMA verification.
        before=diag()[1];send([72,before+2],'lower_budget')
        ingest(0,bad=True);ingest(1,bad=True)
        text=ingest(2,exhausted=True);check('VERIFY_LIMIT' in text,'verification_cap_reached')
        check(diag()[1]==before+2,'verification_cap_not_exceeded');reset('reset_exhausted_budget')
        send([73],'budget_after_reset')
        # MAC-check operational limit, with no authenticated application dispatch.
        open_session(2);packet=alice.wrap(0x100,packed([67]));bad=bytearray(packet);bad[-1]^=1;before=diag()
        check(command('D',bytes(bad),'mac_budget_1')[0]==-7,'mac_budget_1');check(command('D',bytes(bad),'mac_budget_2')[0]==-7,'mac_budget_2');check(command('D',packet,'mac_budget_exhausted')[0]==-8,'mac_budget_exhausted');check(diag()==before,'mac_budget_no_application_effect')
        check(command('D',packed([60]),'plaintext')[0]==-3,'plaintext_rejected')
        result['functional_tests_complete']=True
    except BaseException as exc:result['error']=repr(exc);raise
    finally:
        if process is not None and process.poll() is None:process.terminate();process.wait(timeout=10)
        for obj in [uart,log,xlog,txlog]:
            if obj is not None:obj.close()
        if programmed:
            try:
                with UARTSession(out/'baseline_restore',args.port) as restored:result['baseline_manifest']=restored.manifest;result['baseline_restored']=True
            except BaseException as exc:result['restore_error']=repr(exc)
        result['complete']=bool(result.get('functional_tests_complete') and result.get('baseline_restored') and not result.get('error'));save()
        status('COMPLETED_PENDING_RAW_VERIFICATION' if result['complete'] else 'STOPPED_ERROR',port_released=True,baseline_restored=result.get('baseline_restored',False))
        print('SECURE_ACCUMULATOR_EVIDENCE',out,flush=True)
    assert result['complete']
if __name__=='__main__':main()
