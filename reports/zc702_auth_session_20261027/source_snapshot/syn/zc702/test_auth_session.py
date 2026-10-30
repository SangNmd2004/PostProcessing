"""Validate the separate session prototype on host and compile for Cortex-A9."""
from pathlib import Path
import argparse,hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[2]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=ROOT/'reports/zc702_auth_session_20261027')
    args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    commands=[]
    def run(name,argv):
        p=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True)
        (out/(name+'.stdout.log')).write_text(p.stdout,encoding='utf-8')
        (out/(name+'.stderr.log')).write_text(p.stderr,encoding='utf-8')
        commands.append(dict(name=name,argv=argv,returncode=p.returncode))
        assert p.returncode==0,f'{name} failed; see {out}'
        return p.stdout
    for item in json.loads((ROOT/'firmware/crypto/SOURCE.json').read_text()):
        assert hashlib.sha256((ROOT/'firmware/crypto'/item['file']).read_bytes()).hexdigest()==item['sha256']
    c=ROOT/'firmware/zc702_uart/auth_session.c';ref=ROOT/'firmware/crypto/siphash.c'
    host='C:/msys64/mingw64/bin/gcc.exe';exe=out/'session_tests.exe'
    run('host_compile',[host,'-std=c11','-O2','-Wall','-Wextra','-Werror',str(ROOT/'syn/zc702/tests/auth_session_test.c'),str(c),str(ref),'-o',str(exe)])
    text=run('host_tests',[str(exe)])
    assert 'AUTH_SESSION_HOST_PASS' in text and 'KNOWN_LIMITATION' in text
    arm='D:/Xilinx/Vitis/2020.2/gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe'
    for name,file in [('session',c),('siphash',ref)]:
        run('arm_'+name,[arm,'-std=c11','-mcpu=cortex-a9','-mfpu=vfpv3','-mfloat-abi=hard','-O2','-Wall','-Wextra','-Werror','-c',str(file),'-o',str(out/(name+'_arm.o'))])
    manifest=json.loads((ROOT/'build/zc702/uart_firmware/manifest.json').read_text())
    for file,sha in manifest['files'].items():assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==sha,file
    sources=['firmware/zc702_uart/auth_session.c','firmware/zc702_uart/auth_session.h','firmware/crypto/siphash.c','firmware/crypto/siphash.h',
             'firmware/crypto/SOURCE.json','syn/zc702/tests/auth_session_test.c','syn/zc702/test_auth_session.py']
    receipt=dict(status='HOST_SESSION_REGRESSION_AND_ARM_COMPILE_PASS',commands=commands,
                 source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
                 baseline_manifest_verified_files=len(manifest['files']),hardware_rerun=False,
                 scope='Volatile computational session framing only; no trusted handshake, durable anti-rollback or QKD security certification',
                 known_limitation='Reprovisioning the old SID/keys after reset can accept old frames; caller must enforce freshness externally',
                 project_status='PARTIAL',host_output=text)
    (out/'SESSION_TEST_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(text.strip());print('ARM_SESSION_AND_REFERENCE_COMPILE_PASS; BASELINE_HASHES_PASS',len(manifest['files']))

if __name__=='__main__':main()
