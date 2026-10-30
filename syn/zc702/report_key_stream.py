"""Replay captured commands, source counts and raw output independently of runtime assertions."""
from pathlib import Path
import argparse,collections,csv,hashlib,json,re,struct,sys,zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
import puncture as pu
import ir_model as m
import pa_model as pa
from pa_accum import PAAccumulator
from hankel_exact import hankel_hash
from run_key_stream import Source,bits_words

ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path);args=ap.parse_args()
folder=args.run.resolve();result=json.loads((folder/'result.json').read_text())
assert result['complete'] and result['hardware_capture'] and not result['security_certified']
uart=(folder/'uart.log').read_text();xsct=(folder/'xsct.log').read_text(errors='replace')
assert not re.search(r'FATAL|TIMEOUT|DMA_ERROR|MISMATCH',uart)
assert 'ZC702_PROGRAM_MMIO_PASS' in xsct and 'ZC702_SMOKE_CPU_STARTED' in xsct
frames=json.loads((folder/'tx_manifest.json').read_text());payloads={}
for f in frames:
    data=(folder/f['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==f['sha256'] and f'{zlib.crc32(data):08x}'==f['crc32']
    payloads[f['seq']]=struct.unpack('<'+'I'*(len(data)//4),data)
sources={name:Source(name) for name in result['sources']}
for name,source in sources.items():assert hashlib.sha256(source.path.read_bytes()).hexdigest()==result['sources'][name]['sha256']
codes=m.load_codes(128);key_groups=collections.OrderedDict()
for seq,index,value in re.findall(r'QKD_FUNC_KEY seq=(\d+) word=(\d+) value=([0-9a-fA-F]{16})',uart):
    key_groups.setdefault(int(seq),[]).append((int(index),int(value,16)))
convrows=[r for r in result['records'] if r['outcome'] in ['VERIFIED_ADDED','INJECTED_TAG_REJECT','WRONG_KEY_TAG_REJECT']]
assert len(key_groups)==len(convrows)
rows_for_key=dict(zip(key_groups,convrows));actual_keys={};record_for_commit={};last_code=None;last_keyseq=None
for f in frames:
    words=payloads[f['seq']]
    if f['op']==10:last_code=words[1]&3
    if f['op']==14:
        group=key_groups[f['seq']];assert [i for i,_ in group]==list(range(48))
        bits=np.unpackbits(np.frombuffer(struct.pack('<48Q',*[v for _,v in group]),dtype=np.uint8),bitorder='little')
        positions=pu.order(m.CODE_ORDER[last_code],codes[m.CODE_ORDER[last_code]],128,307)
        keep=np.ones(3072,dtype=bool);keep[positions]=False
        actual=bits[keep];row=rows_for_key[f['seq']]
        alice,bob,nk,nt,mt,xl,xh=sources[row['source']].block(row['source_block'])
        assert row['nk']==nk and row['nt']==nt and row['mt']==mt and row['test_start']==xl and row['test_stop']==xh
        if row['outcome']!='WRONG_KEY_TAG_REJECT':assert np.array_equal(actual,alice)
        actual_keys[f['seq']]=actual;last_keyseq=f['seq']
    if f['op']==60:record_for_commit[f['seq']]=(last_keyseq,rows_for_key[last_keyseq])
def get(pattern):
    found=re.search(pattern,uart)
    assert found,pattern
    return found
ref=PAAccumulator([.6,.2,0],[.75,.125,.125]);keys=[];seed=[];pending=None;output=None;emission=0
block_rows=[];decision_rows=[];emission_rows=[];check_rows=[];last_revealed=0;last_code=0
for f in frames:
    seq=f['seq'];w=payloads[seq];op=w[0]
    if op==10:last_code=w[1]&3;last_revealed=w[4]
    elif op==12:last_revealed+=w[1]
    elif op==61:ref.reset();keys=[];seed=[];pending=None;output=None
    elif op==60:
        keyseq,row=record_for_commit[seq];nk=list(w[2:5]);nt=list(w[5:8]);mt=list(w[8:11])
        assert nk==row['nk'] and nt==row['nt'] and mt==row['mt']
        actual=actual_keys[keyseq];padded=np.pad(actual,(0,(-len(actual))%32))
        seedbits=np.unpackbits(np.frombuffer(struct.pack('<120I',*w[12:132]),dtype=np.uint8),bitorder='little')
        tag=bits_words(pa.pa_hash(padded,seedbits),64)[0];wanted=w[132]|(w[133]<<32)
        if tag!=wanted:
            reply=get(fr'QKD_STREAM_TAG_REJECT seq={seq} bits=(\d+)');assert int(reply.group(1))==ref.n
            check_rows.append({'case':'wrong_tag_not_appended','pass':True,'seq':seq});continue
        leak=m.CODE_MB[m.CODE_ORDER[last_code]]*128-307+last_revealed+64
        added=get(fr'QKD_STREAM_ADDED seq={seq} block=(\d+) bits=(\d+) leak=(\d+)')
        assert int(added.group(1))==w[1] and int(added.group(3))==leak
        ref.add(nk,nt,mt,leak,w[11]);keys.append(actual.copy());assert ref.n==int(added.group(2))
        block_rows.append({'stream_id':w[1],'source':row['source'],'source_block':row['source_block'],
                           'key_bits':2765,'nk':';'.join(map(str,nk)),'nt':';'.join(map(str,nt)),'mt':';'.join(map(str,mt)),
                           'leak_ec_bits':leak,'attempts':len(row['attempts']),'replay_time_seconds':w[11]})
    elif op==62:
        response=get(fr'QKD_STREAM_DECISION seq={seq} action=(\d+) bits=(\d+) ell=(\d+) split=(\d+) emit_bits=(\d+) seed_words=(\d+)')
        action,n,ell,split,emit,ns=map(int,response.groups());expected,refell,_,reason=ref.decide(w[1])
        assert action=={'wait':0,'emit':1,'abort':2}[expected] and n==ref.n and bool(split)==ref._split
        assert ell==(refell//64*64 if expected=='emit' else 0)
        decision_rows.append({'action':expected,'bits':n,'ell':ell,'split':split,'emit_bits':emit,'virtual_seconds':w[1],'reason':reason})
        if expected=='abort':ref.reset();keys=[]
        elif expected=='emit':
            assert emit==ref.emit_n
            pending={'n':n,'ell':ell,'emit':emit,'ns':ns,'split':split};seed=[]
    elif op==63:
        assert pending and w[1]==pending['ns'] and w[2]==len(seed) and w[3]==len(w)-4
        seed.extend(w[4:])
    elif op==64:
        if not pending or len(seed)!=pending['ns']:
            get(fr'QKD_STREAM_REJECT seq={seq} reason=INCOMPLETE_SEED bits=(\d+)')
            check_rows.append({'case':'incomplete_seed_no_output','pass':True,'seq':seq});continue
        joined=np.concatenate(keys);selected=joined[:pending['emit']]
        saved=np.load(folder/f'emit_{emission}_reference.npz')
        seedbits=np.unpackbits(np.frombuffer(struct.pack('<'+'I'*len(seed),*seed),dtype=np.uint8),bitorder='little')
        assert np.array_equal(saved['key'],selected) and np.array_equal(saved['seed'],seedbits) and int(saved['ell'])==pending['ell']
        print('INDEPENDENT_NTT_CHECK',len(selected),pending['ell'],flush=True)
        expected_bits=hankel_hash(np.pad(selected,(0,(-len(selected))%32)),seedbits,pending['ell'])
        expected_words=bits_words(expected_bits,64)
        output=(folder/f'emit_{emission}_output.bin').read_bytes()
        assert output==struct.pack('<'+'Q'*len(expected_words),*expected_words)
        done=get(fr'QKD_STREAM_EMITTED seq={seq} output_bits=(\d+) input_bits=(\d+) tail_bits=(\d+) passes=(\d+)')
        assert list(map(int,done.groups()))==[pending['ell'],pending['emit'],pending['n']-pending['emit'],(pending['ell']+1023)//1024]
        emission_rows.append({'input_bits':pending['emit'],'output_bits':pending['ell'],'split':pending['split'],
                              'tail_bits':pending['n']-pending['emit'],'passes':(pending['ell']+1023)//1024,'all_words_match':True,
                              'output_sha256':hashlib.sha256(output).hexdigest()})
        tail=joined[pending['emit']:];keys=[tail] if len(tail) else [];ref.emitted();pending=None;emission+=1
    elif op==65:
        assert output is not None
        for k in range(w[1],w[1]+w[2]):
            got=get(fr'QKD_STREAM_WORD seq={seq} word={k} value=([0-9a-fA-F]{{16}})')
            assert int(got.group(1),16)==struct.unpack_from('<Q',output,k*8)[0]
    elif op==66:output=None
    elif op==68:
        expected=bits_words(np.concatenate(keys) if keys else np.array([],dtype=np.uint8))
        for k in range(w[1],w[1]+w[2]):assert int(get(fr'QKD_STREAM_BUFFER seq={seq} word={k} value=([0-9a-fA-F]{{8}})').group(1),16)==expected[k]
        check_rows.append({'case':'retained_tail_readback','pass':True,'seq':seq,'words':w[2]})
    elif op==69:
        values=get(fr'QKD_STREAM_WIPE_CHECK seq={seq} key_crc=([0-9a-fA-F]+) work_crc=([0-9a-fA-F]+) seed_crc=([0-9a-fA-F]+) output_crc=([0-9a-fA-F]+)')
        assert not keys and output is None
        assert [int(x,16) for x in values.groups()]==[zlib.crc32(bytes(size)) for size in [2000000,2000000,4000260,2000000]]
        check_rows.append({'case':'full_buffer_zero_crc','pass':True,'seq':seq})
assert emission==len(result['emissions'])
negative={(r['source'],r['source_block']) for r in result['records'] if r['outcome']=='INJECTED_TAG_REJECT'}
reused=[r for r in block_rows if (r['source'],r['source_block']) in negative]
out=ROOT/'reports'/('zc702_key_stream_'+result['started_utc']);out.mkdir(parents=True,exist_ok=True)
def write(name,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
write('blocks.csv',block_rows);write('decisions.csv',decision_rows);write('emissions.csv',emission_rows);write('checks.csv',check_rows)
text=['# Buffer verified key → finite-key → PA trên ZC702','',
      f"Lượt `{result['started_utc']}`, scenario `{result['scenario']}`, COM3, PL 50 MHz. Alice và nguồn decoy mô phỏng.",'',
      f"Đã kiểm tra {len(frames)} request có CRC/hash, {len(block_rows)} block được thêm sau xác minh và {emission} lần EMIT. "
      'NK/NT/MT được đối chiếu với đúng cửa sổ nguồn. PE lấy từ X, không lấy mẫu công khai trong Z key.','',
      '| Input bit | Output ℓ | Số lượt PA PL | Split | Tail bit |', '|---:|---:|---:|---:|---:|']
for r in emission_rows:text.append(f"| {r['input_bits']} | {r['output_bits']} | {r['passes']} | {r['split']} | {r['tail_bits']} |")
text+=['','Mọi bit đầu ra được đối chiếu lại bằng NTT số nguyên, dùng seed từ packet thật và key thực đọc từ DMA. '
       'Không dùng kết quả FFT dấu phẩy động để quyết định PASS. Tag sai và seed thiếu phải giữ đầu ra; '
       'readback tail và CRC toàn bộ buffer xóa được ghi trong checks.csv nếu phép thử có chạy.','',
       'Đây là kiểm thử chức năng theo mô hình finite-key hiện có, chưa phải chứng nhận an toàn QKD. '
       'Cần rà soát adaptive postselection, ngân sách ε toàn phiên, seed/kênh xác thực. '
       'Timestamp điều khiển dùng đồng hồ replay ảo; không phải phép đo thông lượng quang/board. '
       'Seed PA/verification là NumPy PCG64 công khai cho replay, được giữ trong packet; không phải nguồn entropy vật lý đã kiểm chứng. '
       'Các phiên nguồn được giữ riêng theo level; chúng không được gọi là dữ liệu quang đo thật.','',
       f'Ca âm có block được dùng lại trong buffer: {len(reused)}. '
       'Nếu khác 0, transcript bổ sung của ca âm chưa được cộng vào leakage; chỉ dùng lượt đó cho kiểm thử chức năng, '
       'không dùng số ℓ làm tuyên bố khóa bí mật. Runner mới dành riêng block âm, không giữ lại block đó.','',
       f'[UART](../../build/zc702/key_stream_runs/{result["started_utc"]}/uart.log) · '
       f'[Receipt](../../build/zc702/key_stream_runs/{result["started_utc"]}/result.json)','']
(out/'REPORT.md').write_text('\n'.join(text),encoding='utf-8')
proof={'raw_replay_verified':True,'packets':len(frames),'verified_blocks':len(block_rows),'emissions':emission_rows,
       'checks':len(check_rows),'negative_transcript_reused_blocks':len(reused),'security_certified':False,
       'source_hashes':{name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ['result.json','uart.log','tx_manifest.json','firmware_manifest.json']}}
(out/'verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
print('KEY_STREAM_RAW_REPLAY_PASS',out,flush=True)
