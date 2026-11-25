"""Capture timer-paced IR component measurements on a separate lab ELF."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,random,re,struct,subprocess,time
from uart_session import UARTSession,ROOT
from checkpoint_io import write_checkpoint
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--build',required=True,type=Path);ap.add_argument('--fixtures',required=True,type=Path);ap.add_argument('--port',default='COM3');ap.add_argument('--config',type=Path);ap.add_argument('--smoke',action='store_true');args=ap.parse_args()
    build=args.build.resolve();fixtures=args.fixtures.resolve();vectors=json.loads((fixtures/'fixtures.json').read_text());manifest=json.loads((build/'manifest.json').read_text())
    job=json.loads((ROOT/'RUNNING_JOBS.json').read_text());assert job.get('port_released',False) and job['status']!='COMPLETED_PENDING_RAW_VERIFICATION',job
    cases=[]
    if args.config:
        config=json.loads(args.config.read_text());cases=config['cases'];assert config['fixture_sha256']==sha(fixtures/'fixtures.json')
    elif args.smoke:
        cases=[dict(k=1,jobs=4,rtt=1000,interval=1000,capacity=4,policy=p,repeat=0,phase='smoke') for p in [0,1,2]]
        cases+=[dict(k=4,jobs=8,rtt=1000,interval=0,capacity=1,policy=2,repeat=0,phase='drop_smoke')]
        config=dict(cases=cases,fixture_sha256=sha(fixtures/'fixtures.json'),scope='SMALL_BOARD_PREFLIGHT_NOT_RESEARCH_QUALIFICATION')
    else:
        cases=[dict(k=1,jobs=32,rtt=1000,interval=0,capacity=128,policy=p,repeat=r,phase='training') for p in [0,1] for r in range(3)]
        validation=[dict(k=k,jobs=32,rtt=rtt,interval=interval,capacity=128,policy=p,repeat=0,phase='pilot') for k in [1,2,4] for rtt in [0,1000] for interval in [100,1000] for p in [0,1,2]]
        random.Random(2026110211).shuffle(validation);cases+=validation
        config=dict(cases=cases,fixture_sha256=sha(fixtures/'fixtures.json'),scope='FIXED_FADJ_DDR_IR_COMPONENT_PILOT; PA/MAC/UART excluded; repeated two paired public inputs')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'build/zc702/paced_runs'/stamp;out.mkdir(parents=True,exist_ok=False)
    result=dict(complete=False,started_utc=stamp,hardware_capture=True,config=config,config_source_sha256=sha(args.config) if args.config else None,build_manifest=manifest,fixtures=vectors,fixture_directory=fixtures.relative_to(ROOT).as_posix(),runs=[])
    (out/'frozen_config.json').write_text(json.dumps(config,indent=2)+'\n');(out/'runner_at_execution.py').write_bytes(Path(__file__).read_bytes())
    def save():write_checkpoint(out/'result.json',result)
    def status(s,**kw):write_checkpoint(ROOT/'RUNNING_JOBS.json',dict(status=s,pid=os.getpid(),script='syn/zc702/run_paced_board.py',run_directory=out.relative_to(ROOT).as_posix(),port=args.port,**kw))
    save();status('RUNNING',port_released=False);programmed=False
    try:
        programmed=True
        result['capture_start_monotonic_ns']=time.perf_counter_ns()
        with UARTSession(out/'capture',args.port,test_elf=ROOT/manifest['elf']) as uart:
            result['baseline_manifest']=uart.manifest
            for v in vectors['vectors']:
                data=(fixtures/v['file']).read_bytes();assert sha(fixtures/v['file'])==v['sha256']
                w=struct.unpack('<'+'I'*(len(data)//4),data);uart.command([70,v['slot'],len(w),*w],r'QKD_BENCH_VECTOR seq={seq} index='+str(v['slot']))
            pe=[]
            for source in vectors['sources']:pe.extend([struct.unpack('<I',struct.pack('<f',source['q_pe']))[0],source['n_pe']])
            uart.command([78,*pe],r'QKD_PACED_CONFIG seq={seq} n_pe0=10000 n_pe1=10000')
            for i,c in enumerate(cases):
                seq,m=uart.command([76,c['k'],c['jobs'],c['rtt'],c['interval'],c['capacity'],c['policy']],r'QKD_PACED_PASS seq={seq} contexts=(\d+) jobs=(\d+) corrected=(\d+) discarded=(\d+) dropped=(\d+) interval_us=(\d+) policy=(\d+) elapsed_us=(\d+)')
                k,jobs,corrected,discarded,dropped,interval,policy,elapsed=map(int,m.groups());assert [k,jobs,interval,policy]==[c['k'],c['jobs'],c['interval'],c['policy']];assert corrected+discarded+dropped==jobs
                read_seq,_=uart.command([77]);rows=[]
                for j in range(jobs):
                    reply=uart.expect(fr'QKD_PACED_JOB seq={read_seq} id={j} scheduled=(\d+) arrived=(\d+) dispatch=(\d+) complete=(\d+) profile=(\d+) slot=(\d+) backlog=(\d+) outcome=(\d+) attempts=(\d+) leak=(\d+) cycles=(\d+)')
                    fields=['scheduled','arrived','dispatch','complete','profile','slot','backlog','outcome','attempts','leak','cycles'];rows.append(dict(id=j,**dict(zip(fields,map(int,reply.groups())))))
                uart.expect(fr'QKD_PACED_ROWS_DONE seq={read_seq} rows={jobs}')
                result['runs'].append(dict(case=c,run_seq=seq,read_seq=read_seq,elapsed_us=elapsed,corrected=corrected,discarded=discarded,dropped=dropped,rows=rows));save()
                print('PACED_BOARD_PROGRESS',i+1,'/',len(cases),'K',k,'policy',policy,'interval',interval,'us','done',corrected,'drop',dropped,flush=True)
            result['functional_tests_complete']=True
    except BaseException as exc:
        result['error']=repr(exc)
        try:
            nm='D:/Xilinx/Vitis/2020.2/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-nm.exe'
            symbols=subprocess.check_output([nm,str(ROOT/manifest['elf'])],text=True)
            found=re.search(r'^([0-9a-f]+) [a-zA-Z] paced_debug$',symbols,re.M)
            command=['D:/Xilinx/Vitis/2020.2/bin/xsct.bat',str(ROOT/'syn/zc702/diagnose_paced.tcl')]+(['0x'+found[1]] if found else [])
            p=subprocess.run(command,capture_output=True,text=True,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
            (out/'failed_cpu_diagnostic.log').write_text(p.stdout+p.stderr);result['diagnostic_returncode']=p.returncode
        except BaseException as diagnostic_error:result['diagnostic_error']=repr(diagnostic_error)
        raise
    finally:
        if programmed:
            try:
                with UARTSession(out/'baseline_restore',args.port) as restored:result['baseline_manifest']=restored.manifest;result['baseline_restored']=True
            except BaseException as exc:result['restore_error']=repr(exc)
        result['complete']=bool(result.get('functional_tests_complete') and result.get('baseline_restored') and not result.get('error'));save()
        status('COMPLETED_PENDING_RAW_VERIFICATION' if result['complete'] else 'STOPPED_ERROR',port_released=True,baseline_restored=result.get('baseline_restored',False));print('PACED_EVIDENCE',out,flush=True)
    assert result['complete']
if __name__=='__main__':main()
