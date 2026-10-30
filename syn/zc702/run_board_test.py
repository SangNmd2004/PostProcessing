"""Verify bundle, capture COM3, then program/run the physical board via XSCT."""
from pathlib import Path
from zipfile import ZipFile
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import serial

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/zc702'
parser = argparse.ArgumentParser()
parser.add_argument('--port', default='COM3')
parser.add_argument('--timeout', type=float, default=150)
args = parser.parse_args()
subprocess.run([sys.executable, str(ROOT/'syn/zc702/verify_bundle.py')], cwd=ROOT, check=True)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
run_dir = OUT/'board_runs'/stamp
run_dir.mkdir(parents=True, exist_ok=False)
with ZipFile(OUT/'qkd_zc702.xsa') as z:
    (OUT/'ps7_init.tcl').write_bytes(z.read('ps7_init.tcl'))

# Open UART before any reset/programming. Sharing errors stop without touching hardware.
uart = serial.Serial(args.port, 115200, timeout=0.1, write_timeout=1)
uart.reset_input_buffer()
capture = bytearray()
result = {'hardware_capture':True, 'board':'ZC702', 'port':args.port, 'baud':115200,
          'started_utc':stamp, 'board_pass':False}
result['artifact_sha256'] = {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in
    [OUT/'qkd_zc702.bit', OUT/'qkd_zc702.xsa', OUT/'vitis/qkd_smoke/Debug/qkd_smoke.elf']}
proc = None
print('UART_OPEN', args.port, 'log directory:', run_dir, flush=True)
try:
    with (run_dir/'xsct.log').open('wb') as xsct_log, (run_dir/'uart.log').open('wb') as uart_log:
        proc = subprocess.Popen(['D:/Xilinx/Vitis/2020.2/bin/xsct.bat',
                                 str(ROOT/'syn/zc702/program_smoke.tcl')], cwd=ROOT,
                                stdout=xsct_log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + args.timeout
        terminal_time = None
        exited_time = None
        while time.monotonic() < deadline:
            chunk = uart.read(max(1, uart.in_waiting))
            if chunk:
                capture.extend(chunk)
                uart_log.write(chunk)
                uart_log.flush()
                print(chunk.decode('utf-8', errors='replace'), end='', flush=True)
            if b'QKD_ZC702_SELFTEST_PASS' in capture or b'QKD_ZC702_SELFTEST_FAIL' in capture:
                if terminal_time is None:
                    terminal_time = time.monotonic()
                if time.monotonic() - terminal_time >= 1 and proc.poll() is not None:
                    break
            if proc.poll() is not None:
                if exited_time is None:
                    exited_time = time.monotonic()
                program_log = (run_dir/'xsct.log').read_text(errors='replace')
                if proc.returncode != 0 or ('ZC702_SMOKE_CPU_STARTED' not in program_log and
                                           time.monotonic() - exited_time >= 1):
                    break
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
        result['xsct_returncode'] = proc.returncode
    text = capture.decode('utf-8', errors='replace')
    start = text.rfind('QKD_ZC702_SELFTEST_START')
    receipt = text[start:] if start >= 0 else ''
    blocks = re.findall(r'QKD_IR_VECTOR_PASS block=(\d+) attempts=(\d+)', receipt)
    result['ir_blocks'] = [{'block':int(b),'attempts':int(a)} for b,a in blocks]
    result['pa_pass'] = 'QKD_PA_VECTOR_PASS bits=4096' in receipt
    expected_seed_id = re.search(r'#define SMOKE_VECTOR_SHA256 "([0-9a-f]+)"',
                                 (ROOT/'firmware/zc702/smoke_vectors.h').read_text()).group(1)
    result['vectors_sha256'] = expected_seed_id
    xsct_text = (run_dir/'xsct.log').read_text(errors='replace')
    result['programming_pass'] = 'ZC702_PROGRAM_MMIO_PASS' in xsct_text and 'ZC702_SMOKE_CPU_STARTED' in xsct_text
    result['board_pass'] = bool(proc.returncode == 0 and result['programming_pass'] and start >= 0 and expected_seed_id in receipt and
                                len(blocks) == 9 and sorted(int(b) for b,a in blocks) == list(range(9)) and
                                result['pa_pass'] and
                                'QKD_ZC702_SELFTEST_PASS blocks=9 pa=1' in receipt and
                                not re.search(r'FAIL|ERROR|TIMEOUT|MISMATCH', receipt))
finally:
    uart.close()
    if proc is not None and proc.poll() is None:
        proc.terminate()
    (run_dir/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print('\nBOARD_TEST_' + ('PASS' if result['board_pass'] else 'FAIL'), 'evidence:',run_dir,flush=True)
if not result['board_pass']:
    print((run_dir/'xsct.log').read_text(errors='replace')[-6000:], flush=True)
    raise SystemExit(1)
