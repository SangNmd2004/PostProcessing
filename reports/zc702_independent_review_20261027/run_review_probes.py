"""Host-only review probes. Writes exclusively into this review directory."""
from pathlib import Path
import csv,hashlib,importlib.util,json,re,subprocess,sys
import numpy as np
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent

def load(name,file):
    s=importlib.util.spec_from_file_location(name,ROOT/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
    compiler='C:/msys64/mingw64/bin/gcc.exe'
    command=[compiler,'-std=c11','-O2','-Wall','-Wextra','-I'+str(ROOT/'firmware/zc702_uart'),str(OUT/'reproduce_c_issues.c')]
    command += [str(ROOT/'firmware/zc702_uart'/file) for file in ['auth_channel.c','event_scheduler.c','session_persistence.c']]
    command += ['-o',str(OUT/'reproduce_c_issues.exe')]
    build=subprocess.run(command,capture_output=True,text=True)
    (OUT/'c_build.log').write_text(build.stdout+build.stderr)
    assert build.returncode==0
    probe=subprocess.run([str(OUT/'reproduce_c_issues.exe')],capture_output=True,text=True,check=True)
    (OUT/'c_reproductions.log').write_text(probe.stdout)
    auth=load('auth_probe','syn/zc702/test_auth_channel.py')
    mask=(1<<64)-1;psk=0x0123456789abcdef;seq=1
    tag=auth.compute_mac(0x9e3779b97f4a7c15,psk,b'',seq,0)
    assert tag==int(re.search(r'empty_type0_tag=([0-9a-f]+)',probe.stdout).group(1),16)
    def undo_shift(y,s):
        x=y
        for _ in range(6):x=y^(x>>s)
        return x&mask
    z=undo_shift(tag,31)*pow(0x94d049bb133111eb,-1,1<<64)&mask
    z=undo_shift(z,27)*pow(0xbf58476d1ce4e5b9,-1,1<<64)&mask
    recovered=undo_shift(z,30)^(seq<<32)
    assert recovered==psk
    paced=load('paced_probe','syn/zc702/run_paced_arrival_benchmark.py')
    simulated=paced.PacedArrivalSimulator(1,'EFFICIENCY',677.8,yield_per_block=1382.5).run(500)
    sys.path.insert(0,str(ROOT/'model'))
    import ir_model as ir
    import pa_ntt_model as ntt
    matrices=load('rate_probe','model/ldpc_rate_095_matrix.py')
    m=matrices.generate_rate_095_base_matrix();groups={}
    for c in range(40):
        if min(m[0][c],m[1][c])>=0:groups.setdefault((m[0][c]-m[1][c])%128,[]).append(c)
    four_cycles=[cols for cols in groups.values() if len(cols)>1]
    enc=load('encoder_probe','model/test_syndrome_encoder.py')
    rng=np.random.default_rng(20261027);bits=rng.integers(0,2,3072,dtype=np.int64)
    codes=ir.load_codes(128);mismatch={}
    for code in ir.CODE_ORDER:
        actual=ir.syndrome(codes[code],bits.reshape(1,24,128),128).reshape(-1)
        toy=np.asarray(enc.simulate_hardware_encoder(bits.tolist(),code))
        mismatch[code]=int(np.sum(toy!=actual))
    firmware=json.loads((ROOT/'build/zc702/uart_firmware/manifest.json').read_text())
    bad=[file for file,sha in firmware['files'].items() if hashlib.sha256((ROOT/file).read_bytes()).hexdigest()!=sha]
    assert not bad
    old=ROOT/'data/research/review_work_items_20261027T035757Z.csv'
    with old.open(encoding='utf-8-sig',newline='') as f:previous={r['id']:r for r in csv.DictReader(f)}
    with (ROOT/'reports/zc702_work_items.csv').open(encoding='utf-8-sig',newline='') as f:current=list(csv.DictReader(f))
    promoted=[r['id'] for r in current if r['status']=='PASS_FUNCTIONAL_BOARD' and previous[r['id']]['status']!='PASS_FUNCTIONAL_BOARD']
    receipt=dict(scope='Host-only code review probes; no FPGA programmed, no canonical report/source modified',
        auth_empty_type0_psk_recovered_from_one_tag=(recovered==psk),
        c_probes=probe.stdout.splitlines(),paced_simulation_at_500=simulated,static_report_value_eff_mbps=.691,
        ntt_length_divides_q_minus_one={str(n):(ntt.PRIME_Q-1)%n==0 for n in [1<<20,1<<21,1<<24,1<<27]},
        rate095_four_cycle_column_groups=four_cycles,
        syndrome_encoder_mismatched_bits_vs_real_codes=mismatch,
        current_firmware_manifest_files_verified=len(firmware['files']),
        newly_promoted_to_board_pass=promoted,
        baseline_bit_sha256=hashlib.sha256((ROOT/'build/zc702/qkd_zc702.bit').read_bytes()).hexdigest())
    (OUT/'PROBE_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
