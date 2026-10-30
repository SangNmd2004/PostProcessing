"""Definitions for experimental FER and verification budget; no security certificate."""
from decimal import Decimal
import math

def zero_failures_upper(n,confidence=.95):
    """Exact one-sided binomial upper bound for zero events in n independent trials."""
    if n<1 or not 0<confidence<1:raise ValueError('invalid trial count/confidence')
    return -math.expm1(math.log1p(-confidence)/n)

def wilson_interval(events,trials,z=1.959963984540054):
    """Two-sided Wilson interval. This is distinct from zero_failures_upper()."""
    if not 0<=events<=trials or trials<1:raise ValueError('invalid counts')
    p=events/trials;den=1+z*z/trials
    center=(p+z*z/(2*trials))/den
    half=z*math.sqrt(p*(1-p)/trials+z*z/(4*trials*trials))/den
    return max(0,center-half),min(1,center+half)

def verification_budget(tag_bits,checks,epsilon):
    if tag_bits<1 or checks<0:raise ValueError('invalid tag parameters')
    eps=Decimal(str(epsilon))
    if not 0<eps<1:raise ValueError('invalid budget')
    bound=Decimal(checks)/Decimal(1<<tag_bits)
    return {'tag_bits':tag_bits,'checks':checks,'allocated_epsilon':str(eps),
            'union_bound':str(bound),'max_checks':int(eps*(1<<tag_bits)),'within_budget':bound<=eps}

if __name__=='__main__':
    assert abs(zero_failures_upper(3000)-.0009980790119965555)<1e-15
    assert abs(zero_failures_upper(10000)-.00029952835977664627)<1e-15
    assert verification_budget(64,5786,'1e-15')['max_checks']==18446
    assert verification_budget(64,5786,'5e-16')['within_budget']
    assert not verification_budget(64,10000,'5e-16')['within_budget']
    assert wilson_interval(0,10000)[0]==0
    print('EXPERIMENT_METRICS_CHECK_PASS')
