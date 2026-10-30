"""Export timing figures from verified CSVs; min/max across repeats, not FER CIs."""
from pathlib import Path
import argparse,csv,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('report',type=Path);args=ap.parse_args();out=args.report
assert json.loads((out/'verified_evidence.json').read_text())['raw_replay_verified']
with (out/'tung_block.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
codes=['r12','r23','r34','r56'];groups=[[r for r in rows if r['code']==c and int(r['delay_us'])==0] for c in codes]
assert all(len(g)==3 for g in groups)
fields=['PS_load_us','PS_ir_poll_us','PS_key_rx_us','PS_reveal_write_us','strip_D_us','verification_call_us','PA1024_call_us']
labels=['Input setup / cache / DMA','IR RUN to status','KEY RX / cache','REVEAL writes','Strip D','Tag64 call (DMA + PL)','PA1024 call (DMA + PL)']
colors=['#425f92','#168aad','#8ecae6','#90be6d','#f9c74f','#f8961e','#bd5d74']
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
x=np.arange(4);fig,ax=plt.subplots(figsize=(10,5.3));bottom=np.zeros(4)
for field,label,color in zip(fields,labels,colors):
    means=np.array([np.mean([float(r[field]) for r in g]) for g in groups])
    ax.bar(x,means,bottom=bottom,label=label,color=color,width=.56);bottom+=means
totals=[[float(r['disjoint_compute_spans_us']) for r in g] for g in groups]
assert np.allclose(bottom,[np.mean(t) for t in totals])
ax.errorbar(x,bottom,yerr=[bottom-np.array([min(t) for t in totals]),np.array([max(t) for t in totals])-bottom],fmt='none',ecolor='#111',capsize=4)
ax.set_xticks(x,codes);ax.set_ylabel('Instrumented disjoint spans (microseconds)')
ax.set_title('ZC702 50 MHz: compute spans, K=1, zero injected host delay')
ax.legend(loc='upper left',bbox_to_anchor=(1.01,1),frameon=False)
ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
fig.subplots_adjust(right=.70,bottom=.19)
fig.text(.08,.035,'Three repeats: mean with min/max range. Counter overhead retained.\nExcludes UART/host gaps; verify and PA include cache/DMA. Different fixture per code; not a rate ablation.',fontsize=9)
for extension in ['png','svg']:fig.savefig(out/f'compute_phase_breakdown.{extension}',dpi=180,bbox_inches='tight')
plt.close(fig)
fig,ax=plt.subplots(figsize=(9,5.3));width=.32
for offset,field,label,color in [(-width/2,'disjoint_compute_spans_us','Instrumented compute spans','#168aad'),
                                (width/2,'host_transaction_us','Host transaction (public debug workload)','#f8961e')]:
    values=[[float(r[field]) for r in g] for g in groups];mean=np.array([np.mean(v) for v in values])
    ax.bar(x+offset,mean,width,label=label,color=color)
    ax.errorbar(x+offset,mean,yerr=[mean-np.array([min(v) for v in values]),np.array([max(v) for v in values])-mean],fmt='none',ecolor='#222',capsize=3)
    for location,value in zip(x+offset,mean):
        label=f'{value/1000:.1f} ms' if value>=10000 else f'{value:.0f} us'
        ax.annotate(label,(location,value),xytext=(0,6),textcoords='offset points',ha='center',fontsize=8)
ax.set_yscale('log');ax.set_ylim(80,3e6);ax.set_xticks(x,codes)
ax.set_ylabel('Microseconds (log scale)');ax.set_title('UART validation wall time and compute spans: different scopes',pad=58)
ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),frameon=False);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
fig.subplots_adjust(bottom=.20)
fig.text(.09,.04,'Mean and min/max of three zero-delay repeats. Includes full KEY readback and expected PA payload.\nThis is not a production traffic benchmark or secret-key throughput.',fontsize=9)
for extension in ['png','svg']:fig.savefig(out/f'UART_validation_vs_compute.{extension}',dpi=180,bbox_inches='tight')
plt.close(fig)
report=out/'REPORT.md';text=report.read_text(encoding='utf-8')
if 'compute_phase_breakdown.png' not in text:
    text+='\n[Đồ thị các span compute](compute_phase_breakdown.png) · [SVG](compute_phase_breakdown.svg) · '
    text+='[UART validation và compute](UART_validation_vs_compute.png) · [SVG](UART_validation_vs_compute.svg).\n'
    report.write_text(text,encoding='utf-8')
print('PHASE_FIGURES_WRITTEN',out)
