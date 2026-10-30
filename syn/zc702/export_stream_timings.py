"""Export counter-derived timing and f from captured stream attempts; no RTT claim."""
from pathlib import Path
import argparse,collections,csv,json,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
from experiment_metrics import wilson_interval
import ir_model as m
import dyn_ir as d
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('run',type=Path);args=ap.parse_args()
folder=args.run.resolve();r=json.loads((folder/'result.json').read_text());assert r['complete']
sources={};data=[]
for name,src in r['sources'].items():
    source=np.load(src['path']);z=source['basis']==0;sources[name]=(source['a'][z],source['b'][z])
for row in r['records']:
    if not row['attempts']:continue
    a,b=sources[row['source']];start=row['key_start'];q=float((a[start:start+2765]!=b[start:start+2765]).mean())
    cycles=row['attempts'][-1]['cycles'];den=2765*m.h2(q)
    data.append({'source':row['source'],'source_block':row['source_block'],'code':row.get('code',d.basic_code(row['q_pe'])),'qber_pct':q*100,
                 'outcome':row['outcome'],'attempts':len(row['attempts']),'revealed_bits':row.get('revealed',''),'leak_ec_bits':row.get('leak',''),
                 'f_ir_without_tag':(row['leak']-64)/den if den and row['added'] else '',
                 'f_ec_with_tag':row['leak']/den if den and row['added'] else '',
                 'decoder_cycles_cumulative':cycles,'decoder_busy_us_at_50MHz':cycles/50,
                 'scope':'counter-derived active decoder time; excludes UART RTT verification PA; not throughput'})
out=ROOT/'reports'/('zc702_key_stream_'+r['started_utc']);out.mkdir(exist_ok=True)
with (out/'counter_timings_and_f.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
print('STREAM_COUNTER_EXPORT_PASS',len(data),out)
