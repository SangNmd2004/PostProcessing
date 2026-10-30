"""Host-only PSK bootstrap prototype using HMAC-SHA256 and RFC5869 HKDF.

Four messages confirm the transcript and fresh peer nonces before provisioning.
Not a standardized handshake, not forward secret, not implemented on ARM, and
not an information-theoretic QKD authentication or durable accounting proof.
"""
from dataclasses import dataclass,field
import hashlib,hmac,secrets,struct
from qas2_pc import Session,MAX_PACKETS


class BootstrapError(ValueError):pass


def hkdf_sha256(ikm,salt,info,length):
    if not 0<=length<=255*32:raise ValueError('Invalid HKDF length')
    prk=hmac.digest(salt or bytes(32),ikm,'sha256');out=b'';last=b''
    for i in range(1,(length+31)//32+1):
        last=hmac.digest(prk,last+info+bytes([i]),'sha256');out+=last
    return out[:length]


@dataclass(frozen=True,repr=False)
class Provisioning:
    role:int
    sid:bytes
    key_ab:bytes=field(repr=False)
    key_ba:bytes=field(repr=False)
    packet_limit:int
    def open_pc_session(self):
        session=Session();session.open(self.role,self.sid,self.key_ab,self.key_ba,self.packet_limit)
        return session


class Bootstrap:
    """One handshake object per connection, single-threaded owner.

    A root PSK and fixed peer IDs must be installed over a TRUSTED mechanism.
    nonce_source defaults to OS CSPRNG; deterministic injection is for tests only.
    Abort requires a NEW object/new nonces. Never serialize/reuse Provisioning.
    """
    def __init__(self,role,psk,alice_id,bob_id,packet_limit,nonce_source=secrets.token_bytes):
        if (type(role) is not int or role not in (0,1) or
            not isinstance(psk,bytes) or len(psk)!=32 or not any(psk) or
            any(not isinstance(x,bytes) or len(x)!=16 or not any(x) for x in (alice_id,bob_id)) or
            alice_id==bob_id or type(packet_limit) is not int or not 1<=packet_limit<=MAX_PACKETS):
            raise BootstrapError('Invalid trusted provisioning')
        self.role=role;self._psk=psk;self._a=alice_id;self._b=bob_id
        self.limit=packet_limit;self._nonce_source=nonce_source;self.state='NEW'
        self._ch=self._sh=self._na=self._nb=b'';self._material=None
        self._cf_key=self._sf_key=b''

    def abort(self):
        self.state='CLOSED';self._psk=self._cf_key=self._sf_key=b''
        self._material=None;self._ch=self._sh=self._na=self._nb=b''

    def _fail(self,message):self.abort();raise BootstrapError(message)

    def _expect(self,role,state):
        if self.role!=role or self.state!=state:self._fail('Unexpected handshake state')

    def _nonce(self):
        nonce=self._nonce_source(32)
        if not isinstance(nonce,bytes) or len(nonce)!=32 or not any(nonce):self._fail('Invalid nonce source')
        return nonce

    @staticmethod
    def _tag(key,label,payload):return hmac.digest(key,b'QKD/QAS2/bootstrap/v1/'+label+b'\0'+payload,'sha256')

    def _verify(self,packet,kind,size,key,label):
        if not isinstance(packet,bytes) or len(packet)!=size+32 or packet[:5]!=b'QBH1'+bytes([kind]):
            self._fail('Invalid bootstrap frame')
        if not hmac.compare_digest(packet[size:],self._tag(key,label,packet[:size])):
            self._fail('Bootstrap authentication failed')
        return packet[:size]

    def _derive(self,limit):
        self._transcript=hashlib.sha256(self._ch+self._sh).digest()
        salt=self._na+self._nb
        def derive(label,n):
            return hkdf_sha256(self._psk,salt,b'QKD/QAS2/session/v1/'+self._transcript+b'/'+label,n)
        self._material=Provisioning(self.role,derive(b'sid',16),derive(b'alice-to-bob',16),derive(b'bob-to-alice',16),limit)
        self._cf_key=derive(b'client-finished',32);self._sf_key=derive(b'server-finished',32)

    def client_hello(self):
        self._expect(0,'NEW');self._na=self._nonce()
        body=b'QBH1\x01'+self._a+self._b+self._na+struct.pack('<I',self.limit)
        self._ch=body+self._tag(self._psk,b'client-hello',body);self.state='WAIT_SERVER'
        return self._ch

    def server_hello(self,client_hello):
        self._expect(1,'NEW')
        body=self._verify(client_hello,1,73,self._psk,b'client-hello')
        if body[5:21]!=self._a or body[21:37]!=self._b or not any(body[37:69]):self._fail('Peer identity/nonce mismatch')
        proposed=struct.unpack('<I',body[69:73])[0]
        if not 1<=proposed<=MAX_PACKETS:self._fail('Invalid packet limit')
        self._na=body[37:69];self._nb=self._nonce();self._ch=client_hello
        chosen=min(proposed,self.limit)
        reply=b'QBH1\x02'+hashlib.sha256(client_hello).digest()+self._nb+struct.pack('<I',chosen)
        self._sh=reply+self._tag(self._psk,b'server-hello',reply)
        self._derive(chosen);self.state='WAIT_CLIENT_FINISHED'
        return self._sh

    def client_finished(self,server_hello):
        self._expect(0,'WAIT_SERVER')
        body=self._verify(server_hello,2,73,self._psk,b'server-hello')
        chosen=struct.unpack('<I',body[69:73])[0]
        if body[5:37]!=hashlib.sha256(self._ch).digest() or not any(body[37:69]) or not 1<=chosen<=self.limit:
            self._fail('Transcript/limit mismatch')
        self._nb=body[37:69];self._sh=server_hello;self._derive(chosen)
        payload=b'QBH1\x03'+self._transcript
        self.state='WAIT_SERVER_FINISHED'
        return payload+self._tag(self._cf_key,b'client-finished',payload)

    def server_finished(self,client_finished):
        self._expect(1,'WAIT_CLIENT_FINISHED')
        body=self._verify(client_finished,3,37,self._cf_key,b'client-finished')
        if body[5:]!=self._transcript:self._fail('Transcript mismatch')
        reply=b'QBH1\x04'+self._transcript
        packet=reply+self._tag(self._sf_key,b'server-finished',reply)
        self.state='ESTABLISHED';self._psk=self._cf_key=self._sf_key=b''
        return packet

    def accept_server_finished(self,packet):
        self._expect(0,'WAIT_SERVER_FINISHED')
        body=self._verify(packet,4,37,self._sf_key,b'server-finished')
        if body[5:]!=self._transcript:self._fail('Transcript mismatch')
        self.state='ESTABLISHED';self._psk=self._cf_key=self._sf_key=b''

    def take_provisioning(self):
        if self.state!='ESTABLISHED':self._fail('Session not confirmed or already consumed')
        material=self._material;self._material=None;self.state='CONSUMED'
        return material
