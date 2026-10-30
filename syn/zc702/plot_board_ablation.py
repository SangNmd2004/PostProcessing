"""Plot paired board ablation; conditional f on common successes and explicit component timing scope."""
from pathlib import Path
import argparse,csv,json,statistics
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('report',type=Path);args=ap.parse_args();out=args.report
assert json.loads((out/'verified_evidence.json').read_text())['raw_replay_verified']
def read(name):
    with (out/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
rows=read('trials.csv');summary=read('summary.csv');contrasts=read('paired_contrasts.csv')
names=[r['configuration'] for r in summary];groups={}
for r in rows:groups.setdefault(int(r['trial']),{})[r['configuration']]=r
common=[g for g in groups.values() if all(r['outcome']=='SUCCESS' for r in g.values())]
labels=['OMS / random\nET,PP off','OMS + GS\nET,PP off','NMS + GS\nET,PP off','NMS + GS\nET,PP on']
colors=['#536d9a','#248cab','#55a578','#ba718d'];x=np.arange(4)
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(2,2,figsize=(12,8.2))
series=[([float(r['mean_attempts_all']) for r in summary],'Mean attempts, all inputs',None),
        ([statistics.mean(float(g[name]['f_ir']) for g in common) for name in names],f'Mean f IR, common successes (n={len(common)})',(1.30,1.48)),
        ([float(r['DDR_IR_corrected_Mbit_s']) for r in summary],'DDR IR corrected Mbit/s',None)]
for ax,(values,title,ylim) in zip(axes.flat,series):
    ax.bar(x,values,color=colors,width=.62);ax.set_xticks(x,labels);ax.set_title(title);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    if ylim:ax.set_ylim(*ylim)
    else:ax.set_ylim(0,max(values)*1.2)
    for i,value in enumerate(values):ax.annotate(f'{value:.3f}',(i,value),xytext=(0,5),textcoords='offset points',ha='center',fontsize=9)
ax=axes[1,1];mean=np.array([float(r['mean_delta_attempts']) for r in contrasts]);lower=np.array([float(r['normal_approx95_low']) for r in contrasts]);upper=np.array([float(r['normal_approx95_high']) for r in contrasts])
y=np.arange(3);ax.errorbar(mean,y,xerr=[mean-lower,upper-mean],fmt='o',capsize=4,color='#35475e')
ax.axvline(0,color='#777',linestyle='--',linewidth=1);ax.set_yticks(y,['+GS','+NMS','+ET/PP']);ax.invert_yaxis()
ax.set_xlabel('Change in mean attempts (to minus from)');ax.set_title('Paired contrasts, normal-approx 95% CI');ax.grid(axis='x',alpha=.18)
fig.suptitle('ZC702 paired four-stage ablation: BSC 3%, r23, 1,000 input pairs',fontsize=14)
fig.tight_layout(rect=[0,.13,1,.95])
fig.text(.05,.035,'Timing: K=1, four-job DDR batches, RTT=0; PS/DMA/golden checks included; UART/tag/PA excluded.\n'
         'f excludes verification tags; common-success comparison avoids unequal survivor sets. Rates are descriptive aggregates.\n'
         'Sparse failure events do not establish a FER improvement. These are decoder-component measurements, not secret-key throughput.',fontsize=9)
for extension in ['png','svg']:fig.savefig(out/f'four_stage_ablation.{extension}',dpi=180,bbox_inches='tight')
plt.close(fig)
p=out/'REPORT.md';text=p.read_text(encoding='utf-8')
if 'four_stage_ablation.png' not in text:p.write_text(text+'\n[Paired ablation figure](four_stage_ablation.png) | [SVG](four_stage_ablation.svg).\n',encoding='utf-8')
print('BOARD_ABLATION_FIGURES_WRITTEN',out,flush=True)
