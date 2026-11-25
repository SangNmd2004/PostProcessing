"""Export measured IR proxy curves with frozen predictions; never label them secret-key rate."""
from pathlib import Path
import argparse,csv,json,statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--sequence',required=True,type=Path);args=ap.parse_args();folder=args.sequence
    with (folder/'arrival_verified/measurements.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    config=json.loads((folder/'frozen_model/frozen_validation.json').read_text());groups={}
    for r in rows:groups.setdefault((int(r['interval']),int(r['policy'])),[]).append(float(r['IR_proxy_Mbit_s']))
    names=['EFFICIENCY','THROUGHPUT','ADAPTIVE'];colors=['#2166ac','#b2182b','#1b7837'];fig,ax=plt.subplots(figsize=(8.6,5.3))
    summary=[]
    for p in range(3):
        intervals=sorted({i for i,policy in groups if policy==p},reverse=True);x=[1e6/i for i in intervals]
        y=[statistics.median(groups[i,p]) for i in intervals]
        low=[ym-min(groups[i,p]) for i,ym in zip(intervals,y)];high=[max(groups[i,p])-ym for i,ym in zip(intervals,y)]
        predicted=[next(c['prediction']['IR_proxy_Mbit_s'] for c in config['cases'] if c['interval']==i and c['policy']==p) for i in intervals]
        ax.errorbar(x,y,yerr=[low,high],fmt='o-',label=names[p]+' measured',color=colors[p],capsize=3)
        ax.plot(x,predicted,'--',color=colors[p],alpha=.65,label=names[p]+' frozen prediction')
        summary.extend(dict(policy=names[p],arrival_blocks_s=a,interval_us=i,measured_proxy_Mbit_s=b,predicted_proxy_Mbit_s=c,repeat_min=min(groups[i,p]),repeat_max=max(groups[i,p])) for a,i,b,c in zip(x,intervals,y,predicted))
    ax.set(xlabel='Scheduled arrival rate (blocks/s)',ylabel='IR retained-bit proxy (Mbit/s)',title='ZC702 50 MHz: timer-paced DDR IR, K=1\n128 repeated jobs/run; excludes UART, tag, PE leakage and PA')
    ax.grid(alpha=.22);ax.legend(fontsize=8,ncol=2);fig.text(.5,.015,'Error bars: observed min/max of two repetitions, not confidence intervals.',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.035,1,1))
    for ext in ['png','svg']:fig.savefig(folder/('IR_proxy_validation.'+ext),dpi=180)
    with (folder/'IR_proxy_summary.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    print('PACED_PLOT_EXPORTED',folder)
if __name__=='__main__':main()
