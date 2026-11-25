"""Conditional K1 DDR-IR latency model: fixed paired slots and measured demands.

Fresh arrival schedules are validation; inputs remain the public training pool.
This is not a QBER/FER predictor or a finite-key yield/security model.
"""
import math

def simulate(params,jobs,interval_us,policy):
    if not isinstance(jobs,int) or not 1<=jobs<=128 or interval_us<0 or policy not in [0,1,2]:raise ValueError('invalid case')
    service=params['slot_service_us'];gaps=params['profile_gap_us'];proxy=params['slot_IR_proxy_bits']
    if len(service)!=4 or len(proxy)!=4 or any(not math.isfinite(v) or v<=0 for v in service) or any(v<0 or not math.isfinite(v) for v in gaps):raise ValueError('invalid parameters')
    rows=[];finish=0.;profile=0;out=0
    for i in range(jobs):
        ready=finish+(gaps[profile] if i else 0)
        dispatch=max(i*interval_us,ready)
        arrived=jobs if interval_us==0 else min(jobs,math.floor(dispatch/interval_us)+1)
        backlog=max(0,arrived-i-1)
        if policy==2:
            if backlog>=4:profile=1
            elif backlog<=1:profile=0
        else:profile=policy
        slot=i%2*2+profile;finish=dispatch+service[slot];out+=proxy[slot]
        rows.append(dict(id=i,dispatch=dispatch,complete=finish,profile=profile,slot=slot,backlog=backlog))
    return dict(elapsed_us=finish,IR_proxy_bits=out,IR_proxy_Mbit_s=out/finish,rows=rows)

if __name__=='__main__':
    p=dict(slot_service_us=[10,5,20,8],profile_gap_us=[1,2],slot_IR_proxy_bits=[100,80,90,70])
    one=simulate(p,2,0,0);assert one['elapsed_us']==31 and one['IR_proxy_bits']==190
    paced=simulate(p,2,100,0);assert paced['elapsed_us']==120
    fixed=simulate(p,8,0,1);assert [r['profile'] for r in fixed['rows']]==[1]*8
    adaptive=simulate(p,8,0,2);assert adaptive['rows'][0]['profile']==1 and adaptive['rows'][-1]['profile']==0
    for mode in [0,1,2]:
        r=simulate(p,16,50,mode);assert all(row['dispatch']>=row['id']*50 for row in r['rows'])
    print('PACED_COMPONENT_MODEL_SELF_CHECK_PASS; NO_BOARD_OR_SECURITY_CLAIM')
