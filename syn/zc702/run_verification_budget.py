"""Physical regression of the shared boot-lifetime tag-check budget. Public fixtures only."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,struct,sys,zlib
import numpy as np
from uart_session import ROOT,UARTSession
sys.path.insert(0,str(ROOT/'model'))
import ir_model as ir
import puncture as pu
import pa_model as pa

stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
folder=ROOT/'build/zc702/verification_budget_runs'/stamp;folder.mkdir(parents=True)
result={'complete':False,'hardware_capture':True,'started_utc':stamp,'scope':'shared boot-lifetime cap; public simulated fixtures; no security certification','checks':[]}
campaign_dir=ROOT/'build/zc702/uart_csv_nms_gs'
campaign=json.loads((campaign_dir/'campaign.json').read_text())
record=next(r for r in campaign['records'] if r['model_outcome']=='SUCCESS' and r['attempts']==1)
payload=(campaign_dir/record['file']).read_bytes();assert hashlib.sha256(payload).hexdigest()==record['sha256']
v=list(struct.unpack('<'+'I'*(len(payload)//4),payload))
cfg,cfg2,pre,attempts,ns,err,nrev=v[:7];assert attempts==1 and pre==nrev==0
ch=v[9:9+192];syn=v[9+192:9+192+ns];keywords=v[9+192+ns:]
key=np.unpackbits(np.frombuffer(struct.pack('<96I',*keywords),dtype=np.uint8),bitorder='little')
code=cfg&3;name=ir.CODE_ORDER[code]
positions=list(map(int,pu.order(name,ir.load_codes(128)[name],128,307)))
mask=np.ones(3072,dtype=bool);mask[positions]=False
x=np.pad(key[mask],(0,19));assert len(x)==2784
rng=np.random.default_rng(2026102701)
seeds=[list(map(int,rng.integers(0,2**32,120,dtype=np.uint32))) for _ in range(2)]
def hash_words(seed):
    sb=np.unpackbits(np.frombuffer(struct.pack('<120I',*seed),dtype=np.uint8),bitorder='little')
    return list(map(int,np.frombuffer(np.packbits(pa.pa_hash(x,sb),bitorder='little').tobytes(),dtype='<u8')))
tag=hash_words(seeds[0])[0];expected=hash_words(seeds[1])
def perblock(bad=False):
    wanted=tag^int(bad)
    expected32=[w for value in expected for w in [value&0xffffffff,value>>32]]
    out=[20,code,*positions,*seeds[0],wanted&0xffffffff,wanted>>32,*seeds[1],*expected32]
    assert len(out)==583;return out
def stream(bad=False,block_id=0):
    wanted=tag^int(bad)
    return [60,block_id,2765,0,0,100,20,0,1,0,0,0,*seeds[0],wanted&0xffffffff,wanted>>32]
def save():(folder/'result.json').write_text(json.dumps(result,indent=2)+'\n')
try:
    with UARTSession(folder) as session:
        result['firmware_manifest']=session.manifest
        result['fixture']={'file':str((campaign_dir/record['file']).relative_to(ROOT)),'sha256':record['sha256'],'record':record}
        command=session.command
        def check(label,values,pattern):
            seq,reply=command(values,pattern)
            result['checks'].append({'case':label,'seq':seq,'op':values[0],'reply':reply.group(0),'pass':True})
            save();return reply
        def budget(used,limit):
            return check('budget_state', [73],fr'QKD_FUNC_BUDGET_STATE seq={{seq}} used={used} limit={limit} remaining={limit-used}')
        def load(check_active=False):
            command([10,cfg,cfg2,ns,0,*ch,*syn],r'QKD_FUNC_LOADED seq={seq}')
            if check_active:
                check('active_block_cap_change_rejected',[72,8],r'QKD_FUNC_BUDGET_REJECT seq={seq} used=0 limit=8')
            _,a=command([11],r'QKD_FUNC_ATTEMPT seq={seq} status=([0-9a-fA-F]+) iters=([0-9a-fA-F]+) errcnt=(\d+) cycles=(\d+) ticks=(\d+)')
            assert int(a.group(1),16)&3==1 and int(a.group(3))==err
            seq,_=command([14]);got=[]
            for k in range(48):got.append(int(session.expect(fr'QKD_FUNC_KEY seq={seq} word={k} value=([0-9a-fA-F]{{16}})').group(1),16))
            assert got==[keywords[i]|keywords[i+1]<<32 for i in range(0,96,2)]
        def reset_buffer():command([61],r'QKD_STREAM_RESET seq={seq}')
        def state(bits,next_id,rejected):
            check('stream_state',[67],fr'QKD_STREAM_STATE seq={{seq}} bits={bits} next_id={next_id} pending=0 out_bits=0 rejected={rejected} retired=0 aborted=0')
        budget(0,18446)
        check('lower_initial_cap',[72,8],r'QKD_FUNC_BUDGET_SET seq={seq} used=0 limit=8')
        check('cannot_raise_cap',[72,9],r'QKD_FUNC_BUDGET_REJECT seq={seq} used=0 limit=8')
        reset_buffer();load(check_active=True)
        check('invalid_block_no_charge',stream(block_id=9),r'QKD_STREAM_REJECT seq={seq} reason=BLOCK_ID bits=0');budget(0,8)
        invalid=stream();invalid[2]=2766
        check('invalid_key_counts_no_charge',invalid,r'QKD_STREAM_REJECT seq={seq} reason=CAPACITY_COUNTS bits=0');budget(0,8)
        invalid=stream();invalid[8]=101
        check('invalid_test_counts_no_charge',invalid,r'QKD_STREAM_REJECT seq={seq} reason=TEST_COUNTS bits=0');budget(0,8)
        check('stream_bad_tag_charged',stream(True),r'QKD_STREAM_TAG_REJECT seq={seq} bits=0');budget(1,8);state(0,0,1)
        check('rejected_key_not_reusable',stream(),r'QKD_STREAM_REJECT seq={seq} reason=NO_VERIFIED_INPUT bits=0');budget(1,8)
        load();check('perblock_bad_tag_charged',perblock(True),r'QKD_FUNC_TAG_REJECT seq={seq} pa_emitted=0');budget(2,8)
        check('lower_after_use',[72,6],r'QKD_FUNC_BUDGET_SET seq={seq} used=2 limit=6')
        check('cannot_lower_below_used',[72,1],r'QKD_FUNC_BUDGET_REJECT seq={seq} used=2 limit=6')
        command([0],r'QKD_FUNC_RESET seq={seq}');command([30],r'QKD_FUNC_ACC_RESET seq={seq}');reset_buffer();budget(2,6)
        load();check('stream_success_charged',stream(),r'QKD_STREAM_ADDED seq={seq} block=0 bits=2765 leak=\d+');budget(3,6);state(2765,1,0)
        check('incomplete_seed_no_charge',[64],r'QKD_STREAM_REJECT seq={seq} reason=INCOMPLETE_SEED bits=2765');budget(3,6)
        load();seq,_=command(perblock())
        for k,value in enumerate(expected):
            reply=session.expect(fr'QKD_FUNC_PA seq={seq} word={k} value=([0-9a-fA-F]{{16}})');assert int(reply.group(1),16)==value
        reply=session.expect(fr'QKD_FUNC_PIPE_PASS seq={seq} input_bits=2765 output_bits=1024')
        result['checks'].append({'case':'perblock_success_all_pa_words','seq':seq,'op':20,'reply':reply.group(0),'pass':True});budget(4,6)
        reset_buffer();budget(4,6)
        load();check('second_stream_reject_charged',stream(True),r'QKD_STREAM_TAG_REJECT seq={seq} bits=0');budget(5,6)
        load();check('last_perblock_reject_charged',perblock(True),r'QKD_FUNC_TAG_REJECT seq={seq} pa_emitted=0');budget(6,6)
        load();check('stream_exhausted_blocked',stream(),r'QKD_FUNC_VERIFY_LIMIT seq={seq} used=6 limit=6');budget(6,6);state(0,0,1)
        check('exhausted_stream_input_consumed',stream(),r'QKD_STREAM_REJECT seq={seq} reason=NO_VERIFIED_INPUT bits=0')
        load();check('perblock_exhausted_blocked',perblock(),r'QKD_FUNC_VERIFY_LIMIT seq={seq} used=6 limit=6');budget(6,6)
        check('exhausted_perblock_input_consumed',stream(),r'QKD_STREAM_REJECT seq={seq} reason=NO_VERIFIED_INPUT bits=0')
        reset_buffer();command([0],r'QKD_FUNC_RESET seq={seq}');command([30],r'QKD_FUNC_ACC_RESET seq={seq}');budget(6,6)
        check('exhausted_cap_cannot_raise',[72,18446],r'QKD_FUNC_BUDGET_REJECT seq={seq} used=6 limit=6')
        _,wipe=command([69],r'QKD_STREAM_WIPE_CHECK seq={seq} key_crc=([0-9a-fA-F]+) work_crc=([0-9a-fA-F]+) seed_crc=([0-9a-fA-F]+) output_crc=([0-9a-fA-F]+)')
        assert [int(s,16) for s in wipe.groups()]==[zlib.crc32(bytes(n)) for n in [2000000,2000000,4000260,2000000]]
        result['checks'].append({'case':'stream_buffers_zero','pass':True})
        result.update(complete=True,physical_tag_checks=6,cap=6,successful_checks=2,rejected_tags=4,blocked_on_exhaustion=2)
except BaseException as exc:
    result['error']=repr(exc);raise
finally:
    save();print('VERIFICATION_BUDGET_EVIDENCE',folder,flush=True)
print('VERIFICATION_BUDGET_BOARD_PASS',len(result['checks']),flush=True)
