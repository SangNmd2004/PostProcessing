"""Logged request/response transport for physical functional tests."""
from pathlib import Path
from zipfile import ZipFile
import hashlib,json,re,struct,subprocess,sys,time,zlib
import serial
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/zc702'

class UARTSession:
    def __init__(self,folder,port='COM3',profile_transport=False):
        self.folder=Path(folder);self.port=port;self.seq=0;self.pending=bytearray();self.process=None
        self.frames=[]
        self.profile_transport=profile_transport;self.host_timings=[]
    def __enter__(self):
        subprocess.run([sys.executable,str(ROOT/'syn/zc702/verify_bundle.py')],check=True)
        self.manifest=json.loads((OUT/'uart_firmware/manifest.json').read_text())
        for name,digest in self.manifest['files'].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('artifact/source mismatch: '+name)
        self.folder.mkdir(parents=True,exist_ok=True);(self.folder/'tx_packets').mkdir()
        (self.folder/'firmware_manifest.json').write_text(json.dumps(self.manifest,indent=2)+'\n')
        self.uart=serial.Serial(self.port,115200,timeout=.1,write_timeout=5)
        self.log=(self.folder/'uart.log').open('wb');self.xlog=(self.folder/'xsct.log').open('wb')
        try:
            self.uart.reset_input_buffer()
            with ZipFile(OUT/'qkd_zc702.xsa') as z:(OUT/'ps7_init.tcl').write_bytes(z.read('ps7_init.tcl'))
            self.process=subprocess.Popen(['D:/Xilinx/Vitis/2020.2/bin/xsct.bat',str(ROOT/'syn/zc702/program_smoke.tcl'),'uart'],
                cwd=ROOT,stdout=self.xlog,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            self.expect(r'QKD_UART_READY version=1 max_words=4096',120)
            self.process.wait(timeout=30);self.xlog.flush()
            text=(self.folder/'xsct.log').read_text(errors='replace')
            if self.process.returncode or 'ZC702_PROGRAM_MMIO_PASS' not in text or 'ZC702_SMOKE_CPU_STARTED' not in text:
                raise RuntimeError('programming receipt missing')
        except BaseException:
            self.__exit__(*sys.exc_info());raise
        return self
    def expect(self,pattern,timeout=60):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if b'\n' in self.pending:
                raw,_,tail=self.pending.partition(b'\n');self.pending[:]=tail
                text=raw.decode(errors='replace').strip()
                if re.search(r'FATAL|TIMEOUT|DMA_ERROR|MISMATCH',text):raise RuntimeError(text)
                found=re.fullmatch(pattern,text)
                if found:return found
                if text.startswith(('QKD_UART_','QKD_FUNC_','QKD_STREAM_')):raise RuntimeError('unexpected: '+text)
                continue
            chunk=self.uart.read(max(1,self.uart.in_waiting))
            if chunk:self.pending.extend(chunk);self.log.write(chunk);self.log.flush()
            if self.process.poll() not in (None,0):raise RuntimeError('JTAG failure')
        raise TimeoutError(pattern)
    def command(self,values,pattern=None):
        seq=self.seq;self.seq+=1
        if not 0<len(values)<=4096:raise ValueError('packet size')
        payload=struct.pack('<'+'I'*len(values),*map(int,values));name=f'tx_packets/{seq:06d}.bin'
        (self.folder/name).write_bytes(payload)
        self.frames.append({'seq':seq,'op':int(values[0]),'file':name,'bytes':len(payload),
                            'crc32':f'{zlib.crc32(payload):08x}','sha256':hashlib.sha256(payload).hexdigest()})
        started=time.perf_counter_ns() if self.profile_transport else 0
        self.uart.write(struct.pack('<4I',0x51465532,seq,len(values),zlib.crc32(payload)))
        self.expect(fr'QKD_UART_ACCEPT seq={seq}')
        for offset in range(0,len(payload),128):
            chunk=payload[offset:offset+128];self.uart.write(chunk)
            self.expect(fr'QKD_UART_ACK seq={seq} bytes={offset+len(chunk)}')
        if self.profile_transport:
            self.host_timings.append({'seq':seq,'op':int(values[0]),'payload_bytes':len(payload),
                'start_ns':started,'last_ack_ns':time.perf_counter_ns(),'response_complete_ns':None})
        reply=self.expect(pattern.replace('{seq}',str(seq))) if pattern else None
        if pattern and self.profile_transport:self.complete_response(seq)
        return seq,reply
    def complete_response(self,seq):
        if self.profile_transport:
            row=next(r for r in reversed(self.host_timings) if r['seq']==seq)
            row['response_complete_ns']=time.perf_counter_ns()
    def __exit__(self,*unused):
        if self.process is not None and self.process.poll() is None:self.process.terminate()
        for obj in [getattr(self,'uart',None),getattr(self,'log',None),getattr(self,'xlog',None)]:
            if obj is not None:obj.close()
        (self.folder/'tx_manifest.json').write_text(json.dumps(self.frames,indent=2)+'\n')
        if self.profile_transport:
            (self.folder/'host_timings.json').write_text(json.dumps(self.host_timings,indent=2)+'\n')
