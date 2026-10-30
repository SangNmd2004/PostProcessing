"""Ideal closed-queue latency model. Predictions only, not board measurements.

Assumptions: one decoder, K independent resident contexts, identical attempt
service times, fixed post-attempt RTT, work-conserving schedule. Shared UART
service is modeled separately and can become the bottleneck. No PA overlap is
implied. Board validation and held-out calibration remain required.
"""
import heapq

def ideal_speedup(contexts,decode_us,rtt_us):
    if contexts<1 or decode_us<=0 or rtt_us<0:raise ValueError('invalid parameters')
    return min(float(contexts),1+rtt_us/decode_us)

def simulate(contexts,decode_us,rtt_us,attempts=10000,uart_us=0):
    ideal_speedup(contexts,decode_us,rtt_us)
    if attempts<1 or uart_us<0:raise ValueError('invalid workload')
    ready=[(0.,ctx) for ctx in range(contexts)];heapq.heapify(ready)
    decoder_free=0.;link_free=0.;last=0.
    for _ in range(attempts):
        at,ctx=heapq.heappop(ready)
        start=max(at,decoder_free);last=start+decode_us;decoder_free=last
        response=max(last+rtt_us,link_free)+uart_us;link_free=response
        heapq.heappush(ready,(response,ctx))
    return {'elapsed_us':last,'attempts_per_second':attempts*1e6/last,
            'assumption':'ideal closed queue; no measured claim'}

def simulate_blind_jobs(contexts,service_us,rtt_us,attempts_per_vector,jobs):
    """Finite workload with RTT only on failed attempts; no UART/PA in this model."""
    if contexts<1 or jobs<contexts or service_us<=0 or rtt_us<0 or min(attempts_per_vector)<1:
        raise ValueError('invalid workload')
    queue=[(0.,ctx,ctx,0) for ctx in range(contexts)];heapq.heapify(queue)
    next_job=contexts;decoder=0.;finish=0.
    while queue:
        ready,ctx,job,attempt=heapq.heappop(queue)
        finish=max(ready,decoder)+service_us;decoder=finish
        if attempt+1<attempts_per_vector[job%len(attempts_per_vector)]:
            heapq.heappush(queue,(finish+rtt_us,ctx,job,attempt+1))
        elif next_job<jobs:
            heapq.heappush(queue,(finish,ctx,next_job,0));next_job+=1
    return finish

if __name__=='__main__':
    for rtt in [0,100,1000]:
        one=simulate(1,100,rtt)
        for k in [1,2,4]:
            many=simulate(k,100,rtt)
            measured_model=many['attempts_per_second']/one['attempts_per_second']
            assert abs(measured_model-ideal_speedup(k,100,rtt))<.01
    assert simulate(4,100,100,uart_us=1000)['attempts_per_second']<1100
    print('QUEUE_LATENCY_MODEL_SELF_CHECK_PASS; NOT_BOARD_VALIDATION')
