"""Two-resource approximation: shared decoder plus serialized PS/DMA load/reveal.

No measurement is fabricated. L/R must be calibrated on training only; decoder
cycles below follow the RTL schedule for PP disabled and strict convergence.
"""
import math
import ir_model as ir
import layer_sched

def attempt_cycles(code,iterations,converged,pp_used=0,final_usc=None):
    if iterations<1 or pp_used:raise ValueError('only positive-iteration, PP-disabled attempts are modeled')
    base=ir.load_codes(128)[code];edges=sum(v>=0 for row in base for v in row)
    # S_LOAD=26 plus scheduler/start/done observations=2. Failed decode then
    # performs S_USC pipeline/popcount for each layer and a final S_UFIN.
    usc=not converged if final_usc is None else final_usc
    return 28+iterations*layer_sched.iteration_cycles(base)+(edges+8*len(base)+1 if usc else 0)

def packet_workload(payload):
    cfg,cfg2,pre,n,ns,err,nrev=payload[:7]
    if (cfg>>16)&3 or cfg2&15:raise ValueError('prediction cohort requires ET=0 and PP=0 to disambiguate strict convergence')
    if pre:raise ValueError('prediction cohort uses r0=0')
    code=ir.CODE_ORDER[cfg&3];traces=[]
    for i in range(n):
        expected=payload[7+i];conv=bool(expected>>31);iterations=expected&0xfff
        if conv and iterations>=((cfg>>8)&255):raise ValueError('final USC route ambiguous at iteration limit')
        if (expected>>28)&3:raise ValueError('PP not supported by this cycle model')
        traces.append({'decode_us':attempt_cycles(code,iterations,conv)/50,
                       'cycles':attempt_cycles(code,iterations,conv),
                       'reveal_bits':payload[7+n+i] if i+1<n else 0})
    if not payload[7+n-1]>>31:raise ValueError('scheduler prediction cohort uses converged complete jobs')
    return traces

def simulate(contexts,workloads,jobs,load_us,reveal_us_per_bit,rtt_us):
    """CPU load/reveal may overlap decode; queued contexts use round robin.

    L includes average per-job host management, approximated as input load.
    R absorbs average retry dispatch overhead per revealed bit. IRQ/KEY output
    contention is not separately modeled; RTT starts when PS can notice FAIL.
    """
    if not 1<=contexts<=4 or jobs<contexts or not workloads:raise ValueError('invalid workload')
    if min(load_us,reveal_us_per_bit,rtt_us)<0:raise ValueError('negative timing')
    states=[dict(job=i,attempt=0,ready=False) for i in range(contexts)]
    tasks=[dict(at=0.,kind='initial',ctx=i,order=i) for i in range(contexts)]
    now=0.;cpu=None;decoder=None;rr=0;next_job=contexts;done=0;decoded=0;serial=contexts
    cpu_total=decoder_total=0.;eps=1e-9
    while done<jobs:
        if cpu is not None and cpu['finish']<=now+eps:
            states[cpu['ctx']]['ready']=True;cpu=None
        if decoder is not None and decoder['finish']<=now+eps:
            ctx=decoder['ctx'];s=states[ctx];trace=workloads[s['job']%len(workloads)]
            notice=max(now,cpu['finish']) if cpu is not None else now
            if s['attempt']+1<len(trace):
                count=trace[s['attempt']]['reveal_bits'];s['attempt']+=1
                tasks.append(dict(at=notice+rtt_us,kind='reveal',ctx=ctx,bits=count,order=serial));serial+=1
            else:
                done+=1
                if next_job<jobs:
                    s.update(job=next_job,attempt=0,ready=False);next_job+=1
                    tasks.append(dict(at=notice,kind='load',ctx=ctx,order=serial));serial+=1
            decoder=None
        if decoder is None:
            ready=[(rr+offset)%contexts for offset in range(contexts) if states[(rr+offset)%contexts]['ready']]
            if ready:
                ctx=ready[0];s=states[ctx];s['ready']=False;rr=(ctx+1)%contexts
                duration=workloads[s['job']%len(workloads)][s['attempt']]['decode_us']
                if duration<=0:raise ValueError('nonpositive decode duration')
                decoder=dict(ctx=ctx,finish=now+duration);decoded+=1;decoder_total+=duration
        if cpu is None:
            available=[t for t in tasks if t['at']<=now+eps]
            if available:
                def priority(t):
                    rank={'initial':0,'load':1,'reveal':2}[t['kind']]
                    return rank,t['ctx'] if rank==2 else t['order']
                task=min(available,key=priority);tasks.remove(task)
                duration=task.get('bits',0)*reveal_us_per_bit if task['kind']=='reveal' else load_us
                cpu=dict(ctx=task['ctx'],finish=now+duration);cpu_total+=duration
        if done==jobs:break
        upcoming=[v['finish'] for v in [cpu,decoder] if v is not None]
        if cpu is None and tasks:upcoming.append(min(t['at'] for t in tasks))
        if not upcoming:raise RuntimeError('scheduler deadlock')
        next_time=min(upcoming)
        if next_time<now-eps:raise RuntimeError('event time reversal')
        now=max(now,next_time)
    assert now+1e-6>=max(cpu_total,decoder_total)
    return {'elapsed_us':now,'decode_us_sum':decoder_total,'cpu_us_sum':cpu_total,'attempts':decoded}

if __name__=='__main__':
    traces=[[dict(decode_us=10,reveal_bits=5),dict(decode_us=20,reveal_bits=0)],
            [dict(decode_us=15,reveal_bits=0)]]
    for rtt in [0,100,1000]:
        one=simulate(1,traces,20,3,.2,rtt)
        assert abs(one['elapsed_us']-(10*(30+3+rtt+1)+10*(15+3)))<1e-7
    total=simulate(1,traces,20,0,0,0)['elapsed_us']
    for k in [1,2,4]:assert abs(simulate(k,traces,20,0,0,0)['elapsed_us']-total)<1e-7
    assert attempt_cycles('r12',36,False)==9126
    assert attempt_cycles('r23',23,True)==4881
    assert attempt_cycles('r56',9,True)==1639
    print('RESOURCE_MODEL_CAUSALITY_AND_CYCLE_CHECK_PASS; NOT_BOARD_VALIDATION')
