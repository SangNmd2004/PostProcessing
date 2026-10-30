"""Verify raw profiler replies/packets and export labelled overlapping phase spans."""
from pathlib import Path
import argparse,collections,csv,hashlib,json,re,statistics,struct,sys,zlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
import ir_model as ir
import pa_model as pa
import puncture as pu

PHASES=['uart_rx_ack_enqueue','crc32','command_including_reply_printf','reply_fifo_drain',
 'ir_setup_reset','ir_copy_cache_and_dma_start','ir_input_dma_and_hold_drain','ir_pre_reveal_write',
 'ir_run_to_status_poll','ir_key_rx_and_cache','reveal_mmio_write','fail_detect_to_reveal_command',
 'strip_D_positions','verification_PL_call','PA_PL_call','verification_reset_and_rx_setup',
 'verification_mm2s_cache_and_start','verification_dma_and_output_drain','PA_reset_and_rx_setup',
 'PA_mm2s_cache_and_start','PA_dma_and_output_drain','stream_append_and_counts','finite_key_decision',
 'emit_prefix_prepare','emit_tail_and_wipe','seed_copy','stream_reset_and_wipe','reserved27','reserved28']
COMPUTE=[4,5,6,7,8,9,10,12,13,14,21,22,23,24,25,26]
PARENTS={2,11,13,14};CHILDREN={15:13,16:13,17:13,18:14,19:14,20:14}
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path)
args=ap.parse_args();folder=args.run.resolve();result=json.loads((folder/'result.json').read_text())
assert result['complete'] and result['hardware_capture']
uart=(folder/'uart.log').read_text();xsct=(folder/'xsct.log').read_text(errors='replace')
assert 'ZC702_PROGRAM_MMIO_PASS' in xsct and 'ZC702_SMOKE_CPU_STARTED' in xsct
assert not re.search(r'FATAL|TIMEOUT|DMA_ERROR|MISMATCH',uart)
frames=json.loads((folder/'tx_manifest.json').read_text());packets={}
for row in frames:
    data=(folder/row['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==row['sha256'] and f'{zlib.crc32(data):08x}'==row['crc32']
    packets[row['seq']]=struct.unpack('<'+'I'*(len(data)//4),data)
    assert packets[row['seq']][0]==row['op']
assert len(packets)==len(frames)
host=json.loads((folder/'host_timings.json').read_text());host_by_seq={r['seq']:r for r in host}
assert len(host_by_seq)==len(host)==len(frames)
for row in host:
    assert row['start_ns']<=row['last_ack_ns']<=row['response_complete_ns']
    assert row['op']==packets[row['seq']][0]
phase_rows=[];block_rows=[];command_rows=[];seen=set();all_snapshots=0
codes=ir.load_codes(128)
def dump(path,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def lines(seq,prefix):return re.findall(fr'^{prefix} seq={seq}\b[^\r\n]*',uart,re.MULTILINE)
for block_id,record in enumerate(result['records']):
    fixture=record['fixture'];path=ROOT/'build/zc702/uart_csv_nms_gs'/fixture['file'];data=path.read_bytes()
    assert hashlib.sha256(data).hexdigest()==fixture['sha256']
    golden=struct.unpack('<'+'I'*(len(data)//4),data);cfg,cfg2,pre,nattempt,ns,err,nrev=golden[:7]
    key_at=7+2*nattempt+192+ns+nrev
    key=[golden[k]|golden[k+1]<<32 for k in range(key_at,len(golden),2)]
    count=record['timer']['timer_hz'];cpu=record['timer']['cpu_hz'];scale=1e6/count
    assert count==333333343 and cpu==666666687
    assert abs(record['timer']['cal_cycles']/record['timer']['cal_ticks']-cpu/count)<.02
    first=record['command_seqs'][0];enable_seq=first-1
    meta_seq=record['command_seqs'][-1]+1
    assert packets[meta_seq]==(75,0xffffffff)
    assert re.search(fr'^QKD_PROFILE_META seq={meta_seq} count={len(record["snapshots"])} dropped=0 enabled=1 timer_hz={count} cpu_hz={cpu}',uart,re.MULTILINE)
    assert packets[enable_seq]==(74,1)
    config=lines(enable_seq,'QKD_PROFILE_CONFIG');assert len(config)==1
    for field in ['timer_hz','cpu_hz','cal_ticks','cal_cycles','read_ticks']:
        assert re.search(fr'\b{field}={record["timer"][field]}\b',config[0])
    positions=list(map(int,pu.order(fixture['code'],codes[fixture['code']],128,307)))
    bits=np.unpackbits(np.frombuffer(struct.pack('<48Q',*key),dtype=np.uint8),bitorder='little')
    mask=np.ones(3072,dtype=bool);mask[positions]=False;x=np.pad(bits[mask],(0,19))
    phases=collections.Counter();cycles=collections.Counter();total=0;rpc_ns=0;upload_ns=0
    attempt_index=0;previous_cycles=0;pl_cycles=0
    assert [s['command_seq'] for s in record['snapshots']]==record['command_seqs']
    for index,snapshot in enumerate(record['snapshots']):
        command_seq=snapshot['command_seq'];assert command_seq not in seen;seen.add(command_seq)
        values=packets[command_seq];assert values[0]==snapshot['op']
        heads=re.findall(fr'^QKD_PROFILE_SNAPSHOT seq=(\d+) index={index} command_seq={command_seq} op={values[0]} phases=(\d+) total_ticks=([0-9a-fA-F]{{16}})',uart,re.MULTILINE)
        assert len(heads)==1
        query_seq,nphase,ticks=heads[0];query_seq=int(query_seq)
        assert packets[query_seq]==(75,index) and int(ticks,16)==snapshot['total_ticks']
        raw_phases=re.findall(fr'^QKD_PROFILE_PHASE seq={query_seq} id=(\d+) count=(\d+) valid=(\d+) ticks=([0-9a-fA-F]{{16}}) cycles=([0-9a-fA-F]{{16}})',uart,re.MULTILINE)
        parsed=[dict(id=int(a),count=int(b),valid=int(c),ticks=int(d,16),cycles=int(e,16)) for a,b,c,d,e in raw_phases]
        assert parsed==snapshot['phases'] and len(parsed)==int(nphase)
        assert len(lines(query_seq,'QKD_PROFILE_END'))==1
        per={p['id']:p for p in parsed};assert len(per)==len(parsed)
        assert all(k in per for k in [0,1,2,3])
        assert sum(per[k]['ticks'] for k in [0,1,2,3])<=snapshot['total_ticks']
        for p in parsed:
            assert p['count']==p['valid'] and p['ticks']>0
            if p['ticks']>1000*p['count']:
                assert abs(p['cycles']-p['ticks']*cpu/count)<max(200*p['count'],.03*p['ticks']*cpu/count)
            phases[p['id']]+=p['ticks'];cycles[p['id']]+=p['cycles']
            phase_rows.append({'block_id':block_id,'code':fixture['code'],'delay_us':record['delay_us'],'repeat':record['repeat'],
                'command_seq':command_seq,'op':values[0],'phase_id':p['id'],'phase':PHASES[p['id']],
                'spans':p['count'],'pmu_valid_spans':p['valid'],'global_ticks':p['ticks'],'PS_PMU_cycles':p['cycles'],
                'microseconds':p['ticks']*scale,'is_overlapping_parent':p['id'] in PARENTS,
                'child_of_phase_id':CHILDREN.get(p['id'],''),
                'note':'cross-command interval includes UART and host' if p['id']==11 else 'PMU cycles are PS CPU cycles, not PL decoder cycles'})
        for parent,kids in [(13,[15,16,17]),(14,[18,19,20])]:
            if parent in per:assert sum(per[k]['ticks'] for k in kids)<=per[parent]['ticks']
        if values[0]==11:
            raw=lines(command_seq,'QKD_FUNC_ATTEMPT');assert len(raw)==1
            m=re.search(r'status=([0-9a-fA-F]+) iters=([0-9a-fA-F]+) errcnt=(\d+) cycles=(\d+) ticks=(\d+)',raw[0]);assert m
            status,iters=int(m.group(1),16),int(m.group(2),16);expected=golden[7+attempt_index]
            wanted=(1 if expected>>31 else 2)|((expected>>28)&3)<<4|(expected&0x0fff0000)
            assert status&0x0fff0033==wanted and iters&0xfff==expected&0xfff and iters>>16&255==attempt_index+1
            raw_cycles=int(m.group(4));assert raw_cycles>=previous_cycles
            delta=raw_cycles-previous_cycles;previous_cycles=raw_cycles;pl_cycles+=delta;attempt_index+=1
            assert per[8]['ticks']*scale+2>=delta/50
            if expected>>31:assert int(m.group(3))==err
        if values[0]==14:
            got=[int(v,16) for v in re.findall(fr'^QKD_FUNC_KEY seq={command_seq} word=\d+ value=([0-9a-fA-F]{{16}})',uart,re.MULTILINE)]
            assert got==key
        if values[0]==20:
            assert list(values[2:309])==positions
            outputs=[]
            for seed in [values[309:429],values[431:551]]:
                sb=np.unpackbits(np.frombuffer(struct.pack('<120I',*seed),dtype=np.uint8),bitorder='little')
                outputs.append(list(map(int,np.frombuffer(np.packbits(pa.pa_hash(x,sb),bitorder='little').tobytes(),dtype='<u8'))))
            assert values[429]|values[430]<<32==outputs[0][0]
            actual=[int(v,16) for v in re.findall(fr'^QKD_FUNC_PA seq={command_seq} word=\d+ value=([0-9a-fA-F]{{16}})',uart,re.MULTILINE)]
            assert actual==outputs[1] and len(lines(command_seq,'QKD_FUNC_PIPE_PASS'))==1
            assert per[13]['count']==per[14]['count']==1
        h=host_by_seq[command_seq];duration=h['response_complete_ns']-h['start_ns'];upload=h['last_ack_ns']-h['start_ns']
        rpc_ns+=duration;upload_ns+=upload;total+=snapshot['total_ticks'];all_snapshots+=1
        command_rows.append({'block_id':block_id,'code':fixture['code'],'delay_us':record['delay_us'],'repeat':record['repeat'],
            'seq':command_seq,'op':values[0],'payload_bytes':h['payload_bytes'],'host_upload_ack_us':upload/1000,
            'host_RPC_us':duration/1000,'board_snapshot_us':snapshot['total_ticks']*scale,
            'board_outer_unattributed_us':(snapshot['total_ticks']-sum(per[k]['ticks'] for k in [0,1,2,3]))*scale})
    assert attempt_index==nattempt and record['host_transaction_ns']>=rpc_ns
    assert sum(p['count'] for s in record['snapshots'] for p in s['phases'] if p['id']==11)==nattempt-1
    injected=sum(p['host_sleep_ns'] for p in record['injections']);assert len(record['injections'])==nattempt-1
    block_rows.append({'block_id':block_id,'code':fixture['code'],'fixture_seq':fixture['seq'],'delay_us':record['delay_us'],
       'repeat':record['repeat'],'attempts':nattempt,'PL_decode_cycles':pl_cycles,'PL_decode_active_us_at50MHz':pl_cycles/50,
       'PS_ir_poll_us':phases[8]*scale,'PS_load_us':sum(phases[k] for k in [4,5,6,7])*scale,
       'PS_key_rx_us':phases[9]*scale,'PS_reveal_write_us':phases[10]*scale,'strip_D_us':phases[12]*scale,
       'verification_call_us':phases[13]*scale,'PA1024_call_us':phases[14]*scale,
       'disjoint_compute_spans_us':sum(phases[k] for k in COMPUTE)*scale,
       'receive_ack_span_us':phases[0]*scale,'CRC_us':phases[1]*scale,'command_with_printf_us':phases[2]*scale,
       'final_TX_drain_us':phases[3]*scale,'fail_to_reveal_overlap_us':phases[11]*scale,
       'host_injected_sleep_us':injected/1000,'host_upload_ack_us':upload_ns/1000,'host_RPC_sum_us':rpc_ns/1000,
       'host_transaction_us':record['host_transaction_ns']/1000,'board_snapshot_sum_us':total*scale,
       'counter_read_pair_us':record['timer']['read_ticks']*scale,'scope':'repeated public fixtures; includes debug KEY/PA readback; not production throughput'})
out=ROOT/'reports'/('zc702_phase_profile_'+result['started_utc']);out.mkdir(parents=True,exist_ok=True)
dump(out/'tung_pha.csv',phase_rows);dump(out/'tung_lenh.csv',command_rows);dump(out/'tung_block.csv',block_rows)
summary=[]
for code in ir.CODE_ORDER:
    for delay in sorted({r['delay_us'] for r in block_rows if r['code']==code}):
        selected=[r for r in block_rows if r['code']==code and r['delay_us']==delay]
        row={'code':code,'delay_us':delay,'repeats':len(selected),'attempts':selected[0]['attempts']}
        for field in ['PS_load_us','PS_ir_poll_us','PL_decode_active_us_at50MHz','verification_call_us','PA1024_call_us',
                      'disjoint_compute_spans_us','host_transaction_us','receive_ack_span_us','fail_to_reveal_overlap_us']:
            values=[r[field] for r in selected];row['median_'+field]=statistics.median(values)
            row['min_'+field]=min(values);row['max_'+field]=max(values)
        summary.append(row)
dump(out/'tong_hop.csv',summary)
proof={'raw_replay_verified':True,'repeated_blocks':len(block_rows),'command_snapshots':all_snapshots,'phase_rows':len(phase_rows),
       'packets_verified':len(frames),'all_KEY_and_PA_words_match':True,'PMU_vs_global_timer_consistency':True,
       'scope':'K1 repeated public UART workload; PMU is PS CPU cycles; PL counter separate; not FER or secret-key throughput',
       'source_hashes':{name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in
                       ['result.json','uart.log','tx_manifest.json','host_timings.json']}}
(out/'verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
lines=['# Phân rã thời gian PS/PL/UART trên ZC702','',
 f'Đã đối chiếu raw TX/RX cho {len(block_rows)} block lặp lại, {all_snapshots} snapshot lệnh và {len(phase_rows)} dòng phase. '
 'Toàn bộ KEY và PA1024 khớp golden/toán tham chiếu. Đây là workload chức năng K=1 với fixture công khai, không phải mẫu FER độc lập. '
 'Mỗi code dùng một fixture chọn trước khác nhau; chênh lệch giữa code không phải ablation rate trên cùng input.','',
 'PL 50 MHz. Global timer 333.333.343 Hz, CPU/PMU 666.666.687 Hz; divider PMU đã tắt và tỷ lệ hai counter được kiểm tra. '
 'Chu kỳ PMU là chu kỳ PS CPU; `PL_decode_cycles` lấy riêng từ register PL và hiệu giữa các attempt. '
 'Span dài vượt khả năng xác định wrap CCNT 32 bit sẽ bị đánh dấu invalid; các span của run này đều valid.','',
 '| Code | Delay host µs | Attempts | Load PS µs | IR poll µs | Verify µs | PA1024 µs | Host transaction ms |',
 '|---|---:|---:|---:|---:|---:|---:|---:|']
for r in summary:
    lines.append(f"| {r['code']} | {r['delay_us']} | {r['attempts']} | {r['median_PS_load_us']:.3f} | {r['median_PS_ir_poll_us']:.3f} | {r['median_verification_call_us']:.3f} | {r['median_PA1024_call_us']:.3f} | {r['median_host_transaction_us']/1000:.3f} |")
lines+=['','Các file: `tung_pha.csv` (từng phase), `tung_lenh.csv` (RPC/board snapshot), `tung_block.csv`, `tong_hop.csv`. '
        'Min/max là độ trải của số lần lặp, không phải khoảng tin cậy FER.','',
        '**Đọc đúng overlap:** phase 2 bao trùm xử lý lệnh và printf; phase 13/14 bao trùm các phase DMA/cache con. '
        'Phase 11 bắt đầu khi PS thấy FAIL tới đầu lệnh REVEAL, bao gồm reply UART, chờ host và truyền ngược; nó chồng lên nhiều frame. '
        'Không cộng các parent với children hoặc cộng phase 11 vào tổng snapshot. `disjoint_compute_spans_us` chỉ cộng các span compute rời nhau đã instrument, '
        'không phải toàn bộ CPU overhead hay throughput end-to-end.','',
        'UART receive/ACK là wall span CPU, bao gồm ACK enqueue và host/USB waits. TX drain đo phần FIFO còn lại sau hàm lệnh; '
        'phần printf trong lệnh đã có truyền đồng thời. Host RPC đo bằng perf_counter_ns từ trước gửi header đến nhận đủ reply; '
        'không gồm ghi packet file trước lúc bắt đầu, nhưng host transaction gồm khoảng giữa các lệnh và sleep. '
        'Host sleep trước reveal không phải RTT mạng; dùng thời gian sleep thực tế đã lưu, không thay bằng giá trị yêu cầu. '
        'Cột delay là cấu hình mỗi lần reveal; ca một attempt (r56) không có reveal nên sleep thực tế bằng 0 ở cả ba cấu hình delay.','',
        'Workload có đọc lại toàn bộ KEY và gửi expected PA để kiểm chứng, nên lượng UART lớn hơn giao thức sản phẩm. '
        'Không gọi nghịch đảo wall time này là tốc độ khóa bí mật. Có overhead đọc counter chưa trừ; chi phí read-pair lưu tại từng block. '
        'Verification/PA call bao gồm reset DMA, cache và chờ phần cứng; chưa tách pure PL PA bằng counter RTL riêng.','',
        'Chưa đo policy arrival/backlog crossover, lịch đa context bằng profiler này hoặc IRQ DMA thuần. '
        'Chưa đo PA tích lũy lớn trong run này; chỉ per-block 2.784 bit padded → 1.024 bit PA và tag64.','',
        f'[Raw run](../../build/zc702/phase_profile_runs/{result["started_utc"]}/result.json).','']
if (out/'compute_phase_breakdown.png').exists():
    lines+=['','[Compute spans](compute_phase_breakdown.png) | [SVG](compute_phase_breakdown.svg) | '
            '[UART validation vs compute](UART_validation_vs_compute.png) | [SVG](UART_validation_vs_compute.svg).','']
(out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
print('PHASE_PROFILE_RAW_REPLAY_PASS',out,'blocks',len(block_rows),'snapshots',all_snapshots,flush=True)
