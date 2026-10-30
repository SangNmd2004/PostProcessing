"""Host C SHA/HMAC/HKDF + Bob bootstrap compared with Python before board tests."""
from pathlib import Path
import argparse,ctypes as C,hashlib,hmac,json,random,subprocess
from qas2_bootstrap import Bootstrap,hkdf_sha256
ROOT=Path(__file__).resolve().parents[2]
SOURCES=['firmware/crypto/rfc6234/sha224-256.c','firmware/crypto/qcrypto.c','firmware/crypto/siphash.c',
         'firmware/zc702_uart/auth_session.c','firmware/zc702_uart/qas2_bootstrap.c',
         'syn/zc702/tests/auth_session_bridge.c','syn/zc702/tests/bootstrap_bridge.c']

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path)
    args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    command=['C:/msys64/mingw64/bin/gcc.exe','-shared','-std=c11','-O2','-Wall','-Wextra','-Werror',*[str(ROOT/f) for f in SOURCES],'-o',str(out/'bootstrap.dll')]
    p=subprocess.run(command,capture_output=True,text=True)
    (out/'compile.log').write_text(p.stdout+p.stderr);assert p.returncode==0
    lib=C.CDLL(str(out/'bootstrap.dll'));v=C.c_void_p;sz=C.c_size_t;u=C.c_uint32
    specs={'qb_new':([],v),'qb_delete':([v],None),'qboot_init':([v,v,v,v,u],C.c_int),
           'qboot_server_hello':([v,v,sz,v,v],C.c_int),'qboot_server_finished':([v,v,sz,v],C.c_int),
           'qboot_take_session':([v,v],C.c_int),'qcrypto_sha256':([v,sz,v],C.c_int),
           'qcrypto_hmac':([v,sz,v,sz,v],C.c_int),'qcrypto_hkdf':([v,sz,v,sz,v,sz,v,sz],C.c_int),
           'bridge_new':([],v),'bridge_delete':([v],None),
           'bridge_unwrap':([v,v,u,C.POINTER(C.c_uint16),v,C.POINTER(u)],C.c_int)}
    for name,(types,ret) in specs.items():getattr(lib,name).argtypes=types;getattr(lib,name).restype=ret
    def buf(x):return C.create_string_buffer(x)
    checks=0
    def check(x):
        nonlocal checks
        checks+=1;assert x,checks
    rng=random.Random(2026102703);psk=bytes(range(1,33));aid=bytes(range(1,17));bid=bytes(range(17,33))
    for i in range(180):
        n=[0,1,55,56,63,64,65,1000,16384][i%9];data=rng.randbytes(n);key=rng.randbytes([0,1,32,64,65,131][i%6]);answer=C.create_string_buffer(32)
        check(lib.qcrypto_sha256(buf(data),len(data),answer)==0 and answer.raw==hashlib.sha256(data).digest())
        check(lib.qcrypto_hmac(buf(key),len(key),buf(data),len(data),answer)==0 and answer.raw==hmac.digest(key,data,'sha256'))
        ikm=rng.randbytes(i%65);salt=rng.randbytes(i%41);info=rng.randbytes(i%129);length=[0,16,32,42,64,129,8160][i%7];okm=C.create_string_buffer(max(length,1))
        check(lib.qcrypto_hkdf(buf(ikm),len(ikm),buf(salt),len(salt),buf(info),len(info),okm,length)==0 and okm.raw[:length]==hkdf_sha256(ikm,salt,info,length))
    for i in range(100):
        na=rng.randbytes(32);nb=rng.randbytes(32);a=Bootstrap(0,psk,aid,bid,100,lambda n:na);b=Bootstrap(1,psk,aid,bid,50,lambda n:nb)
        ctx=lib.qb_new();session=lib.bridge_new()
        try:
            check(lib.qboot_init(ctx,buf(psk),buf(aid),buf(bid),50)==0)
            ch=a.client_hello();expected_sh=b.server_hello(ch);sh=C.create_string_buffer(105)
            check(lib.qboot_server_hello(ctx,buf(ch),len(ch),buf(nb),sh)==0 and sh.raw==expected_sh)
            cf=a.client_finished(sh.raw);expected_sf=b.server_finished(cf);sf=C.create_string_buffer(69)
            check(lib.qboot_server_finished(ctx,buf(cf),len(cf),sf)==0 and sf.raw==expected_sf)
            a.accept_server_finished(sf.raw);alice=a.take_provisioning().open_pc_session()
            check(lib.qboot_take_session(ctx,session)==0)
            frame=alice.wrap(10,b'host C derived-session check');op=C.c_uint16();n=u();payload=C.create_string_buffer(16384)
            check(lib.bridge_unwrap(session,buf(frame),len(frame),C.byref(op),payload,C.byref(n))==0 and payload.raw[:n.value]==b'host C derived-session check')
            check(lib.qboot_take_session(ctx,session)!=0)
        finally:lib.qb_delete(ctx);lib.bridge_delete(session)
    for kind,size in [('ch',105),('cf',69)]:
        for at in range(size):
            na=rng.randbytes(32);nb=rng.randbytes(32);a=Bootstrap(0,psk,aid,bid,100,lambda n:na);ch=a.client_hello();ctx=lib.qb_new()
            try:
                check(lib.qboot_init(ctx,buf(psk),buf(aid),buf(bid),50)==0);reply=C.create_string_buffer(105)
                if kind=='ch':
                    bad=bytearray(ch);bad[at]^=1
                    check(lib.qboot_server_hello(ctx,buf(bytes(bad)),len(bad),buf(nb),reply)!=0)
                else:
                    check(lib.qboot_server_hello(ctx,buf(ch),len(ch),buf(nb),reply)==0)
                    cf=bytearray(a.client_finished(reply.raw));cf[at]^=1
                    check(lib.qboot_server_finished(ctx,buf(bytes(cf)),len(cf),C.create_string_buffer(69))!=0)
                session=lib.bridge_new()
                try:check(lib.qboot_take_session(ctx,session)!=0)
                finally:lib.bridge_delete(session)
            finally:lib.qb_delete(ctx)
    files=SOURCES+['firmware/crypto/qcrypto.h','firmware/crypto/rfc6234/sha.h','firmware/crypto/rfc6234/sha-private.h',
                   'firmware/zc702_uart/qas2_bootstrap.h','firmware/zc702_uart/auth_session.h','syn/zc702/qas2_bootstrap.py','syn/zc702/qas2_pc.py','syn/zc702/test_c_bootstrap.py']
    receipt=dict(status='HOST_C_BOOTSTRAP_PASS',checks=checks,primitive_cases=180,completed_c_bob_handshakes=100,
                 tampered_c_input_bytes=174,source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},
                 scope='Real C crypto and Bob state machine on PC; not physical board proof')
    (out/'HOST_TEST_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('HOST_C_BOOTSTRAP_PASS',checks,'checks')

if __name__=='__main__':main()
