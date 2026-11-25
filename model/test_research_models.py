"""Regression tests for event ordering, split preservation and conditional budgets."""
import copy,unittest
from fractions import Fraction
from finite_key_accumulation_model import replay_events,simulate_accumulation_trajectory
from verification_budget_model import compute_union_bound,compute_max_blocks_for_epsilon,analyze_accumulation_session

def append(i,bad=False):
    return dict(session_id=1,event_id=i*2,kind='APPEND',block_id=i,nk=[2570,190,5],nt=[2607,135,4],mt=[1300,100,3] if bad else [0,0,0],leak=269,time_s=i)

class ResearchModelTests(unittest.TestCase):
    def test_split_preserves_tail(self):
        records=[dict(nk=[2570,190,5],nt=[2607,135,4],mt=[0,0,0] if i<90 else [1300,100,3],leak=269,replay_time_seconds=i) for i in range(92)]
        result=simulate_accumulation_trajectory(records,[.6,.2,0],[.75,.125,.125])
        self.assertTrue(result[90]['split']);self.assertEqual(result[90]['remaining_bits'],2765);self.assertEqual(result[91]['bits'],5530)
    def test_repeated_bitcount_decisions_remain_distinct(self):
        events=[append(0),dict(session_id=1,event_id=1,kind='DECIDE',time_s=0),dict(session_id=1,event_id=2,kind='DECIDE',time_s=3601)]
        rows=replay_events(events);self.assertEqual(len(rows),3);self.assertEqual(rows[1]['bits'],rows[2]['bits']);self.assertNotEqual(rows[1]['event_id'],rows[2]['event_id'])
    def test_commit_after_emit_only(self):
        events=[]
        for i in range(40):events.append(append(i))
        events.append(dict(session_id=1,event_id=80,kind='DECIDE',time_s=3600))
        rows=replay_events(events);self.assertEqual(rows[-1]['action'],'emit');self.assertEqual(rows[-1]['bits_after'],110600)
        events.append(dict(session_id=1,event_id=81,kind='EMIT'));self.assertEqual(replay_events(events)[-1]['bits_after'],0)
        events[-1]=dict(append(40),event_id=81,time_s=3601)
        with self.assertRaises(ValueError):replay_events(events)
    def test_split_event_commit_and_abort(self):
        events=[append(i) for i in range(90)];events.append(dict(session_id=1,event_id=180,kind='DECIDE',time_s=90))
        events.extend([dict(append(90,True),event_id=181),dict(session_id=1,event_id=182,kind='DECIDE',time_s=90),dict(session_id=1,event_id=183,kind='EMIT')])
        self.assertEqual(replay_events(events)[-1]['bits_after'],2765)
        events.append(dict(session_id=1,event_id=184,kind='ABORT'));self.assertEqual(replay_events(events)[-1]['bits_after'],0)
    def test_duplicate_ids_and_session_mismatch(self):
        for second in [append(0),dict(append(1),block_id=0),dict(append(1),session_id=2)]:
            with self.assertRaises(ValueError):replay_events([append(0),second])
    def test_time_and_metadata_rejection(self):
        for update in [dict(time_s=-1),dict(mt=[2608,0,0]),dict(nk=[-1,0,0]),dict(leak=-1)]:
            with self.assertRaises(ValueError):replay_events([append(0),dict(append(1),**update)])
    def test_abort_does_not_allow_block_reuse(self):
        with self.assertRaises(ValueError):replay_events([append(0),dict(session_id=1,event_id=1,kind='ABORT'),dict(append(0),event_id=2)])
    def test_reset_requires_new_session(self):
        with self.assertRaises(ValueError):replay_events([append(0),dict(session_id=1,event_id=1,kind='RESET')])
        rows=replay_events([append(0),dict(session_id=2,event_id=0,kind='RESET'),dict(append(0),session_id=2,event_id=1)])
        self.assertEqual(rows[-1]['bits_after'],2765)
    def test_mismatch_observation_is_not_model_input(self):
        e=dict(session_id=1,event_id=1,kind='DECIDE',time_s=0,reported=dict(action='emit',bits=999,ell=100,split=True,emit_bits=999))
        row=replay_events([append(0),e])[-1];self.assertFalse(row['all_fields_match']);self.assertEqual(row['action'],'wait')
    def test_buffer_boundary_and_zero(self):
        row=analyze_accumulation_session();self.assertEqual(row['whole_blocks_that_fit'],5786);self.assertEqual(row['retained_input_bits'],15998290);self.assertEqual(row['unused_capacity_bits'],1710)
        self.assertEqual(analyze_accumulation_session(2764)['whole_blocks_that_fit'],0);self.assertEqual(analyze_accumulation_session(2765)['whole_blocks_that_fit'],1)
    def test_budget_exact_threshold(self):
        self.assertEqual(compute_max_blocks_for_epsilon('1e-15'),18446)
        eps=Fraction(17,1<<64);self.assertEqual(compute_max_blocks_for_epsilon(eps),17)
        self.assertEqual(compute_union_bound(1<<65),1);self.assertEqual(compute_union_bound(0),0)
    def test_rejected_inputs(self):
        for rate in [-.1,1,float('nan'),float('inf')]:
            with self.assertRaises(ValueError):analyze_accumulation_session(rejection_rate=rate)
        for n in [-1,1.5,True]:
            with self.assertRaises(ValueError):compute_union_bound(n)

if __name__=='__main__':unittest.main(verbosity=2)
