"""Replay budget command packets and raw UART replies, with independent tag/PA checks."""
from pathlib import Path
import argparse,csv,hashlib,json,re,struct,sys,zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
import pa_model as pa
import ir_model as ir
import puncture as pu
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path)
args=ap.parse_args();folder=args.run.resolve();result=json.loads((folder/'result.json').read_text())
assert result['complete'] and result['hardware_capture']
uart=(folder/'uart.log').read_text();xsct=(folder/'xsct.log').read_text(errors='replace')
assert 'ZC702_PROGRAM_MMIO_PASS' in xsct and 'ZC702_SMOKE_CPU_STARTED' in xsct
assert not re.search(r'FATAL|TIMEOUT|DMA_ERROR|MISMATCH',uart)
fixture=ROOT/result['fixture']['file'];raw=fixture.read_bytes()
assert hashlib.sha256(raw).hexdigest()==result['fixture']['sha256']
vector=struct.unpack('<'+'I'*(len(raw)//4),raw);cfg,cfg2,pre,attempts,ns,err,nrev=vector[:7]
assert attempts==1 and pre==nrev==0
expected_key=[vector[i]|vector[i+1]<<32 for i in range(9+192+ns,len(vector),2)]
captured=[int(v,16) for v in re.findall(r'QKD_FUNC_KEY seq=\d+ word=\d+ value=([0-9a-fA-F]{16})',uart)]
assert captured and len(captured)%48==0
for start in range(0,len(captured),48):assert captured[start:start+48]==expected_key
bits=np.unpackbits(np.frombuffer(struct.pack('<48Q',*expected_key),dtype=np.uint8),bitorder='little')
positions=list(map(int,pu.order(ir.CODE_ORDER[cfg&3],ir.load_codes(128)[ir.CODE_ORDER[cfg&3]],128,307)))
mask=np.ones(3072,dtype=bool);mask[positions]=False;x=np.pad(bits[mask],(0,19))
def hash64(seed):
    sb=np.unpackbits(np.frombuffer(struct.pack('<120I',*seed),dtype=np.uint8),bitorder='little')
    return list(map(int,np.frombuffer(np.packbits(pa.pa_hash(x,sb),bitorder='little').tobytes(),dtype='<u8')))
used=0;limit=18446;bad=good=blocked=0;states=0;active=False;frames=json.loads((folder/'tx_manifest.json').read_text())
for packet in frames:
    data=(folder/packet['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==packet['sha256'] and f'{zlib.crc32(data):08x}'==packet['crc32']
    values=struct.unpack('<'+'I'*(len(data)//4),data);seq=packet['seq'];op=values[0]
    assert op==packet['op']
    replies=re.findall(fr'^QKD_(?:FUNC|STREAM)_[^\r\n]*\bseq={seq}\b[^\r\n]*',uart,re.MULTILINE)
    text='\n'.join(replies)
    if op==72:
        requested=values[1]
        if 'BUDGET_SET' in text:
            assert used<=requested<=limit;limit=requested
            assert f'used={used} limit={limit}' in text
        else:
            assert 'BUDGET_REJECT' in text and (requested>limit or requested<used or active)
            assert f'used={used} limit={limit}' in text
    elif op==73:
        assert f'used={used} limit={limit} remaining={limit-used}' in text;states+=1
    elif op==10:
        assert 'LOADED' in text;active=True
    elif op==11:
        reply=re.search(r'status=([0-9a-fA-F]+)',text);assert reply
        if int(reply.group(1),16)&1:active=False
    elif op in [20,60]:
        if 'VERIFY_LIMIT' in text:
            assert used==limit and f'used={used} limit={limit}' in text
            assert not re.search(r'QKD_FUNC_PA |PIPE_PASS|STREAM_ADDED',text);blocked+=1;continue
        if 'STREAM_REJECT' in text:continue
        assert used<limit;used+=1
        seed=values[309:429] if op==20 else values[12:132]
        tag_at=429 if op==20 else 132
        tag=values[tag_at]|values[tag_at+1]<<32
        if 'TAG_REJECT' in text:
            assert tag!=hash64(seed)[0];bad+=1
            assert not re.search(r'QKD_FUNC_PA |PIPE_PASS|STREAM_ADDED',text)
        else:
            assert tag==hash64(seed)[0];good+=1
            if op==20:
                expected=hash64(values[431:551])
                received=[int(v,16) for v in re.findall(r'QKD_FUNC_PA seq=\d+ word=\d+ value=([0-9a-fA-F]{16})',text)]
                assert received==expected and 'PIPE_PASS' in text
            else:assert 'STREAM_ADDED' in text
for check in result['checks']:
    assert check['pass']
    if 'reply' in check:assert check['reply'] in uart
assert (used,limit,bad,good,blocked)==(6,6,4,2,2)
out=ROOT/'reports'/('zc702_verification_budget_'+result['started_utc']);out.mkdir(parents=True,exist_ok=True)
with (out/'checks.csv').open('w',encoding='utf-8-sig',newline='') as f:
    fields=list(dict.fromkeys(k for r in result['checks'] for k in r))
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(result['checks'])
proof={'raw_replay_verified':True,'checks':len(result['checks']),'packets':len(frames),'budget_states_verified':states,
       'tag_hashes_checked':used,'valid_tags':good,'rejected_tags':bad,'blocked_on_exhaustion':blocked,
       'source_result_sha256':hashlib.sha256((folder/'result.json').read_bytes()).hexdigest(),
       'source_uart_sha256':hashlib.sha256((folder/'uart.log').read_bytes()).hexdigest(),
       'scope':'Boot-lifetime engineering gate; persistent authenticated-session budget and security proof remain pending'}
(out/'verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
(out/'REPORT.md').write_text('# Kiểm chứng giới hạn xác minh tag trên ZC702\n\n'
    f'PASS {len(result["checks"])} kiểm tra; replay {len(frames)} packet TX và UART thô. '
    'Fixture khóa công khai mô phỏng, kiểm tra toàn bộ KEY và PA1024 với tham chiếu.\n\n'
    '- Hai entry point op20/op60 dùng chung bộ đếm; 2 tag đúng + 4 tag sai = 6 lượt.\n'
    '- Hết cap=6: cả hai đường bị chặn, không append/output mới và input staging mất hiệu lực.\n'
    '- Reset controller/accumulator/buffer không hoàn lại ngân sách; host chỉ được giảm cap và không thể giảm dưới used.\n'
    '- Packet bị từ chối trước xác minh và yêu cầu PA thiếu seed không tiêu hao lượt.\n'
    '- Mặc định mỗi lần khởi động firmware: 18.446 lượt, tương ứng union bound 18.446/2^64 dưới 1e-15 '
    'theo giả định hash/seed phù hợp; phép thử hạ cap xuống 6 để kiểm tra biên nhanh.\n\n'
    '**Giới hạn:** bộ đếm chưa bền vững qua reset CPU/nạp ELF/mất nguồn; chưa gắn session ID xác thực và '
    'chưa giải quyết toàn bộ phân bổ composable epsilon, adaptive selection hoặc nguồn entropy. '
    'Không gọi đây là chứng nhận bảo mật QKD. Không tiêm lỗi DMA trong phép thử này.\n\n'
    f'Raw run: `build/zc702/verification_budget_runs/{result["started_utc"]}/`. '
    'Xem `checks.csv` và `verified_evidence.json`.\n',encoding='utf-8')
print('VERIFICATION_BUDGET_RAW_REPLAY_PASS',out,flush=True)
