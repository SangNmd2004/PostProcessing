"""Export actual multi-pass PA phases only after full key/seed/output replay succeeds."""
from pathlib import Path
import argparse,csv,hashlib,json,re,struct,zlib
from profile_protocol import PHASES
ROOT=Path(__file__).resolve().parents[2]
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path)
args=ap.parse_args();folder=args.run.resolve();result=json.loads((folder/'result.json').read_text())
assert result['complete'] and result['hardware_capture'] and result['profile_snapshots']
out=ROOT/'reports'/('zc702_key_stream_'+result['started_utc'])
functional=json.loads((out/'verified_evidence.json').read_text())
assert functional['raw_replay_verified'] and functional['negative_transcript_reused_blocks']==0
assert functional['source_hashes']['result.json']==hashlib.sha256((folder/'result.json').read_bytes()).hexdigest()
uart=(folder/'uart.log').read_text();frames=json.loads((folder/'tx_manifest.json').read_text());packets={}
for r in frames:
    data=(folder/r['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==r['sha256'] and f'{zlib.crc32(data):08x}'==r['crc32']
    packets[r['seq']]=struct.unpack('<'+'I'*(len(data)//4),data)
timer=result['profile_timer'];hz=timer['timer_hz'];cpu=timer['cpu_hz'];assert abs(timer['cal_cycles']/timer['cal_ticks']-cpu/hz)<.02
meta_packets=[seq for seq,w in packets.items() if w==(75,0xffffffff)]
assert len(meta_packets)==1
assert re.search(fr'^QKD_PROFILE_META seq={meta_packets[0]} count={len(result["profile_snapshots"])} dropped=0 enabled=1 timer_hz={hz} cpu_hz={cpu}',uart,re.MULTILINE)
rows=[];commands=[];emissions=[]
for index,snapshot in enumerate(result['profile_snapshots']):
    seq=snapshot['command_seq'];query=snapshot['query_seq'];op=snapshot['op'];values=packets[seq]
    assert values[0]==op and packets[query]==(75,index)
    head=re.search(fr'^QKD_PROFILE_SNAPSHOT seq={query} index={index} command_seq={seq} op={op} phases={len(snapshot["phases"])} total_ticks=([0-9a-fA-F]{{16}})',uart,re.MULTILINE)
    assert head and int(head.group(1),16)==snapshot['total_ticks']
    assert re.search(fr'^QKD_PROFILE_END seq={query}\b',uart,re.MULTILINE)
    parsed=[dict(id=int(a),count=int(b),valid=int(c),ticks=int(d,16),cycles=int(e,16)) for a,b,c,d,e in re.findall(
        fr'^QKD_PROFILE_PHASE seq={query} id=(\d+) count=(\d+) valid=(\d+) ticks=([0-9a-fA-F]{{16}}) cycles=([0-9a-fA-F]{{16}})',uart,re.MULTILINE)]
    assert parsed==snapshot['phases']
    per={p['id']:p for p in parsed};assert len(per)==len(parsed)
    assert sum(per[k]['ticks'] for k in [0,1,2,3])<=snapshot['total_ticks']
    for p in parsed:
        assert p['valid']<=p['count'] and p['ticks']>0
        if p['valid']==p['count'] and p['ticks']>1000*p['count']:
            assert abs(p['cycles']-p['ticks']*cpu/hz)<max(200*p['count'],.03*p['ticks']*cpu/hz)
        rows.append({'command_seq':seq,'op':op,'phase_id':p['id'],'phase':PHASES[p['id']],
            'spans':p['count'],'valid_PMU_spans':p['valid'],'ticks':p['ticks'],'PS_PMU_cycles_valid_only':p['cycles'],
            'microseconds':p['ticks']*1e6/hz,'overlapping_parent':p['id'] in [2,11,13,14]})
    commands.append({'command_seq':seq,'op':op,'board_snapshot_us':snapshot['total_ticks']*1e6/hz,
                     'RX_ACK_wall_us':per[0]['ticks']*1e6/hz,'command_printf_us':per[2]['ticks']*1e6/hz,
                     'TX_drain_us':per[3]['ticks']*1e6/hz})
    done=re.search(fr'^QKD_STREAM_EMITTED seq={seq} output_bits=(\d+) input_bits=(\d+) tail_bits=(\d+) passes=(\d+)',uart,re.MULTILINE)
    if op==64 and done:
        output_bits,input_bits,tail,passes=map(int,done.groups())
        assert per[14]['count']==passes and all(per[k]['count']==passes for k in [18,19,20])
        assert sum(per[k]['ticks'] for k in [18,19,20])<=per[14]['ticks']
        emissions.append({'input_bits':input_bits,'output_bits':output_bits,'passes':passes,'tail_bits':tail,
            'PA_calls_us':per[14]['ticks']*1e6/hz,'PA_call_mean_us':per[14]['ticks']*1e6/hz/passes,
            'PA_setup_us':per[18]['ticks']*1e6/hz,'PA_mm2s_start_us':per[19]['ticks']*1e6/hz,
            'PA_DMA_output_drain_us':per[20]['ticks']*1e6/hz,'prefix_prepare_us':per[23]['ticks']*1e6/hz,
            'tail_finalize_wipe_us':per[24]['ticks']*1e6/hz,'emit_command_snapshot_us':snapshot['total_ticks']*1e6/hz,
            'scope':'PS-observed PA multi-pass calls include DMA/cache; excludes seed UART, IR and source accumulation'})
assert len(emissions)==len(result['emissions'])
def write(name,values):
    with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(values[0]));w.writeheader();w.writerows(values)
write('profile_tung_pha.csv',rows);write('profile_tung_lenh.csv',commands);write('profile_PA_emit.csv',emissions)
proof={'raw_profile_replay_verified':True,'functional_source_proof_verified':True,'snapshots':len(commands),
       'phase_rows':len(rows),'emissions':emissions,'invalid_PMU_spans':sum(r['spans']-r['valid_PMU_spans'] for r in rows),
       'source_result_sha256':hashlib.sha256((folder/'result.json').read_bytes()).hexdigest()}
(out/'profile_verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
text=['# Đo pha finite-key và PA nhiều pass trên buffer thật','',
      'Đã đối chiếu toàn bộ KEY/decoy/seed/output bằng report_key_stream trước khi kiểm tra counter. '
      'Nguồn Alice/decoy và seed vẫn mô phỏng công khai; clock điều khiển EMIT là replay ảo.','',
      '| Input bit | Output bit | Passes | PA calls ms | Mỗi pass µs | Chuẩn bị prefix µs | Finalize/wipe µs |',
      '|---:|---:|---:|---:|---:|---:|---:|']
for r in emissions:text.append(f"| {r['input_bits']} | {r['output_bits']} | {r['passes']} | {r['PA_calls_us']/1000:.3f} | {r['PA_call_mean_us']:.3f} | {r['prefix_prepare_us']:.3f} | {r['tail_finalize_wipe_us']:.3f} |")
text+=['','Counter là thời gian board thật, tách khỏi replay clock. Profiler bật sau ingest và đọc sau khi EMIT/output xong. '
       'Các phase PA reset/cache/DMA là con của PA call; không cộng trùng. Span nhận seed UART và output readback có trong profile_tung_lenh.csv. '
       'PA call chưa phải pure RTL latency; không quy đổi thành tốc độ khóa bí mật end-to-end. PC NTT reference tính giữa các command, ngoài board snapshot.','',
       f'PMU spans invalid do wrap: {proof["invalid_PMU_spans"]}. Các giá trị cycles chỉ cộng span valid; global timer 64 bit vẫn là nguồn wall time. '
       'Chưa có thí nghiệm nhiều mẫu/CI cho PA lớn; đây là một phiên functional có raw evidence đầy đủ.','']
(out/'PROFILE_REPORT.md').write_text('\n'.join(text),encoding='utf-8')
print('STREAM_PA_PROFILE_RAW_REPLAY_PASS',out,flush=True)
