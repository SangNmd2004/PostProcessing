"""Build a separate public-fixture ARM test ELF; never overwrite baseline ELF."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
SOURCES=['firmware/zc702_uart/bootstrap_test_main.c','firmware/zc702_uart/qas2_bootstrap.c','firmware/zc702_uart/auth_session.c',
         'firmware/crypto/qcrypto.c','firmware/crypto/rfc6234/sha224-256.c','firmware/crypto/siphash.c']

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path)
    args=ap.parse_args();out=args.output.resolve()
    assert out.is_relative_to(ROOT/'build/zc702/bootstrap_test')
    assert not (out/'manifest.json').exists(), 'Use a fresh output directory; never overwrite an archived test build'
    out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((ROOT/'build/zc702/uart_firmware/manifest.json').read_text())
    for file,sha in manifest['files'].items():assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==sha,file
    platform=ROOT/'build/zc702/vitis/qkd_zc702_platform/export/qkd_zc702_platform/sw/qkd_zc702_platform/standalone_domain'
    link=ROOT/'build/zc702/vitis/qkd_smoke/src/lscript.ld'
    gcc='D:/Xilinx/Vitis/2020.2/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe'
    command=[gcc,'-mcpu=cortex-a9','-mfpu=vfpv3','-mfloat-abi=hard','-O2','-Wall','-Wextra','-Werror',
             '-I'+str(platform/'bspinclude/include'),'-specs='+str(link.with_name('Xilinx.spec')),
             '-Wl,--build-id=none','-Wl,-T,'+str(link),'-L'+str(platform/'bsplib/lib'),*[str(ROOT/f) for f in SOURCES],
             '-o',str(out/'bootstrap_test.elf'),'-Wl,--start-group,-lxil,-lgcc,-lc,-lm,--end-group']
    p=subprocess.run(command,capture_output=True,text=True);(out/'build.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
    files=SOURCES+['firmware/zc702_uart/qas2_bootstrap.h','firmware/zc702_uart/auth_session.h','firmware/crypto/qcrypto.h',
        'firmware/crypto/siphash.h','firmware/crypto/rfc6234/sha.h','firmware/crypto/rfc6234/sha-private.h',
        'syn/zc702/program_bootstrap.tcl','syn/zc702/build_bootstrap_test.py','build/zc702/qkd_zc702.bit','build/zc702/qkd_zc702.xsa']
    files += [str(link.relative_to(ROOT)),str(link.with_name('Xilinx.spec').relative_to(ROOT))]
    files += [str(p.relative_to(ROOT)) for p in (platform/'bsplib/lib').glob('*.a')]
    for f in files:
        dest=out/'source_snapshot'/f;dest.parent.mkdir(parents=True,exist_ok=True)
        if (ROOT/f).suffix not in ['.bit','.xsa','.a']:dest.write_bytes((ROOT/f).read_bytes())
    receipt=dict(scope='LAB ONLY: public root-key fixture, host-supplied nonce, plaintext reset/provision controls; not production authentication',
                 elf=str((out/'bootstrap_test.elf').relative_to(ROOT)),elf_sha256=hashlib.sha256((out/'bootstrap_test.elf').read_bytes()).hexdigest(),
                 source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},command=command,
                 baseline_manifest_files_verified=len(manifest['files']))
    (out/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('BOOTSTRAP_TEST_ELF_BUILD_PASS',out)

if __name__=='__main__':main()
