"""Build real C tests against a pinned independent SipHash reference, without UART/JTAG."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=ROOT/'reports/zc702_followthrough_20261027')
    args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    ref=ROOT/'syn/zc702/tests/reference'
    for item in json.loads((ref/'SOURCE.json').read_text()):
        assert hashlib.sha256((ref/item['file']).read_bytes()).hexdigest()==item['sha256']
    commands=[]
    def run(label,argv):
        p=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True)
        (out/(label+'.stdout.log')).write_text(p.stdout,encoding='utf-8')
        (out/(label+'.stderr.log')).write_text(p.stderr,encoding='utf-8')
        commands.append(dict(label=label,command=argv,returncode=p.returncode))
        assert p.returncode==0, f'{label} failed; see {out}'
        return p.stdout
    gcc=Path('C:/msys64/mingw64/bin/gcc.exe')
    exe=out/'auth_prototype_test.exe'
    run('host_compile',[str(gcc),'-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(ref),
                        str(ROOT/'syn/zc702/tests/auth_prototype_test.c'),str(ref/'siphash.c'),'-o',str(exe)])
    output=run('host_tests',[str(exe)])
    assert 'checks=8262 reference_pairs=4096' in output
    spec=importlib.util.spec_from_file_location('python_auth_reference',ROOT/'syn/zc702/test_auth_channel.py')
    model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    assert model.siphash24_64(0x0706050403020100,0x0f0e0d0c0b0a0908,0x0706050403020100)==0x93f5f5799a932462
    arm=Path('D:/Xilinx/Vitis/2020.2/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe')
    run('arm_compile',[str(arm),'-mcpu=cortex-a9','-mfpu=vfpv3','-mfloat-abi=hard','-O2','-Wall','-Wextra','-Werror',
                       '-I'+str(ROOT/'firmware/zc702_uart'),'-c',str(ROOT/'firmware/zc702_uart/auth_channel.c'),'-o',str(out/'auth_channel_arm.o')])
    manifest=json.loads((ROOT/'build/zc702/uart_firmware/manifest.json').read_text())
    for file,sha in manifest['files'].items():
        assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==sha,file
    files=['firmware/zc702_uart/auth_channel.c','firmware/zc702_uart/auth_channel.h','syn/zc702/test_auth_channel.py',
           'syn/zc702/tests/auth_prototype_test.c','syn/zc702/test_auth_prototype.py']
    receipt=dict(status='HOST_REGRESSION_AND_ARM_COMPILE_PASS',checks=8262,independent_reference_pairs=4096,
                 python_known_answer_pass=True,baseline_manifest_files_verified=len(manifest['files']),
                 commands=commands,source_sha256={file:hashlib.sha256((ROOT/file).read_bytes()).hexdigest() for file in files},
                 scope='Eight-byte SipHash algorithm and prototype packet regressions; ARM compile only; no board run or security certification',
                 persistence_after_reset='UNIMPLEMENTED',project_status='PARTIAL')
    (out/'AUTH_TEST_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(output.strip());print('ARM_AUTH_COMPILE_PASS; BASELINE_MANIFEST_PASS',len(manifest['files']))

if __name__=='__main__':main()
