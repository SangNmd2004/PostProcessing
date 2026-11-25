"""Build the generic UART ELF with the existing matching BSP, leaving smoke ELF intact."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import shutil

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'build/zc702'
subprocess.run([sys.executable, str(ROOT/'syn/zc702/verify_bundle.py')], check=True, cwd=ROOT)
dest = OUT/'uart_firmware'
dest.mkdir(exist_ok=True)
if (dest/'qkd_uart.elf').exists():
    previous=hashlib.sha256((dest/'qkd_uart.elf').read_bytes()).hexdigest()
    archive=OUT/'uart_firmware_history'/previous
    if not archive.exists():
        shutil.copytree(dest,archive)
driver=(ROOT/'firmware/qkd_pp_driver.c').read_text()
controller=driver[driver.index('#define F_TARGET'):driver.index('static void reveal_bits')]
(dest/'controller_generated.h').write_text('#include <math.h>\n#include <stdbool.h>\n#include "qkd_pp_regs.h"\n'+controller,encoding='utf-8')
accum=driver[driver.index('#define PA_N_MAX'):driver.index('/* ---------------- multi-context operation')]
(dest/'accumulator_generated.h').write_text(accum,encoding='utf-8')
for name in ['service.h','functional.h','multicontext.h','irq_test.h','key_stream.h','latency_benchmark.h','hw_profiler.h']:
    shutil.copyfile(ROOT/'firmware/zc702_uart'/name,dest/(name+'.snapshot'))
source = (ROOT/'firmware/zc702/smoke_main.c').read_text()
old = 'static int test_ir(uint32_t block)\n{\n    const smoke_vector_t *v = &smoke_vectors[block];'
assert source.count(old) == 1
source = source.replace(old, 'static int test_ir_vector(const smoke_vector_t *v, uint32_t block)\n{')
source = source[:source.index('int main(void)')] + '\n#include "service.h"\n'
(dest/'uart_main.c').write_text(source, encoding='utf-8')
platform = OUT/'vitis/qkd_zc702_platform/export/qkd_zc702_platform/sw/qkd_zc702_platform/standalone_domain'
gcc = Path('D:/Xilinx/Vitis/2020.2/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe')
link = OUT/'vitis/qkd_smoke/src/lscript.ld'
elf = dest/'qkd_uart.elf'
command = [str(gcc), '-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard', '-O2',
           '-Wall', '-Wextra', '-Werror', '-Wno-unused-const-variable',
           '-I'+str(platform/'bspinclude/include'), '-I'+str(ROOT/'firmware/zc702'),
           '-I'+str(ROOT/'firmware/zc702_uart'), '-specs='+str(link.with_name('Xilinx.spec')), '-Wl,-build-id=none',
           '-I'+str(dest), '-I'+str(ROOT/'firmware'),
           '-Wl,-T,'+str(link), '-L'+str(platform/'bsplib/lib'), str(dest/'uart_main.c'),
           '-o', str(elf), '-Wl,--start-group,-lxil,-lgcc,-lc,-lm,--end-group']
run = subprocess.run(command, cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
(dest/'build.log').write_text(run.stdout, encoding='utf-8')
print(run.stdout)
run.check_returncode()
files = [OUT/'qkd_zc702.bit', OUT/'qkd_zc702.xsa', elf, link, dest/'uart_main.c',
         ROOT/'firmware/zc702_uart/service.h', ROOT/'firmware/zc702/smoke_vectors.h', Path(__file__)]
files += sorted((platform/'bsplib/lib').glob('*.a'))
files += [ROOT/'firmware/zc702_uart/functional.h',ROOT/'firmware/qkd_pp_driver.c',
          ROOT/'firmware/qkd_pp_regs.h',ROOT/'firmware/qkd_punct_tables.h',dest/'controller_generated.h',
          dest/'accumulator_generated.h',dest/'service.h.snapshot',dest/'functional.h.snapshot']
files += [ROOT/'firmware/zc702_uart/multicontext.h',dest/'multicontext.h.snapshot']
files += [ROOT/'firmware/zc702_uart/irq_test.h',dest/'irq_test.h.snapshot']
files += [ROOT/'firmware/zc702_uart/key_stream.h',dest/'key_stream.h.snapshot']
files += [ROOT/'firmware/zc702_uart/latency_benchmark.h',dest/'latency_benchmark.h.snapshot']
files += [ROOT/'firmware/zc702_uart/hw_profiler.h',dest/'hw_profiler.h.snapshot']
manifest = {'protocol':1, 'context':0, 'files':{p.relative_to(ROOT).as_posix():
            hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
(dest/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
print('ZC702_UART_BUILD_PASS', elf)
