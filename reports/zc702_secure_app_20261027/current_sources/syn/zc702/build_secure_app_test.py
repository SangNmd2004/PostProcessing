"""Build an isolated QAS2-to-real-IR/PA fixture dispatcher using baseline helpers."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path)
    args=ap.parse_args();out=args.output.resolve()
    assert out.is_relative_to(ROOT/'build/zc702/secure_app_test') and not (out/'manifest.json').exists()
    out.mkdir(parents=True,exist_ok=True)
    baseline=ROOT/'build/zc702/uart_firmware';m=json.loads((baseline/'manifest.json').read_text())
    for name,sha in m['files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha,name
    for name in ['controller_generated.h','accumulator_generated.h']:(out/name).write_bytes((baseline/name).read_bytes())
    prefix=(baseline/'uart_main.c').read_text().split('#include "service.h"')[0]
    main=(ROOT/'firmware/zc702_uart/bootstrap_test_main.c').read_text()
    main=main.replace('QB_READY','SA_READY')
    main=main.replace('qas_reset(&data_session);','{qas_reset(&data_session);secure_lifecycle_clear();}')
    a=main.index("        }else if(line[0]=='D'){");b=main.index('\n        answer(rc,reply,count);',a)
    main=main[:a]+'''        }else if(line[0]=='G'){
            uint32_t diagnostic[5]={secure_dispatch_count,verification_used,(uint32_t)functional_active,(uint32_t)functional_key_valid,(uint32_t)secure_health};
            memcpy(reply,diagnostic,sizeof(diagnostic));count=sizeof(diagnostic);rc=0;
        }else if(line[0]=='D'){
            uint32_t written=0;rc=secure_dispatch(&data_session,input,(uint32_t)n,reply,sizeof(reply),&written);count=written;
        }
'''+main[b:]
    generated=prefix+'\n#include "secure_app_service.h"\n'+main
    (out/'secure_main.c').write_text(generated)
    platform=ROOT/'build/zc702/vitis/qkd_zc702_platform/export/qkd_zc702_platform/sw/qkd_zc702_platform/standalone_domain'
    link=ROOT/'build/zc702/vitis/qkd_smoke/src/lscript.ld'
    sources=['firmware/zc702_uart/qas2_bootstrap.c','firmware/zc702_uart/auth_session.c','firmware/crypto/qcrypto.c',
             'firmware/crypto/rfc6234/sha224-256.c','firmware/crypto/siphash.c']
    command=['D:/Xilinx/Vitis/2020.2/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe',
             '-mcpu=cortex-a9','-mfpu=vfpv3','-mfloat-abi=hard','-O2','-Wall','-Wextra','-Werror','-Wno-unused-const-variable',
             '-I'+str(platform/'bspinclude/include'),'-I'+str(ROOT/'firmware/zc702'),'-I'+str(ROOT/'firmware/zc702_uart'),
             '-I'+str(ROOT/'firmware'),'-I'+str(out),'-specs='+str(link.with_name('Xilinx.spec')),
             '-Wl,--build-id=none','-Wl,-T,'+str(link),'-L'+str(platform/'bsplib/lib'),str(out/'secure_main.c'),
             *[str(ROOT/name) for name in sources],'-o',str(out/'secure_app_test.elf'),'-Wl,--start-group,-lxil,-lgcc,-lc,-lm,--end-group']
    p=subprocess.run(command,capture_output=True,text=True);(out/'build.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
    files=set(m['files'])|set(sources)|{'firmware/zc702_uart/bootstrap_test_main.c','firmware/zc702_uart/secure_app_service.h',
         'firmware/zc702_uart/qas2_bootstrap.h','firmware/zc702_uart/auth_session.h','firmware/crypto/qcrypto.h',
         'firmware/crypto/rfc6234/sha.h','firmware/crypto/rfc6234/sha-private.h','firmware/crypto/siphash.h',
         'syn/zc702/build_secure_app_test.py','syn/zc702/program_bootstrap.tcl'}
    for name in files:
        if (ROOT/name).suffix in ['.h','.c','.py','.tcl','.ld']:
            dest=out/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/name).read_bytes())
    receipt=dict(scope='LAB public root/host nonce/reset controls and debug KEY readback; authenticated fixture commands only, no production security claim',
        elf=(out/'secure_app_test.elf').relative_to(ROOT).as_posix(),elf_sha256=hashlib.sha256((out/'secure_app_test.elf').read_bytes()).hexdigest(),
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(files)},
        generated_sha256=hashlib.sha256((out/'secure_main.c').read_bytes()).hexdigest(),command=command)
    (out/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n');print('SECURE_APP_TEST_BUILD_PASS',out)

if __name__=='__main__':main()
