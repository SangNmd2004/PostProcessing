"""Negative control: alter a raw per-job leakage metric while runner JSON remains PASS."""
from pathlib import Path
import argparse,json,re,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    altered=out/'altered_capture';shutil.copytree(args.run,altered)
    p=altered/'capture/uart.log';uart=p.read_text();changed,count=re.subn(r'(QKD_PACED_JOB[^\n]* leak=)(\d+)',lambda m:m[1]+str(int(m[2])+1),uart,count=1);assert count==1;p.write_text(changed)
    cmd=[sys.executable,str(ROOT/'syn/zc702/verify_paced_board.py'),str(altered),'--output',str(out/'rejected_report'),'--no-job-update']
    result=subprocess.run(cmd,capture_output=True,text=True);(out/'stdout.log').write_text(result.stdout);(out/'stderr.log').write_text(result.stderr)
    assert result.returncode!=0 and "r['leak']==v['leak']" in result.stderr,result.stderr
    (out/'NEGATIVE_CONTROL.json').write_text(json.dumps(dict(status='ALTERED_UART_LEAK_REJECTED',command=cmd,returncode=result.returncode,runner_result_unchanged=True),indent=2)+'\n');print('ALTERED_UART_LEAK_REJECTED')
if __name__=='__main__':main()
