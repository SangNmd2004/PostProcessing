"""Standalone publication-style plots from measured latency CSV; no re-fitting."""
from pathlib import Path
import argparse,csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('directory',type=Path);args=ap.parse_args();folder=args.directory
with (folder/'summary.csv').open(encoding='utf-8-sig',newline='') as f:summary=list(csv.DictReader(f))
with (folder/'measurements.csv').open(encoding='utf-8-sig',newline='') as f:raw=list(csv.DictReader(f))
for kind in ['speedup','throughput']:
    fig,ax=plt.subplots(figsize=(7.2,4.2),layout='constrained')
    for k in [1,2,4]:
        rows=sorted([r for r in summary if int(r['contexts'])==k],key=lambda r:int(r['rtt_us']))
        x=[int(r['rtt_us'])/1000 for r in rows]
        field='measured_speedup_vs_K1' if kind=='speedup' else 'IR_corrected_Mbit_s'
        y=[float(r[field]) for r in rows]
        low=[];high=[]
        for r,median in zip(rows,y):
            elapsed=[int(v['elapsed_us']) for v in raw if int(v['contexts'])==k and int(v['rtt_us'])==int(r['rtt_us'])]
            if kind=='throughput':samples=[32*2765/t for t in elapsed]
            else:samples=[float(r['median_elapsed_us'])*median/t for t in elapsed]
            low.append(max(0,median-min(samples)));high.append(max(0,max(samples)-median))
        ax.errorbar(x,y,yerr=[low,high],marker='o',capsize=3,label=f'K = {k}')
    ax.set_xscale('symlog',linthresh=.1);ax.set_xticks([0,.1,1,10],['0','0.1','1','10'])
    ax.set_xlabel('Injected reveal delay (ms)')
    ax.set_ylabel('Measured speedup relative to K = 1' if kind=='speedup' else 'Corrected IR throughput (Mbit/s)')
    ax.set_title('ZC702, PL 50 MHz, DDR replay IR benchmark',fontsize=11)
    ax.grid(alpha=.25);ax.legend()
    fig.text(.5,-.025,'Repeated public vectors; correctness checks included; UART and PA excluded.\nError bars: min-max of 3 runs, not confidence intervals.',ha='center',fontsize=8)
    for suffix in ['png','svg']:fig.savefig(folder/f'latency_{kind}.{suffix}',dpi=200,bbox_inches='tight')
    plt.close(fig)
print('LATENCY_PLOTS_WRITTEN',folder)
