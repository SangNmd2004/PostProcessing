"""Independently hash the actual DMA wrong key and Alice key using the transmitted tag seed."""
from pathlib import Path
import argparse,csv,hashlib,json,re,struct,sys,zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
import ir_model as m
import puncture as pu
import pa_model as pa
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path);args=ap.parse_args();folder=args.run.resolve()
result=json.loads((folder/'result.json').read_text());assert result['complete'] and result['hardware_capture']
source=json.loads((ROOT/result['source_ablation']/'result.json').read_text())
assert hashlib.sha256((ROOT/result['source_ablation']/'result.json').read_bytes()).hexdigest()==result['source_result_sha256']
rng=np.random.default_rng(result['fixture']['seed']);alice=rng.integers(0,2,2765,dtype=np.int64)
bob=alice^(rng.random(2765)<source['config']['qber']).astype(np.int64)
assert hashlib.sha256(alice.astype(np.uint8).tobytes()+bob.astype(np.uint8).tobytes()).hexdigest()==result['fixture']['input_sha256']
uart=(folder/'uart.log').read_text();xsct=(folder/'xsct.log').read_text(errors='replace')
assert 'ZC702_PROGRAM_MMIO_PASS' in xsct and not re.search(r'FATAL|TIMEOUT|DMA_ERROR|MISMATCH',uart)
assert not re.search(r'QKD_FUNC_PA |QKD_STREAM_(?:ADDED|WORD|EMITTED) ',uart),'wrong-key output escaped'
rows=[];last_key=None;last_code=None;used=0
for packet in json.loads((folder/'tx_manifest.json').read_text()):
    data=(folder/packet['file']).read_bytes();assert hashlib.sha256(data).hexdigest()==packet['sha256'] and f'{zlib.crc32(data):08x}'==packet['crc32']
    w=struct.unpack('<'+'I'*(len(data)//4),data);seq=packet['seq'];op=w[0]
    if op==10:last_code=w[1]&3
    if op==14:
        values=re.findall(fr'^QKD_FUNC_KEY seq={seq} word=(\d+) value=([0-9a-fA-F]{{16}})',uart,re.MULTILINE)
        assert [int(i) for i,_ in values]==list(range(48))
        bits=np.unpackbits(np.frombuffer(struct.pack('<48Q',*[int(v,16) for _,v in values]),dtype=np.uint8),bitorder='little')
        code=m.CODE_ORDER[last_code];positions=pu.order(code,m.load_codes(128)[code],128,307);keep=np.ones(3072,dtype=bool);keep[positions]=False
        last_key=bits[keep];assert int((last_key!=alice).sum())==result['fixture']['residual_errors']>0
    if op in [20,60]:
        assert last_key is not None
        seed=w[309:429] if op==20 else w[12:132];at=429 if op==20 else 132
        sb=np.unpackbits(np.frombuffer(struct.pack('<120I',*seed),dtype=np.uint8),bitorder='little')
        def tag(bits):return int(np.frombuffer(np.packbits(pa.pa_hash(np.pad(bits,(0,19)),sb)[:64],bitorder='little').tobytes(),dtype='<u8')[0])
        wanted=w[at]|w[at+1]<<32;assert wanted==tag(alice) and wanted!=tag(last_key)
        pattern=fr'^QKD_FUNC_TAG_REJECT seq={seq} pa_emitted=0' if op==20 else fr'^QKD_STREAM_TAG_REJECT seq={seq} bits=0'
        assert re.search(pattern,uart,re.MULTILINE)
        used+=1;rows.append(dict(op=op,seq=seq,residual_errors=int((last_key!=alice).sum()),genuine_Alice_tag=True,actual_wrong_key_tag_differs=True,output_withheld=True))
    if op==73:assert re.search(fr'^QKD_FUNC_BUDGET_STATE seq={seq} used={used} limit=18446 remaining={18446-used}',uart,re.MULTILINE)
assert len(rows)==2 and {r['op'] for r in rows}=={20,60}
out=ROOT/'reports'/('zc702_wrong_codeword_'+result['started_utc']);out.mkdir(parents=True,exist_ok=True)
with (out/'checks.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
proof=dict(raw_replay_verified=True,actual_DMA_wrong_key_readback=True,genuine_Alice_tags=True,entry_points_verified=[20,60],
    residual_errors=result['fixture']['residual_errors'],budget_checks_charged=used,PA_or_append_after_wrong_key=False,
    source_result_sha256=hashlib.sha256((folder/'result.json').read_bytes()).hexdigest())
(out/'verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
(out/'REPORT.md').write_text('# Codeword sai tự nhiên bị tag Alice chặn trên ZC702\n\n'
    f'Fixture từ ablation trial={result["fixture"]["trial"]}, seed={result["fixture"]["seed"]}; '
    f'decoder hội tụ nhưng còn {result["fixture"]["residual_errors"]} bit khác Alice. '
    'Đã đọc toàn bộ KEY thực qua DMA/UART và tính lại hash độc lập.\n\n'
    'Tag gửi vào là hash đúng của Alice với seed đã truyền, không cố ý lật bit tag. '
    'Cả op20 và op60 từ chối codeword sai, không phát PA/append, tính đủ hai lượt vào ngân sách; reset buffer không hoàn lại lượt.\n\n'
    'Đây là một fixture nguồn BSC công khai, thử hai entry point; không tính là hai mẫu lỗi độc lập hoặc FER campaign mới. '
    'Không thay đổi các nhãn NOT_TESTED tag/PA của các campaign FER khác. '
    'Seed vẫn là fixture kiểm thử, chưa có kênh xác thực/session persistence và không chứng nhận security thực.\n',encoding='utf-8')
print('NATURAL_WRONG_CODEWORD_RAW_REPLAY_PASS',out,flush=True)
