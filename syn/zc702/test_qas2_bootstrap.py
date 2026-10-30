"""RFC primitive vectors, hostile transcript tests, and derived-key host C interop."""
from pathlib import Path
import argparse,ctypes as C,hashlib,hmac,json,random,subprocess
from qas2_bootstrap import Bootstrap,BootstrapError,hkdf_sha256
from qas2_pc import SessionError,Status
ROOT=Path(__file__).resolve().parents[2]

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path)
    args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    checks=0;categories={};rng=random.Random(2026102702)
    psk=bytes(range(1,33));aid=bytes(range(1,17));bid=bytes(range(17,33))
    def check(value,category):
        nonlocal checks
        checks+=1;categories[category]=categories.get(category,0)+1;assert value,(category,checks)
    def pair(alimit=100,blimit=50):
        return (Bootstrap(0,psk,aid,bid,alimit,nonce_source=rng.randbytes),
                Bootstrap(1,psk,aid,bid,blimit,nonce_source=rng.randbytes))
    def exchange(a,b):
        ch=a.client_hello();sh=b.server_hello(ch);cf=a.client_finished(sh);sf=b.server_finished(cf)
        a.accept_server_finished(sf);return ch,sh,cf,sf
    def rejected(callback,peer,category):
        try:callback()
        except BootstrapError:check(peer.state=='CLOSED',category)
        else:raise AssertionError('hostile handshake accepted: '+category)
    check(hmac.digest(bytes([0x0b])*20,b'Hi There','sha256').hex()==
          'b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7','rfc4231_hmac_case1')
    check(hkdf_sha256(bytes([0x0b])*22,bytes(range(13)),bytes(range(0xf0,0xfa)),42).hex()==
          '3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865','rfc5869_hkdf_case1')
    check(hkdf_sha256(bytes([0x0b])*22,b'',b'',42).hex()==
          '8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d9d201395faa4b61a96c8','rfc5869_hkdf_case3')
    # Compile the real QAS2 C endpoint, not a second Python mock.
    command=['C:/msys64/mingw64/bin/gcc.exe','-shared','-std=c11','-O2','-Wall','-Wextra','-Werror',
             str(ROOT/'syn/zc702/tests/auth_session_bridge.c'),str(ROOT/'firmware/zc702_uart/auth_session.c'),
             str(ROOT/'firmware/crypto/siphash.c'),'-o',str(out/'bootstrap_bridge.dll')]
    compiled=subprocess.run(command,capture_output=True,text=True)
    (out/'compile.stdout.log').write_text(compiled.stdout);(out/'compile.stderr.log').write_text(compiled.stderr)
    assert compiled.returncode==0
    lib=C.CDLL(str(out/'bootstrap_bridge.dll'));p=C.c_void_p;u32=C.c_uint32;u16=C.c_uint16
    for name,types,result in [('bridge_new',[],p),('bridge_delete',[p],None),
        ('bridge_open',[p,C.c_int,p,p,p,u32],C.c_int),
        ('bridge_wrap',[p,u16,p,u32,p,u32,C.POINTER(u32)],C.c_int),
        ('bridge_unwrap',[p,p,u32,C.POINTER(u16),p,C.POINTER(u32)],C.c_int)]:
        getattr(lib,name).argtypes=types;getattr(lib,name).restype=result
    def buf(data):return C.create_string_buffer(data)
    session_ids=set();first_messages=None;first_frame=None;first_material=None
    for i in range(100):
        a,b=pair();messages=exchange(a,b);ma=a.take_provisioning();mb=b.take_provisioning()
        check(ma.sid==mb.sid and ma.key_ab==mb.key_ab and ma.key_ba==mb.key_ba,'matching_material')
        check(ma.packet_limit==mb.packet_limit==50 and ma.key_ab!=ma.key_ba,'policy_key_separation')
        check(ma.sid not in session_ids,'fresh_test_sessions');session_ids.add(ma.sid)
        alice=ma.open_pc_session();frame=alice.wrap(10,b'synthetic Alice payload')
        h=lib.bridge_new();assert h
        try:
            check(lib.bridge_open(h,1,buf(mb.sid),buf(mb.key_ab),buf(mb.key_ba),mb.packet_limit)==0,'derived_C_provisioning')
            raw=C.create_string_buffer(16384);length=u32();op=u16()
            check(lib.bridge_unwrap(h,buf(frame),len(frame),C.byref(op),raw,C.byref(length))==0 and
                  op.value==10 and raw.raw[:length.value]==b'synthetic Alice payload','derived_PC_to_C')
            packet=C.create_string_buffer(16424);written=u32();answer=b'synthetic Bob reply'
            check(lib.bridge_wrap(h,11,buf(answer),len(answer),packet,len(packet),C.byref(written))==0,'derived_C_to_PC')
            check(alice.unwrap(packet.raw[:written.value])==(11,answer),'derived_C_to_PC')
        finally:lib.bridge_delete(h)
        rejected(a.take_provisioning,a,'single_use_export')
        if first_messages is None:first_messages=messages;first_frame=frame;first_material=mb
    # Flip every byte of each of the four message types in a fresh exchange.
    for stage,size in enumerate([105,105,69,69]):
        for at in range(size):
            a,b=pair();ch=a.client_hello()
            if stage==0:
                bad=bytearray(ch);bad[at]^=1;rejected(lambda:b.server_hello(bytes(bad)),b,'tamper_client_hello');continue
            sh=b.server_hello(ch)
            if stage==1:
                bad=bytearray(sh);bad[at]^=1;rejected(lambda:a.client_finished(bytes(bad)),a,'tamper_server_hello');continue
            cf=a.client_finished(sh)
            if stage==2:
                bad=bytearray(cf);bad[at]^=1;rejected(lambda:b.server_finished(bytes(bad)),b,'tamper_client_finished');continue
            sf=b.server_finished(cf);bad=bytearray(sf);bad[at]^=1
            rejected(lambda:a.accept_server_finished(bytes(bad)),a,'tamper_server_finished')
    a,b=pair();rejected(a.take_provisioning,a,'unconfirmed_export')
    a,b=pair();b.server_hello(a.client_hello());rejected(b.take_provisioning,b,'unconfirmed_export')
    broken=Bootstrap(0,psk,aid,bid,50,nonce_source=lambda n:bytes(n))
    rejected(broken.client_hello,broken,'invalid_nonce_source')
    a,b=pair();ch=a.client_hello();other_id=bytes([0x70])*16
    wrong_id=Bootstrap(1,psk,other_id,bid,50,nonce_source=rng.randbytes)
    rejected(lambda:wrong_id.server_hello(ch),wrong_id,'wrong_peer_identity')
    a,b=pair();ch=a.client_hello();wrong=Bootstrap(1,bytes([0x55])*32,aid,bid,50,nonce_source=rng.randbytes)
    rejected(lambda:wrong.server_hello(ch),wrong,'wrong_psk')
    # Replayed CH is authenticated but cannot finish against a fresh Bob nonce.
    old_ch,old_sh,old_cf,old_sf=first_messages
    _,b=pair();b.server_hello(old_ch);rejected(lambda:b.server_finished(old_cf),b,'replayed_client_finished')
    a,b=pair();ch=a.client_hello();rejected(lambda:a.client_finished(old_sh),a,'mixed_transcript')
    a,b=pair();sh=b.server_hello(a.client_hello());a.client_finished(sh)
    rejected(lambda:a.accept_server_finished(old_sf),a,'replayed_server_finished')
    _,b=pair();exchange_a,_=pair();messages=exchange(exchange_a,b);fresh=b.take_provisioning().open_pc_session()
    try:fresh.unwrap(first_frame)
    except SessionError as exc:check(exc.status==Status.SESSION,'old_data_in_new_session')
    else:raise AssertionError('old data accepted by fresh handshake session')
    # Deterministic nonce reuse at BOTH ends remains an explicit failure mode.
    def fixed(_):return bytes([0x33])*32
    materials=[]
    for _ in range(2):
        a=Bootstrap(0,psk,aid,bid,100,nonce_source=fixed);b=Bootstrap(1,psk,aid,bid,50,nonce_source=fixed)
        exchange(a,b);materials.append(a.take_provisioning())
    check(materials[0].sid==materials[1].sid and materials[0].key_ab==materials[1].key_ab,'known_both_nonce_reuse_limitation')
    fixtures=[]
    for i,packet in enumerate(first_messages,1):
        filename=f'public_fixture_message_{i}.bin';(out/filename).write_bytes(packet)
        fixtures.append(dict(file=filename,bytes=len(packet),sha256=hashlib.sha256(packet).hexdigest()))
    source_files=['syn/zc702/qas2_bootstrap.py','syn/zc702/test_qas2_bootstrap.py','syn/zc702/qas2_pc.py',
                  'syn/zc702/tests/auth_session_bridge.c','firmware/zc702_uart/auth_session.c','firmware/zc702_uart/auth_session.h',
                  'firmware/crypto/siphash.c','firmware/crypto/siphash.h']
    receipt=dict(status='HOST_BOOTSTRAP_TRANSCRIPT_AND_C_DATA_INTEROP_PASS',checks=checks,categories=categories,
                 completed_host_handshakes=100,tampered_handshake_bytes=348,
                 primitives='HMAC-SHA256 RFC4231 case1; HKDF-SHA256 RFC5869 cases1,3',fixtures=fixtures,
                 source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_files},
                 fixture_seed=2026102702,compiler_command=command,hardware_capture=False,project_status='PARTIAL',
                 scope='Handshake runs in Python at both ends; derived keys provision real host C QAS2 data endpoint; no ARM handshake/UART/durable accounting',
                 limitations=['not a standardized or independently proven handshake','no forward secrecy','both nonce reuse repeats session keys','trusted root PSK provisioning and board entropy still missing','global correctness budget/power-loss rollback not solved'])
    (out/'BOOTSTRAP_TEST_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('QAS2_HOST_BOOTSTRAP_PASS',checks,'checks; 100 handshakes; 348 tampered bytes; host C data interop')

if __name__=='__main__':main()
