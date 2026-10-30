"""Reproducible functional gates with simulated Alice; no Vivado implementation.

Runs sequentially for an 8 GB host. This is not acceptance of real TRNG/security,
70 MHz/throughput claims, or research improvements listed in the source MD.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'build/zc702'
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--port',default='COM3')
args=ap.parse_args()
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
folder=OUT/'acceptance_runs'/stamp;folder.mkdir(parents=True,exist_ok=False)
receipt={'complete':False,'scope':'functional_with_PC_Alice_only','stages':[]}
def save(): (folder/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
def run(script,*arguments):
    command=[sys.executable,str(ROOT/'syn/zc702'/script),*map(str,arguments)]
    output=[]
    with (folder/(str(len(receipt['stages']))+'_'+script+'.log')).open('w',encoding='utf-8') as log:
        process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
        for line in process.stdout:
            output.append(line);log.write(line);log.flush();print(line,end='',flush=True)
        code=process.wait()
    receipt['stages'].append({'script':script,'arguments':list(map(str,arguments)),'exit_code':code});save()
    if code:raise RuntimeError('Stage failed: '+script)
    return ''.join(output)
try:
    run('build_uart.py')
    campaign=folder/'nms_gs_csv'
    run('generate_uart_campaign.py','--native-only','--cn','nms75','--puncturing','gs','--out',campaign)
    output=run('run_uart_campaign.py','--port',args.port,'--campaign',campaign/'campaign.json')
    board=next(line.split('UART_EVIDENCE ',1)[1].strip() for line in output.splitlines() if line.startswith('UART_EVIDENCE '))
    run('export_uart_csv.py',board)
    basic=json.loads((Path(board)/'result.json').read_text())
    run('merge_report_csv.py',ROOT/'reports'/('zc702_uart_'+basic['started_utc']))
    output=run('run_functional_session.py','--port',args.port,'--campaign',campaign/'campaign.json')
    functional=next(line.split('FUNCTIONAL_EVIDENCE ',1)[1].strip() for line in output.splitlines() if line.startswith('FUNCTIONAL_EVIDENCE '))
    run('report_functional_session.py',functional)
    detail=json.loads((Path(functional)/'result.json').read_text())
    assert basic['complete'] and basic['hardware_matches']==84
    assert detail['complete'] and len(detail['records'])==63 and len(detail['control_checks'])==8
    assert len(detail['multicontext_checks'])==4
    assert any(r.get('negative_tag_test') and r['verification_rejected'] for r in detail['records'])
    assert all(a.get('irq_count')==1 for r in detail['records'] for a in r['attempts'])
    receipt.update(complete=True,csv_board_run=board,functional_board_run=functional)
finally:save()
print('FUNCTIONAL_ACCEPTANCE_PASS',folder,flush=True)
