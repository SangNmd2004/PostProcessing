"""Conditional steady-state profile crossover; mathematical model, not measured board performance.

Yields must be supplied by a justified finite-key/security model. A functionally
matching PA output length does not by itself certify the yield as secret bits.
"""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class Profile:
    name:str
    accepted_probability:float
    retained_bits_per_accepted_block:float
    # Each demand is seconds of a serial resource per input block. Parallel
    # context/RTT effects must already be reflected in the decoder demand.
    resource_demands:dict
    def __post_init__(self):
        if not 0<=self.accepted_probability<=1 or self.retained_bits_per_accepted_block<0:
            raise ValueError('invalid yield')
        if not self.resource_demands or any(v<0 or not math.isfinite(v) for v in self.resource_demands.values()):
            raise ValueError('invalid demands')
    @property
    def yield_per_input(self):return self.accepted_probability*self.retained_bits_per_accepted_block
    @property
    def capacity(self):
        peak=max(self.resource_demands.values())
        return 1/peak if peak else math.inf
    def rate(self,arrival_blocks_per_second):
        if arrival_blocks_per_second<0:raise ValueError('negative arrival rate')
        return self.yield_per_input*min(arrival_blocks_per_second,self.capacity)

def crossing(efficiency,throughput):
    """EFF higher yield, THR higher input capacity: return a unique positive crossing if one exists."""
    ye,yt=efficiency.yield_per_input,throughput.yield_per_input
    ce,ct=efficiency.capacity,throughput.capacity
    if not ye>yt>0 or not ct>ce>0:
        return {'exists':False,'reason':'requires EFF higher yield and THR higher input capacity'}
    point=ye*ce/yt
    if not ce<point<ct:
        return {'exists':False,'reason':'THR saturated retained-bit rate does not exceed EFF',
                'efficiency_saturation':ye*ce,'throughput_saturation':yt*ct}
    return {'exists':True,'arrival_blocks_per_second':point,'retained_bits_per_second':ye*ce,
            'efficiency_capacity':ce,'throughput_capacity':ct,
            'scope':'fluid steady-state bound; no burst/backpressure/hysteresis transients'}

def blind_expectations(outcomes,n_key,syndrome_bits,punctured,r0,delta):
    """Aggregate a fixed policy's attempts and IR leakage from outcome masses.

    Each item: probability, attempts, outcome in correct/wrong/discard. Decoder
    stops on wrong convergence too. Leak here excludes verification and PE.
    Empirical masses require held-out checking; this function does not predict
    convergence probabilities from QBER/code on its own.
    """
    if n_key<=0 or syndrome_bits<punctured or not 0<=r0<=punctured or delta<1:
        raise ValueError('invalid code/reveal configuration')
    if abs(sum(r['probability'] for r in outcomes)-1)>1e-10:raise ValueError('outcome masses must sum to one')
    max_attempts=1+math.ceil((punctured-r0)/delta)
    correct=wrong=attempts=leak_correct=0.
    for r in outcomes:
        p=r['probability'];a=r['attempts'];kind=r['outcome']
        if p<0 or not 1<=a<=max_attempts or kind not in ['correct','wrong','discard']:raise ValueError('invalid outcome')
        disclosed=r0+min((a-1)*delta,punctured-r0)
        leak=syndrome_bits-punctured+disclosed
        attempts+=p*a
        if kind=='correct':correct+=p;leak_correct+=p*leak
        elif kind=='wrong':wrong+=p
    reach=[sum(r['probability'] for r in outcomes if r['attempts']>=a) for a in range(1,max_attempts+1)]
    assert abs(sum(reach)-attempts)<1e-9
    return {'probability_correct':correct,'probability_wrong':wrong,'probability_discard':1-correct-wrong,
            'expected_attempts':attempts,'reach_probability':reach,
            'mean_IR_leak_given_correct':leak_correct/correct if correct else None,
            'mean_disclosed_fraction_given_correct':leak_correct/(n_key*correct) if correct else None,
            'scope':'IR leakage excludes PE/tag; wrong codeword is not a tag rejection'}

if __name__=='__main__':
    # Synthetic unit examples only; no imported historic 5.81/8.67 board claim.
    e=Profile('EFF',1,.6,{'decoder':.25,'PA':.01})
    t=Profile('THR',1,.4,{'decoder':.125,'PA':.01})
    point=crossing(e,t);assert point['exists'] and abs(point['arrival_blocks_per_second']-6)<1e-12
    assert e.rate(2)>t.rate(2) and abs(e.rate(6)-t.rate(6))<1e-12 and t.rate(8)>e.rate(8)
    pa_limited=Profile('THR',1,.4,{'decoder':.125,'PA':.3})
    assert not crossing(e,pa_limited)['exists']
    expected=blind_expectations([dict(probability=.7,attempts=1,outcome='correct'),
        dict(probability=.2,attempts=2,outcome='correct'),dict(probability=.1,attempts=5,outcome='discard')],2765,1024,307,0,77)
    assert abs(expected['expected_attempts']-1.6)<1e-12
    assert abs(expected['mean_IR_leak_given_correct']-(.7*717+.2*794)/.9)<1e-10
    print('CROSSOVER_AND_BLIND_EXPECTATIONS_SELF_CHECK_PASS; SYNTHETIC_EXAMPLES_NOT_BOARD')
