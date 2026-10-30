"""Verify final XSA/bitstream/configuration and write a reproducible bundle manifest."""
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/zc702'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def require(condition, message):
    if not condition:
        raise SystemExit('BUNDLE_VERIFY_FAIL: ' + message)

xsa, bit = OUT / 'qkd_zc702.xsa', OUT / 'qkd_zc702.bit'
require(xsa.is_file() and bit.is_file(), 'final XSA/bitstream missing')
with ZipFile(xsa) as z:
    require(z.testzip() is None, 'XSA ZIP CRC failed')
    embedded = [n for n in z.namelist() if n.endswith('.bit')]
    require(len(embedded) == 1, 'expected one bitstream inside XSA')
    require(sha(z.read(embedded[0])) == sha(bit.read_bytes()), 'embedded bitstream differs from external bitstream')
    hwh = ET.fromstring(z.read(next(n for n in z.namelist() if n.endswith('.hwh'))))

modules = {m.get('INSTANCE'): m for m in hwh.findall('.//MODULE')}
reset_params = {x.get('NAME'):x.get('VALUE') for x in modules['reset'].findall('./PARAMETERS/PARAMETER')}
reset_ports = {x.get('NAME'):x for x in modules['reset'].findall('./PORTS/PORT')}
one_ports = {x.get('NAME'):x for x in modules['one'].findall('./PORTS/PORT')}
one_params = {x.get('NAME'):x.get('VALUE') for x in modules['one'].findall('./PARAMETERS/PARAMETER')}
require(reset_params.get('C_AUX_RESET_HIGH') == '0' and int(one_params['CONST_VAL'],0) == 1 and
        reset_ports['aux_reset_in'].get('SIGNAME') == one_ports['dout'].get('SIGNAME'),
        'active-low auxiliary reset must be tied HIGH, not asserted')
config = {}
for name, receive in [('dma_ch',1), ('dma_syn',0), ('dma_pa',1), ('dma_seed',0)]:
    require(name in modules, 'missing ' + name)
    p = {x.get('NAME'): x.get('VALUE') for x in modules[name].findall('./PARAMETERS/PARAMETER')}
    expected = {'C_INCLUDE_SG':'0', 'C_SG_INCLUDE_STSCNTRL_STRM':'0', 'C_SG_LENGTH_WIDTH':'26',
                'C_INCLUDE_MM2S':'1', 'C_INCLUDE_S2MM':str(receive), 'C_M_AXI_MM2S_DATA_WIDTH':'64',
                'C_M_AXIS_MM2S_TDATA_WIDTH':'32'}
    if receive:
        expected.update(C_M_AXI_S2MM_DATA_WIDTH='64', C_S_AXIS_S2MM_TDATA_WIDTH='64')
    for k, value in expected.items():
        require(p.get(k) == value, f'{name} {k}: {p.get(k)} != {value}')
    config[name] = expected

ps = {x.get('NAME'): x.get('VALUE') for x in modules['ps7'].findall('./PARAMETERS/PARAMETER')}
require(float(ps['PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ']) == 50.0, 'FCLK0 is not 50 MHz')
addresses = {'dma_ch':0x40400000, 'dma_syn':0x40410000, 'dma_pa':0x40420000,
             'dma_seed':0x40430000, 'qkd':0x43c00000}
ranges = {m.get('INSTANCE'):m for m in hwh.findall('.//MEMRANGE') if m.get('MEMTYPE') == 'REGISTER'}
for name, address in addresses.items():
    require(name in ranges and int(ranges[name].get('BASEVALUE'),16) == address, 'incorrect MMIO base: ' + name)
timing = (OUT / 'timing_routed.rpt').read_text(encoding='utf-8')
require('All user specified timing constraints are met.' in timing, 'post-route timing did not pass')
complete_logs = [p for p in [OUT/'implement.log',OUT/'export.log'] if p.is_file() and
                 p.stat().st_mtime >= xsa.stat().st_mtime and
                 re.search(r'^ZC702_SYSTEM_IMPLEMENT_DONE\s*$',p.read_text(encoding='utf-8'),re.MULTILINE)]
require(bool(complete_logs), 'fresh implementation/export completion marker missing')

