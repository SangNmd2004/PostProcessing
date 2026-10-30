"""Run the supplied regression benches in XSim without editing project sources."""
from pathlib import Path
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
BIN = Path('D:/Xilinx/Vivado/2020.2/bin')
SOURCES = [ROOT / p for p in (
    'rtl/ldpc/ldpc_sdp_ram.v', 'rtl/ldpc/qc_cyclic_shifter.v',
    'rtl/ldpc/ldpc_code_rom.v', 'rtl/ldpc/ldpc_ir_decoder.v',
    'rtl/top/qkd_ir_core.v', 'rtl/pa/pa_hankel_hash.v', 'rtl/top/qkd_pp_axi.v',
    'rtl/top/qkd_pp_zc702.v',
)]

def run(name, args):
    result = subprocess.run([str(BIN / (name + '.bat')), *map(str, args)],
                            cwd=OUT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors='replace', timeout=900,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    (OUT / (name + '_' + str(args[0]).replace('/', '_') + '.stdout.txt')).write_text(
        result.stdout, encoding='utf-8')
    print(result.stdout[-4000:], flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
    return result.stdout

benches = []
for name, data in [('tb_qkd_ir', 'tb'), ('tb_qkd_ir_ctx', 'sessions_tb')]:
    content = (ROOT / 'tb' / (name + '.v')).read_text(encoding='utf-8')
    content = content.replace('`define DATA_DIR "data/' + data + '/"',
                              '`define DATA_DIR "' + (ROOT / 'data' / data).as_posix() + '/"')
    content = content.replace('`define RTT_CYC 5000', '`define RTT_CYC 10000')
    content = content.replace('qkd_pp_axi #(.ZC(ZC), .SH_W(SH_W)) dut', 'qkd_pp_zc702 dut')
    content = content.replace('qkd_pp_axi #(.ZC(ZC), .SH_W(SH_W), .CTX_W(CTX_W)) dut', 'qkd_pp_zc702 dut')
    dest = OUT / (name + '_review.v')
    dest.write_text(content, encoding='utf-8')
    benches.append(dest)

run('xvlog', ['--relax', *SOURCES])
selected = [('tb_qkd_ir', 'review_basic', benches[0]), ('tb_qkd_ir_ctx', 'review_ctx', benches[1])]
if '--ctx-only' in sys.argv[1:]:
    selected = selected[1:]
for top, snapshot, bench in selected:
    # Separate compiler invocations isolate DATA_DIR macros between testbenches.
    run('xvlog', ['--relax', bench])
    run('xelab', [top, '-s', snapshot, '--debug', 'off', '--mt', '2'])
    result = run('xsim', [snapshot, '-runall', '-log', snapshot + '.log'])
    if 'TB_RESULT: PASS' not in result:
        raise SystemExit('Missing PASS for ' + top)
    if top == 'tb_qkd_ir_ctx':
        count = int((ROOT / 'data/sessions_tb/nblk.hex').read_text().strip(), 16)
        if f'TOTAL {count} blocks' not in result:
            raise SystemExit('Wrong vector set/count for ' + top)
print('ZC702_REVIEW_SIM_DONE', flush=True)
