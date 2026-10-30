"""Transport-independent PC codec for the volatile QAS2 computational prototype.

Does not open UART, provision trust, persist state, or establish QKD security.
Python reset drops key references; it does not guarantee physical memory erasure.
"""
import hmac
import struct
from enum import IntEnum

HEADER=struct.Struct('<4sBBH16sII')
MAX_PAYLOAD=16384
MAX_PACKETS=1000000
MASK=(1<<64)-1


class Status(IntEnum):
    OK=0
    CLOSED=-1
    ARGUMENT=-2
    FORMAT=-3
    SESSION=-4
    DIRECTION=-5
    REPLAY=-6
    BAD_TAG=-7
    EXHAUSTED=-8
    CAPACITY=-9


class SessionError(ValueError):
    def __init__(self,status):
        self.status=Status(status)
        super().__init__(self.status.name)


def siphash24(key,message):
    """Standard SipHash-2-4, arbitrary byte message, returns eight LE tag bytes."""
    if len(key)!=16:
        raise ValueError('SipHash requires exactly 16 key bytes')
    k0,k1=struct.unpack('<QQ',key)
    v=[0x736f6d6570736575^k0,0x646f72616e646f6d^k1,
       0x6c7967656e657261^k0,0x7465646279746573^k1]
    def rotate(x,n):return ((x<<n)|(x>>(64-n)))&MASK
    def rounds(n):
        for _ in range(n):
            v[0]=(v[0]+v[1])&MASK;v[1]=rotate(v[1],13)^v[0];v[0]=rotate(v[0],32)
            v[2]=(v[2]+v[3])&MASK;v[3]=rotate(v[3],16)^v[2]
            v[0]=(v[0]+v[3])&MASK;v[3]=rotate(v[3],21)^v[0]
            v[2]=(v[2]+v[1])&MASK;v[1]=rotate(v[1],17)^v[2];v[2]=rotate(v[2],32)
    boundary=len(message)//8*8
    for at in range(0,boundary,8):
        m=int.from_bytes(message[at:at+8],'little')
        v[3]^=m;rounds(2);v[0]^=m
    tail=((len(message)&255)<<56)|int.from_bytes(message[boundary:],'little')
    v[3]^=tail;rounds(2);v[0]^=tail;v[2]^=255;rounds(4)
    return struct.pack('<Q',v[0]^v[1]^v[2]^v[3])


class Session:
    """Explicit trusted provisioning; callers must enforce fresh SID and keys."""
    def __init__(self):self.reset()

    def reset(self):
        self.active=False
        self._sid=self._tx_key=self._rx_key=b''
        self.tx_next=self.rx_last=self.tx_used=self.rx_checks=self.limit=0
        self.direction=0

    def open(self,role,sid,alice_to_bob,bob_to_alice,packet_limit):
        if (self.active or type(role) is not int or role not in (0,1) or
            type(packet_limit) is not int or not 1<=packet_limit<=MAX_PACKETS or
            any(not isinstance(x,(bytes,bytearray)) for x in (sid,alice_to_bob,bob_to_alice)) or
            any(len(x)!=16 or not any(x) for x in (sid,alice_to_bob,bob_to_alice)) or
            hmac.compare_digest(alice_to_bob,bob_to_alice)):
            raise SessionError(Status.ARGUMENT)
        self.reset()
        self._sid=bytes(sid)
        self._tx_key=bytes(alice_to_bob if role==0 else bob_to_alice)
        self._rx_key=bytes(bob_to_alice if role==0 else alice_to_bob)
        self.direction=role;self.tx_next=1;self.limit=packet_limit;self.active=True

    def wrap(self,opcode,payload):
        if not isinstance(payload,(bytes,bytearray)) or len(payload)>MAX_PAYLOAD or type(opcode) is not int or not 0<=opcode<=65535:
            raise SessionError(Status.ARGUMENT)
        if not self.active:raise SessionError(Status.CLOSED)
        if self.tx_used>=self.limit or self.tx_next>=0xffffffff:raise SessionError(Status.EXHAUSTED)
        body=HEADER.pack(b'QAS2',2,self.direction,opcode,self._sid,self.tx_next,len(payload))+bytes(payload)
        frame=body+siphash24(self._tx_key,body)
        self.tx_next+=1;self.tx_used+=1
        return frame

    def unwrap(self,frame):
        if not self.active:raise SessionError(Status.CLOSED)
        if not isinstance(frame,(bytes,bytearray)):raise SessionError(Status.ARGUMENT)
        if not 40<=len(frame)<=MAX_PAYLOAD+40:raise SessionError(Status.FORMAT)
        # Verify and return bytes from the SAME immutable snapshot.
        frame=bytes(frame)
        magic,version,direction,opcode,sid,seq,length=HEADER.unpack_from(frame)
        if magic!=b'QAS2' or version!=2 or length>MAX_PAYLOAD or len(frame)!=40+length:
            raise SessionError(Status.FORMAT)
        if not hmac.compare_digest(sid,self._sid):raise SessionError(Status.SESSION)
        if direction!=(self.direction^1):raise SessionError(Status.DIRECTION)
        if not seq or seq<=self.rx_last:raise SessionError(Status.REPLAY)
        if self.rx_checks>=self.limit:raise SessionError(Status.EXHAUSTED)
        self.rx_checks+=1
        if not hmac.compare_digest(siphash24(self._rx_key,frame[:-8]),frame[-8:]):
            raise SessionError(Status.BAD_TAG)
        self.rx_last=seq
        return opcode,bytes(frame[32:-8])


class StreamDecoder:
    """Bounded partial-frame collector; emitted frames STILL REQUIRE MAC checks.

    Malformed headers clear the partial buffer and raise; no silent resync or
    automatic session reopen. Internal buffer never exceeds one maximum frame.
    """
    def __init__(self):self.reset()
    def reset(self):self.buffer=bytearray();self.needed=32
    def feed(self,chunk):
        result=[];at=0
        while at<len(chunk):
            take=min(self.needed-len(self.buffer),len(chunk)-at)
            self.buffer.extend(chunk[at:at+take]);at+=take
            if len(self.buffer)!=self.needed:continue
            if self.needed==32:
                magic,version,_,_,_,_,size=HEADER.unpack(self.buffer)
                if magic!=b'QAS2' or version!=2 or size>MAX_PAYLOAD:
                    self.reset();raise SessionError(Status.FORMAT)
                self.needed=40+size
            else:
                result.append(bytes(self.buffer));self.reset()
        return result