files = [xsa, bit, OUT/'system_routed.dcp', OUT/'timing_routed.rpt', OUT/'utilization_routed.rpt', OUT/'drc_routed.rpt']
files += sorted((ROOT/'rtl').rglob('*.v'))
files += sorted((ROOT/'firmware/zc702').glob('*.c')) + sorted((ROOT/'firmware/zc702').glob('*.h'))
files += sorted((ROOT/'syn/zc702').glob('*.tcl')) + sorted((ROOT/'syn/zc702').glob('*.ps1'))
files += sorted((ROOT/'syn/zc702').glob('*.py')) + sorted((ROOT/'firmware/zc702').glob('*.py'))
elfs = list((OUT/'vitis/qkd_smoke').rglob('qkd_smoke.elf')) if (OUT/'vitis/qkd_smoke').exists() else []
if elfs:
    require(len(elfs) == 1, 'ambiguous firmware ELF selection')
    image = elfs[0].read_bytes()
    require(image[:5] == b'\x7fELF\x01' and int.from_bytes(image[18:20],'little') == 40,
            'firmware is not a 32-bit ARM ELF')
    platform = OUT/'vitis/qkd_zc702_platform'
    copied_xsa = list(platform.rglob('*.xsa'))
    require(bool(copied_xsa), 'BSP hardware handoff missing')
    for p in copied_xsa:
        require(sha(p.read_bytes()) == sha(xsa.read_bytes()), 'BSP uses a different XSA: ' + str(p))
    for p in (ROOT/'firmware/zc702').glob('*'):
        if p.suffix in ('.c','.h'):
            compiled_source = OUT/'vitis/qkd_smoke/src'/p.name
            require(compiled_source.is_file() and sha(compiled_source.read_bytes()) == sha(p.read_bytes()),
                    'application source differs from repository: ' + p.name)
    parameters = platform/'ps7_cortexa9_0/standalone_domain/bsp/ps7_cortexa9_0/include/xparameters.h'
    require(parameters.is_file(), 'BSP xparameters.h missing')
    defines = dict(re.findall(r'^#define\s+(\w+)\s+(\S+)', parameters.read_text(), re.MULTILINE))
    require(defines.get('XPAR_XAXIDMA_NUM_INSTANCES') == '4', 'BSP DMA instance count mismatch')
    require(int(defines['STDOUT_BASEADDRESS'],0) == 0xe0001000, 'BSP stdout is not UART1')
    for name, address in addresses.items():
        if name == 'qkd':
            continue
        prefix = 'XPAR_' + name.upper() + '_'
        require(int(defines[prefix+'BASEADDR'],0) == address, 'BSP DMA address mismatch: ' + name)
        require(defines[prefix+'INCLUDE_SG'] == '0', 'BSP unexpectedly enables SG: ' + name)
        require(defines[prefix+'SG_LENGTH_WIDTH'] == '26', 'BSP transfer-length width mismatch: ' + name)
    files += copied_xsa + [parameters]
files += elfs
board_runs = []
passing_run = None
for result_file in sorted((OUT/'board_runs').glob('*/result.json')):
    proof = json.loads(result_file.read_text(encoding='utf-8'))
    board_runs.append({'result':result_file.relative_to(ROOT).as_posix(), 'board_pass':proof.get('board_pass',False)})
    if proof.get('board_pass') and proof.get('hardware_capture'):
        hashes = proof.get('artifact_sha256',{})
        required = [xsa,bit,*elfs]
        if all(hashes.get(p.relative_to(ROOT).as_posix()) == sha(p.read_bytes()) for p in required):
            uart_file = result_file.with_name('uart.log')
            uart = uart_file.read_text(encoding='utf-8',errors='replace')
            received = re.findall(r'QKD_IR_VECTOR_PASS block=(\d+)',uart)
            require(len(received) == 9 and sorted(map(int,received)) == list(range(9)), 'board UART block receipts incomplete')
            require('QKD_PA_VECTOR_PASS bits=4096' in uart and 'QKD_ZC702_SELFTEST_PASS blocks=9 pa=1' in uart,
                    'board UART final receipts incomplete')
            passing_run = result_file.relative_to(ROOT).as_posix()
            files += [result_file,uart_file,result_file.with_name('xsct.log')]
manifest = {'board':'ZC702', 'part':'xc7z020clg484-1', 'fclk0_mhz':50,
            'hardware_stage':'post_route', 'board_test':'PASS_CONTEXT_0_GOLDEN_VECTORS' if passing_run else 'NOT_PASSED' if board_runs else 'NOT_RUN',
            'passing_board_result':passing_run, 'board_runs':board_runs,
            'dma':config, 'addresses':{k:hex(v) for k,v in addresses.items()},
            'files':{p.relative_to(ROOT).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in files}}
(OUT/'bundle_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('ZC702_BUNDLE_VERIFY_PASS bit_sha256=' + sha(bit.read_bytes()))
print('manifest:', OUT/'bundle_manifest.json')
