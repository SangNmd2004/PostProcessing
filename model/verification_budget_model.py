"""Conditional verification collision accounting; no persistence implementation.

Bounds assume the deployed hash/seed policy establishes per-check epsilon.
Input buffer capacity is distinct from PA output length and hard-cap safety is
separate from a plug-in rejection-rate workload estimate.
"""
from pathlib import Path
from fractions import Fraction
import argparse,json,math
TWO_TO_64=1<<64
RECONCILED_BITS_PER_BLOCK=2765

def _count(n):
    if not isinstance(n,int) or isinstance(n,bool) or n<0:raise ValueError('nonnegative integer count required')
    return n

def compute_union_bound(n_blocks,tag_bits=64):
    _count(n_blocks)
    if not isinstance(tag_bits,int) or isinstance(tag_bits,bool) or tag_bits<1:raise ValueError('positive integer tag length required')
    return float(min(Fraction(1),Fraction(n_blocks,1<<tag_bits)))

def compute_max_blocks_for_epsilon(eps_cor,tag_bits=64):
    epsilon=Fraction(str(eps_cor))
    if not 0<epsilon<1 or not isinstance(tag_bits,int) or isinstance(tag_bits,bool) or tag_bits<1:raise ValueError('invalid epsilon or tag length')
    return (epsilon.numerator*(1<<tag_bits))//epsilon.denominator

def analyze_accumulation_session(buffer_capacity_bits=16_000_000,rejection_rate=0.0,eps_cor_budget='1e-15'):
    _count(buffer_capacity_bits)
    if not math.isfinite(rejection_rate) or not 0<=rejection_rate<1:raise ValueError('rejection rate must be finite in [0,1)')
    cap=compute_max_blocks_for_epsilon(eps_cor_budget)
    fit=buffer_capacity_bits//RECONCILED_BITS_PER_BLOCK
    estimate=math.ceil(Fraction(fit)/(1-Fraction(str(rejection_rate))))
    return dict(buffer_capacity_bits=buffer_capacity_bits,whole_blocks_that_fit=fit,retained_input_bits=fit*RECONCILED_BITS_PER_BLOCK,
                unused_capacity_bits=buffer_capacity_bits-fit*RECONCILED_BITS_PER_BLOCK,
                rejection_rate=rejection_rate,estimated_verification_attempts=estimate,max_verification_attempts=cap,
                conditional_union_bound_at_estimate=compute_union_bound(estimate),
                estimate_within_cap=estimate<=cap,hard_cap_failure_bound=compute_union_bound(cap),
                scope='INPUT_BUFFER_AND_CONDITIONAL_COLLISION_ACCOUNTING; rejection estimate is not a probability guarantee; PA output unspecified')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=Path);args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    report=dict(status='CONDITIONAL_MATH_ANALYSIS_ONLY',persistence_implemented=False,anti_rollback_verified=False,
                default_cap=compute_max_blocks_for_epsilon('1e-15'),
                assumptions=['per-check conditional hash collision bound established separately','valid hash-family seed policy','count includes all reserved checks'],
                scenarios=[analyze_accumulation_session(rejection_rate=r) for r in [0,.1,.3,.5]],
                excluded_claims=['secret output volume','absolute security','MAC bound','storage persistence','rollback protection'])
    (args.output/'REPORT.json').write_text(json.dumps(report,indent=2)+'\n')
    (args.output/'REPORT.md').write_text('# Conditional verification budget analysis\n\n18446 checks at assumed per-check epsilon2^-64 and budget1e-15. '
        'A16Mbit input buffer fits5786 whole blocks, not16Mbit PA output. Rejection-rate estimates are not worst-case guarantees. '
        'No durable storage, anti-rollback, production or composable protocol security claim. See REPORT.json.\n',encoding='utf-8')
    print('CONDITIONAL_BUDGET_ANALYSIS_WRITTEN',args.output)
if __name__=='__main__':main()
