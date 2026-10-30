"""Differential PC-Python / real C QAS2 tests; no UART or JTAG access."""
from pathlib import Path
import argparse,ctypes as C,hashlib,json,random,subprocess
from qas2_pc import Session,SessionError,Status,StreamDecoder,siphash24
ROOT=Path(__file__).resolve().parents[2]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',required=True,type=Path)
    args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    command=['C:/msys64/mingw64/bin/gcc.exe','-std=c11','-shared','-O2','-Wall','-Wextra','-Werror',
             str(ROOT/'syn/zc702/tests/auth_session_bridge.c'),str(ROOT/'firmware/zc702_uart/auth_session.c'),
             str(ROOT/'firmware/crypto/siphash.c'),'-o',str(out/'qas2_bridge.dll')]
    compiled=subprocess.run(command,capture_output=True,text=True)
    (out/'compile.stdout.log').write_text(compiled.stdout);(out/'compile.stderr.log').write_text(compiled.stderr)
    assert compiled.returncode==0
    lib=C.CDLL(str(out/'qas2_bridge.dll'));p=C.c_void_p;u32=C.c_uint32;u16=C.c_uint16
    specs={'bridge_new':([],p),'bridge_delete':([p],None),'bridge_reset':([p],None),
           'bridge_open':([p,C.c_int,p,p,p,u32],C.c_int),
           'bridge_wrap':([p,u16,p,u32,p,u32,C.POINTER(u32)],C.c_int),
           'bridge_unwrap':([p,p,u32,C.POINTER(u16),p,C.POINTER(u32)],C.c_int),
           'bridge_last':([p],u32),'bridge_checks':([p],u32),
           'siphash':([p,C.c_size_t,p,p,C.c_size_t],C.c_int)}
    for name,(types,result) in specs.items():
        getattr(lib,name).argtypes=types;getattr(lib,name).restype=result
    rng=random.Random(2026102701);sid=rng.randbytes(16);ab=rng.randbytes(16);ba=rng.randbytes(16)
    handles=[];categories={};checks=0;vectors=[]
    def check(condition,category):
        nonlocal checks
        checks+=1;categories[category]=categories.get(category,0)+1
        assert condition,(category,checks)
    def buf(data):return C.create_string_buffer(data)
    def new(role,limit=100000,identity=sid):
        h=lib.bridge_new();assert h;handles.append(h)
        assert lib.bridge_open(h,role,buf(identity),buf(ab),buf(ba),limit)==0
        s=Session();s.open(role,identity,ab,ba,limit);return h,s
    def cwrap(h,op,payload):
        frame=C.create_string_buffer(16424);n=u32()
        rc=lib.bridge_wrap(h,op,buf(payload),len(payload),frame,len(frame),C.byref(n))
        assert rc==0,rc
        return frame.raw[:n.value]
    def cunwrap(h,frame):
        data=C.create_string_buffer(16384);n=u32();op=u16()
        rc=lib.bridge_unwrap(h,buf(frame),len(frame),C.byref(op),data,C.byref(n))
        return rc,(op.value,data.raw[:n.value])
    def pyunwrap(s,frame):
        try:return 0,s.unwrap(frame)
        except SessionError as exc:return int(exc.status),(0,b'')
    try:
        check(siphash24(bytes(range(16)),b'').hex()=='310e0edd47db6f72','known_answers')
        check(siphash24(bytes(range(16)),bytes(range(8))).hex()=='6224939a79f5f593','known_answers')
        for i in range(300):
            key=rng.randbytes(16);message=rng.randbytes(i if i<256 else rng.randrange(16385));answer=C.create_string_buffer(8)
            check(lib.siphash(buf(message),len(message),buf(key),answer,8)==0,'primitive_reference')
            check(siphash24(key,message)==answer.raw,'primitive_reference')
        ca,pa=new(0);cb,pb=new(1)
        for i in range(512):
            size=[0,1,7,8,9,31,32,255,16384][i] if i<9 else rng.randrange(1025)
            payload=rng.randbytes(size);opcode=rng.randrange(65536)
            for ch,sender,receiver,pyreceiver,op in [(ca,pa,cb,pb,opcode),(cb,pb,ca,pa,opcode^0x8000)]:
                cf=cwrap(ch,op,payload);pf=sender.wrap(op,payload)
                check(cf==pf,'wire_equality')
                check(cunwrap(receiver,pf)==pyunwrap(pyreceiver,cf)==(0,(op,payload)),'bidirectional_receive')
                if len(vectors)<4:
                    file=f'fixture_{len(vectors):02d}.bin';(out/file).write_bytes(cf)
                    vectors.append(dict(file=file,bytes=len(cf),sha256=hashlib.sha256(cf).hexdigest(),scope='Public deterministic host-only fixture'))
        sender,py_sender=new(0);frame=cwrap(sender,17,bytes(range(64)))
        for i in range(len(frame)):
            h,s=new(1);changed=bytearray(frame);changed[i]^=1
            c_result=cunwrap(h,bytes(changed));p_result=pyunwrap(s,bytes(changed))
            check(c_result==p_result and c_result[0]!=0,'tamper_differential')
            check(lib.bridge_last(h)==s.rx_last==0 and lib.bridge_checks(h)==s.rx_checks,'rejection_state')
        h,s=new(1)
        check(cunwrap(h,frame)==pyunwrap(s,frame)==(0,(17,bytes(range(64)))),'replay')
        check(cunwrap(h,frame)==pyunwrap(s,frame)==(Status.REPLAY,(0,b'')),'replay')
        lib.bridge_reset(h);s.reset()
        check(cunwrap(h,frame)==pyunwrap(s,frame)==(Status.CLOSED,(0,b'')),'reset_closed')
        other=bytes([sid[0]^1])+sid[1:];h,s=new(1,identity=other)
        check(cunwrap(h,frame)==pyunwrap(s,frame)==(Status.SESSION,(0,b'')),'cross_session')
        h,s=new(0)
        check(cunwrap(h,frame)==pyunwrap(s,frame)==(Status.DIRECTION,(0,b'')),'reflection')
        h,s=new(1,limit=2);bad=bytearray(frame);bad[-1]^=1
        for status in [Status.BAD_TAG,Status.BAD_TAG,Status.EXHAUSTED]:
            check(cunwrap(h,bytes(bad))==pyunwrap(s,bytes(bad))==(status,(0,b'')),'failed_tag_budget')
        check(lib.bridge_checks(h)==s.rx_checks==2,'failed_tag_budget')
        # Known limitation remains explicit, never counted as anti-rollback proof.
        h,s=new(1)
        check(cunwrap(h,frame)==pyunwrap(s,frame)==(0,(17,bytes(range(64)))),'known_reprovision_limitation')
        frames=[frame,cwrap(sender,23,b''),cwrap(sender,24,rng.randbytes(16384))]
        stream=b''.join(frames);peak=0
        for chunk_size in [1,7,128,4096,len(stream)]:
            decoder=StreamDecoder();actual=[]
            for at in range(0,len(stream),chunk_size):
                actual+=decoder.feed(stream[at:at+chunk_size]);peak=max(peak,len(decoder.buffer))
                check(len(decoder.buffer)<=16424,'bounded_stream_buffer')
            check(actual==frames and not decoder.buffer,'stream_chunking')
        decoder=StreamDecoder();check(decoder.feed(frame[:31])==[],'partial_stream')
        decoder.reset();check(not decoder.buffer,'partial_stream')
        malformed=bytearray(frame[:32]);malformed[28:32]=(0xffffffff).to_bytes(4,'little')
        try:decoder.feed(malformed)
        except SessionError as exc:check(exc.status==Status.FORMAT and not decoder.buffer,'malformed_length')
        else:raise AssertionError('oversized stream header accepted')
        for role,limit in [(0.0,5),(0,2.5),(True,5),(0,True)]:
            s=Session()
            try:s.open(role,sid,ab,ba,limit)
            except SessionError as exc:check(exc.status==Status.ARGUMENT,'provision_argument_types')
            else:raise AssertionError('noninteger provisioning accepted')
    finally:
        for h in handles:lib.bridge_delete(h)
    sources=['syn/zc702/qas2_pc.py','syn/zc702/test_qas2_interop.py','syn/zc702/tests/auth_session_bridge.c',
             'firmware/zc702_uart/auth_session.c','firmware/zc702_uart/auth_session.h','firmware/crypto/siphash.c','firmware/crypto/siphash.h']
    receipt=dict(status='HOST_PYTHON_C_INTEROP_PASS',checks=checks,categories=categories,
                 primitive_reference_cases=300,bit_exact_bidirectional_frames=1024,
                 tampered_frame_bytes=len(frame),maximum_observed_partial_buffer_bytes=peak,
                 source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
                 fixture_seed=2026102701,fixtures=vectors,compiler_command=command,
                 hardware_capture=False,scope='PC simulation and real host C library; no UART/ARM execution/handshake/durable state',
                 known_limitation='Reopening old SID and keys after reset can permit replay',project_status='PARTIAL')
    (out/'INTEROP_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('QAS2_HOST_INTEROP_PASS',checks,'checks; 1024 bit-exact frames; 300 primitive cases')

if __name__=='__main__':main()
