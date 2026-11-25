"""Build a separate DDR-paced IR lab ELF through a private baseline overlay."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();out=args.output.resolve()
    assert out.is_relative_to(ROOT/'build/zc702/paced_test');out.mkdir(parents=True,exist_ok=False)
    base=ROOT/'build/zc702/uart_firmware';manifest=json.loads((base/'manifest.json').read_text())
    for n,h in manifest['files'].items():assert sha(ROOT/n)==h,n
    for n in ['controller_generated.h','accumulator_generated.h']:(out/n).write_bytes((base/n).read_bytes())
    service=(ROOT/'firmware/zc702_uart/service.h').read_text().replace('"functional.h"','"paced_functional_overlay.h"')
    service=service.replace('    xil_printf("QKD_UART_READY', '    xil_printf("QKD_PACED_BUILD version=1 public=1\\r\\n");\n    xil_printf("QKD_UART_READY',1)
    functional=(ROOT/'firmware/zc702_uart/functional.h').read_text()
    functional=functional.replace('static int functional_command(', '#include "paced_benchmark.h"\nstatic int functional_command(',1)
    functional=functional.replace('    uint32_t op=frame[0];', '    uint32_t op=frame[0];\n    if(op>=76u&&op<=78u)return paced_command(n,seq);',1)
    (out/'paced_service_overlay.h').write_text(service);(out/'paced_functional_overlay.h').write_text(functional)
    source=(base/'uart_main.c').read_text().split('#include "service.h"')[0]+'\n#include "paced_service_overlay.h"\n';(out/'paced_main.c').write_text(source)
    platform=ROOT/'build/zc702/vitis/qkd_zc702_platform/export/qkd_zc702_platform/sw/qkd_zc702_platform/standalone_domain'
    link=ROOT/'build/zc702/vitis/qkd_smoke/src/lscript.ld';gcc='D:/Xilinx/Vitis/2020.2/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe'
    cmd=[gcc,'-g','-mcpu=cortex-a9','-mfpu=vfpv3','-mfloat-abi=hard','-O2','-Wall','-Wextra','-Werror','-Wno-unused-const-variable',
         '-I'+str(platform/'bspinclude/include'),'-I'+str(ROOT/'firmware/zc702'),'-I'+str(ROOT/'firmware/zc702_uart'),'-I'+str(ROOT/'firmware'),'-I'+str(out),
         '-specs='+str(link.with_name('Xilinx.spec')),'-Wl,--build-id=none','-Wl,-T,'+str(link),'-L'+str(platform/'bsplib/lib'),str(out/'paced_main.c'),'-o',str(out/'paced_test.elf'),'-Wl,--start-group,-lxil,-lgcc,-lc,-lm,--end-group']
    p=subprocess.run(cmd,capture_output=True,text=True);(out/'build.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
    files=set(manifest['files'])|{'firmware/zc702_uart/paced_benchmark.h','firmware/zc702_uart/paced_queue.h','syn/zc702/build_paced_test.py','syn/zc702/uart_session.py','syn/zc702/program_bootstrap.tcl'}
    for n in files:
        if (ROOT/n).suffix in ['.h','.c','.py','.tcl','.ld']:
            dest=out/'source_snapshot'/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/n).read_bytes())
    receipt=dict(elf=(out/'paced_test.elf').relative_to(ROOT).as_posix(),elf_sha256=sha(out/'paced_test.elf'),command=cmd,
        source_sha256={n:sha(ROOT/n) for n in sorted(files)},generated_sha256={p.name:sha(p) for p in out.iterdir() if p.suffix in ['.h','.c']},
        scope='PUBLIC DDR-paced IR component; fixed f_adj; no PA, MAC, independent FER samples or secret-key throughput')
    (out/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n');print('PACED_ARM_BUILD_PASS',out)
if __name__=='__main__':main()
