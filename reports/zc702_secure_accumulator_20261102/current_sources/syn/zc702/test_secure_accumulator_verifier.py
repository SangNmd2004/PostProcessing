"""Change a PA word and re-MAC the reply: semantic replay must still reject it."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
from qas2_bootstrap import Bootstrap
from qas2_pc import Session,SessionError
ROOT=Path(__file__).resolve().parents[2]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);copy=out/'mutated_run';copy.mkdir()
    for name in ['result.json','tx.jsonl','uart.log','xsct.log','baseline_restore/uart.log','baseline_restore/xsct.log']:
        p=copy/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((args.run/name).read_bytes())
    tx=[json.loads(l) for l in (copy/'tx.jsonl').read_text().splitlines()];lines=(copy/'uart.log').read_text().splitlines();session=Session();changed=None;boot=None
    for i,t in enumerate(tx):
        op=t['op'];data=bytes.fromhex(t['payload_hex']);parts=lines[i+1].split();rc=int(parts[1]);reply=bytes.fromhex(parts[2]) if len(parts)==3 else b''
        if op=='I':boot=Bootstrap(1,bytes(range(1,33)),bytes(range(1,17)),bytes(range(17,33)),10000,nonce_source=lambda n,nonce=data:nonce);session.reset()
        elif op=='R':boot.abort();session.reset()
        elif op=='H':session.reset();assert reply==boot.server_hello(data)
        elif op=='F':assert reply==boot.server_finished(data);session=boot.take_provisioning().open_pc_session()
        elif op=='D':
            try:session.unwrap(data)
            except SessionError:continue
            assert rc==0
            body=reply[32:-8]
            if body.startswith(b'QKD_STREAM_WORD'):
                bad=bytearray(body);at=bad.index(b'value=')+6;bad[at]=ord('1') if bad[at]!=ord('1') else ord('0')
                lines[i+1]='QB 0 '+session.wrap(0x8100,bytes(bad)).hex();changed=i;break
            assert reply==session.wrap(0x8100,body)
    assert changed is not None
    (copy/'uart.log').write_text('\n'.join(lines)+'\n',encoding='ascii')
    argv=[sys.executable,str(ROOT/'syn/zc702/verify_secure_accumulator_board.py'),str(copy),'--output',str(out/'rejected_output')]
    p=subprocess.run(argv,capture_output=True,text=True);(out/'stdout.log').write_text(p.stdout);(out/'stderr.log').write_text(p.stderr)
    assert p.returncode!=0 and 'int(v,16)==golden[int(i)]' in p.stderr,p.stderr
    receipt=dict(status='VALID_MAC_WRONG_PA_REJECTED',changed_command_index=changed,command=argv,returncode=p.returncode,
        source_uart_sha256=hashlib.sha256((args.run/'uart.log').read_bytes()).hexdigest(),
        mutated_uart_sha256=hashlib.sha256((copy/'uart.log').read_bytes()).hexdigest(),
        scope='Negative control: valid QAS2 MAC, unchanged runner PASS fields, one wrong PA word; semantic model rejects it')
    (out/'NEGATIVE_CONTROL.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt['status'])
if __name__=='__main__':main()
