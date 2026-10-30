"""Program generic firmware once, stream CRC32-protected test vectors over UART.

JTAG loads bit/ELF only. All campaign payloads use COM3; stop-and-wait chunks
prevent FIFO overruns. A hardware match includes expected DISCARD outcomes.
"""
from pathlib import Path
from datetime import datetime, timezone
from zipfile import ZipFile
import argparse
import collections
import csv
import hashlib
import json
import re
import struct
import subprocess
import sys
import time
import zlib
import serial

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/zc702'
MAGIC=0x51564431

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',default='COM3')
    ap.add_argument('--campaign',type=Path,default=OUT/'uart_campaign/campaign.json')
    ap.add_argument('--limit',type=int)
    ap.add_argument('--attach',action='store_true',help='Use a service already waiting on UART; skip JTAG')
    args=ap.parse_args()
    campaign=json.loads(args.campaign.read_text())
    if not campaign['complete']:raise ValueError('campaign generation incomplete')
    records=campaign['records'][:args.limit]
    if not records:raise ValueError('empty campaign')
    subprocess.run([sys.executable,str(ROOT/'syn/zc702/verify_bundle.py')],check=True,cwd=ROOT)
    manifest_path=OUT/'uart_firmware/manifest.json'
    manifest=json.loads(manifest_path.read_text())
    for name,digest in manifest['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('UART firmware source/artifact changed; rebuild: '+name)
    for r in records:
        packet=(args.campaign.parent/r['file']).read_bytes()
        if hashlib.sha256(packet).hexdigest()!=r['sha256'] or f'{zlib.crc32(packet):08x}'!=r['crc32']:
            raise ValueError('payload hash mismatch')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_dir=OUT/'uart_runs'/stamp
    run_dir.mkdir(parents=True,exist_ok=False)
    (run_dir/'firmware_manifest.json').write_bytes(manifest_path.read_bytes())
    result={'hardware_capture':True,'board':'ZC702','port':args.port,'baud':115200,
            'started_utc':stamp,'campaign_sha256':hashlib.sha256(args.campaign.read_bytes()).hexdigest(),
            'requested':len(records),'hardware_matches':0,'complete':False,'records':[],
            'source_campaign':str(args.campaign.resolve()),'firmware_manifest':manifest}
    process=None
    def persist():
        (run_dir/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    try:
        with serial.Serial(args.port,115200,timeout=0.15,write_timeout=5) as uart, \
             (run_dir/'uart.log').open('wb') as log, (run_dir/'xsct.log').open('wb') as xlog:
            pending=bytearray()
            def line(timeout=45):
                deadline=time.monotonic()+timeout
                while time.monotonic()<deadline:
                    if b'\n' in pending:
                        raw,_,rest=pending.partition(b'\n');pending[:]=rest
                        text=raw.decode(errors='replace').strip()
                        if any(s in text for s in ['FATAL','MISMATCH','TIMEOUT','ERROR']):
                            raise RuntimeError(text)
                        return text
                    chunk=uart.read(max(1,uart.in_waiting))
                    if chunk:pending.extend(chunk);log.write(chunk);log.flush()
                    if process is not None and process.poll() not in (None,0):
                        raise RuntimeError('JTAG loader failed; inspect xsct.log')
                raise TimeoutError('UART response deadline')
            def expect(pattern,timeout=45):
                deadline=time.monotonic()+timeout
                while time.monotonic()<deadline:
                    text=line(max(0.1,deadline-time.monotonic()))
                    match=re.fullmatch(pattern,text)
                    if match:return match
                    if text.startswith('QKD_UART_'):
                        raise RuntimeError('unexpected UART response: '+text)
                raise TimeoutError(pattern)
            if args.attach:
                # Ping using an empty session frame; service responds without reset.
                uart.write(struct.pack('<4I',MAGIC,0,0,0));previous=expect(r'QKD_UART_DONE passed=(\d+)')
                expect(r'QKD_UART_READY version=1 max_words=4096')
                prior_passes=int(previous.group(1))
                # Clear no bytes: responses for the next header are read normally.
            else:
                uart.reset_input_buffer()
                with ZipFile(OUT/'qkd_zc702.xsa') as z:(OUT/'ps7_init.tcl').write_bytes(z.read('ps7_init.tcl'))
                process=subprocess.Popen(['D:/Xilinx/Vitis/2020.2/bin/xsct.bat',str(ROOT/'syn/zc702/program_smoke.tcl'),'uart'],
                                         cwd=ROOT,stdout=xlog,stderr=subprocess.STDOUT,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                expect(r'QKD_UART_READY version=1 max_words=4096',timeout=120)
                process.wait(timeout=30)
                xlog.flush()
                xt=(run_dir/'xsct.log').read_text(errors='replace')
                if process.returncode or 'ZC702_PROGRAM_MMIO_PASS' not in xt or 'ZC702_SMOKE_CPU_STARTED' not in xt:
                    raise RuntimeError('JTAG programming receipt missing')
                prior_passes=0
            def send(seq,payload,crc):
                uart.write(struct.pack('<4I',MAGIC,seq,len(payload)//4,crc))
                expect(fr'QKD_UART_ACCEPT seq={seq}')
                for off in range(0,len(payload),128):
                    chunk=payload[off:off+128]
                    uart.write(chunk)
                    expect(fr'QKD_UART_ACK seq={seq} bytes={off+len(chunk)}')
            # Negative transport test: bad CRC must be rejected before QKD execution.
            payload=(args.campaign.parent/records[0]['file']).read_bytes()
            send(0xffffffff,payload,zlib.crc32(payload)^1)
            expect(r'QKD_UART_CRC_REJECT seq=4294967295')
            result['bad_crc_rejected']=True
            for r in records:
                payload=(args.campaign.parent/r['file']).read_bytes();seq=r['seq']
                send(seq,payload,zlib.crc32(payload))
                receipt=expect(fr'QKD_UART_RESULT seq={seq} crc=([0-9a-fA-F]{{8}}) conv=(\d+) attempts=(\d+) errcnt=(\d+)')
                crc,conv,attempts,errcnt=receipt.groups()
                expected_conv=r['model_outcome']!='DISCARD'
                # ERRCNT is valid only after convergence; DISCARD can retain a prior value.
                if crc.lower()!=r['crc32'] or bool(int(conv))!=expected_conv or int(attempts)!=r['attempts'] or (expected_conv and int(errcnt)!=r['expected_errcnt']):
                    raise RuntimeError('hardware receipt mismatch: '+str(seq))
                row=dict(r,hardware_match=True,hardware_conv=bool(int(conv)),
                         hardware_errcnt=int(errcnt) if expected_conv else None,hardware_errcnt_register=int(errcnt),
                         hardware_attempts=int(attempts))
                result['records'].append(row);result['hardware_matches']+=1
                persist()
                print(f"HARDWARE_MATCH {seq} {r['source']} {r.get('group','')} QBER={r.get('qber_pct','')} "
                      f"{r.get('code','')} {r['model_outcome']} attempts={attempts}",flush=True)
            uart.write(struct.pack('<4I',MAGIC,0,0,0))
            done=expect(r'QKD_UART_DONE passed=(\d+)')
            if int(done.group(1))!=prior_passes+len(records):raise RuntimeError('session total mismatch')
            result['complete']=True
            result['session_passed_total']=int(done.group(1))
    except Exception as exc:
        result['error']=str(exc)
        raise
    finally:
        if process is not None and process.poll() is None:process.terminate()
        persist()
        if result['records']:
            keys=sorted(set().union(*(r.keys() for r in result['records'])))
            with (run_dir/'blocks.csv').open('w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(result['records'])
        print('UART_EVIDENCE',run_dir,flush=True)
    print('UART_CAMPAIGN_PASS',result['hardware_matches'],flush=True)

if __name__=='__main__':main()
