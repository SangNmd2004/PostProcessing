"""Event-based finite-key functional model and retrospective raw-transcript replay.

No source-security certification. Explicit DECIDE/EMIT events preserve split tail;
replaying an existing board run is never labeled prospective validation.
"""
from pathlib import Path
import argparse,csv,hashlib,json,math,re,struct,sys,zlib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'model'))
import pa_model as pa
from pa_accum import PAAccumulator


def predict_decoy_finite_key(n_k,n_t,m_t,mu,pk,leak_ec,eps_sec=1e-9,eps_cor=1e-15):
    return pa.secure_length_decoy(n_k,n_t,m_t,mu,pk,leak_ec,eps_sec,eps_cor)


def simulate_accumulation_trajectory(records,mu,pk,eps_sec=1e-9,eps_cor=1e-15):
    """Source simulation: decide and commit after each appended source block."""
    acc=PAAccumulator(mu,pk,eps_sec=eps_sec,eps_cor=eps_cor);trajectory=[]
    for i,r in enumerate(records):
        t=r.get('replay_time_seconds',i)
        acc.add(r['nk'],r['nt'],r['mt'],r.get('leak',0),t)
        action,ell,asym,reason=acc.decide(t)
        row=dict(block_index=i,time_s=t,bits=acc.n,ell=ell,asym=asym,action=action,reason=reason,
                 split=bool(acc._split),emit_bits=acc.emit_n if action=='emit' else 0)
        if action=='emit':acc.emitted()
        elif action=='abort':acc.reset()
        row['remaining_bits']=acc.n;trajectory.append(row)
    return trajectory


def replay_events(events,mu=(.6,.2,0),pk=(.75,.125,.125),eps_sec=1e-9,eps_cor=1e-15):
    """Replay ordered events. A decision does not commit an EMIT until PA succeeds.

    event_id is strictly increasing per session; duplicate block IDs within that
    session are rejected even after explicit ABORT. RESET starts a fresh session.
    reported fields are observations to compare, never model inputs.
    """
    acc=PAAccumulator(mu,pk,eps_sec=eps_sec,eps_cor=eps_cor)
    sid=None;last_id=-1;seen=set();pending=None;last_t=-math.inf;rows=[];closed_sessions=set()
    for event in events:
        kind=event['kind'];new_sid=event['session_id'];eid=event['event_id']
        if not isinstance(eid,int) or isinstance(eid,bool) or eid<0:raise ValueError('invalid event ID')
        if kind=='RESET':
            if new_sid==sid or new_sid in closed_sessions:raise ValueError('RESET needs a fresh session ID')
            if sid is not None:closed_sessions.add(sid)
            sid=new_sid;last_id=-1;seen=set();pending=None;last_t=-math.inf;acc.reset()
        elif sid is None:sid=new_sid
        if new_sid!=sid or eid<=last_id:raise ValueError('session mismatch or repeated/out-of-order event')
        last_id=eid;before=acc.n
        row=dict(session_id=sid,event_id=eid,kind=kind,bits_before=before)
        if kind=='APPEND':
            if pending is not None:raise ValueError('pending EMIT must be resolved before append')
            block=event['block_id'];t=event['time_s'];leak=event['leak']
            counts=[event[k] for k in ['nk','nt','mt']]
            if block in seen or not math.isfinite(t) or t<last_t:raise ValueError('duplicate block or reversed time')
            if any(len(v)!=3 or any(not isinstance(x,int) or isinstance(x,bool) or x<0 for x in v) for v in counts):raise ValueError('invalid counts')
            if not sum(counts[0]) or any(x>y for x,y in zip(counts[2],counts[1])):raise ValueError('invalid metadata')
            if not isinstance(leak,int) or leak<0:raise ValueError('invalid leak')
            acc.add(*counts,leak,t);seen.add(block);last_t=t
        elif kind=='DECIDE':
            t=event['time_s']
            if pending is not None or not math.isfinite(t) or t<last_t:raise ValueError('pending EMIT or reversed decision time')
            last_t=t;action,candidate,asym,reason=acc.decide(t)
            prediction=dict(action=action,bits=acc.n,ell=candidate//64*64 if action=='emit' else 0,
                            split=bool(acc._split),emit_bits=acc.n if action=='abort' else acc.emit_n)
            row.update(prediction,candidate_ell=candidate,asym=asym,time_s=t,reason=reason)
            reported=event.get('reported')
            if reported is not None:
                for k,v in prediction.items():row[k+'_matches']=reported[k]==v
                row['all_fields_match']=all(row[k+'_matches'] for k in prediction)
            if action=='emit':pending=prediction.copy()
            elif action=='abort':acc.reset()
        elif kind=='EMIT':
            if pending is None:raise ValueError('EMIT without decision')
            row.update(input_bits=pending['emit_bits'],output_bits=pending['ell'],split=pending['split'])
            acc.emitted();pending=None
            reported=event.get('reported')
            if reported is not None:
                row['all_fields_match']=(reported['input_bits']==row['input_bits'] and reported['output_bits']==row['output_bits'] and reported['tail_bits']==acc.n)
        elif kind=='ABORT':acc.reset();pending=None
        elif kind!='RESET':raise ValueError('unknown event kind')
        row['bits_after']=acc.n;rows.append(row)
    return rows


def events_from_board_run(board_result_path):
    """Recover accepted append/decision/emit order from baseline raw TX and UART.

    This validates accumulator arithmetic/state only; use report_key_stream.py
    for full KEY/tag/PA/source verification. No PASS flags or expected lengths
    in result.json are used as predicted results.
    """
    path=Path(board_result_path);folder=path if path.is_dir() else path.parent
    uart=(folder/'uart.log').read_text();frames=json.loads((folder/'tx_manifest.json').read_text())
    events=[];code=None;revealed=0;session=-1
    for f in frames:
        raw=(folder/f['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=f['sha256'] or f'{zlib.crc32(raw):08x}'!=f['crc32']:raise ValueError('TX hash/CRC mismatch')
        w=list(struct.unpack('<'+'I'*(len(raw)//4),raw));seq=f['seq'];op=w[0]
        event=dict(session_id=max(session,0),event_id=seq)
        if op==10:code=w[1]&3;revealed=w[4]
        elif op==12:revealed+=w[1]
        elif op==61:
            session+=1;events.append(dict(session_id=session,event_id=seq,kind='RESET'))
        elif op==60 and re.search(fr'^QKD_STREAM_ADDED seq={seq} ',uart,re.M):
            if code is None:raise ValueError('append without source code')
            leak=[12,8,6,4][code]*128-307+revealed+64
            events.append(dict(event,kind='APPEND',block_id=w[1],nk=w[2:5],nt=w[5:8],mt=w[8:11],leak=leak,time_s=w[11]))
        elif op==62:
            m=re.search(fr'^QKD_STREAM_DECISION seq={seq} action=(\d+) bits=(\d+) ell=(\d+) split=(\d+) emit_bits=(\d+) seed_words=(\d+)',uart,re.M)
            if not m:raise ValueError('decision receipt missing')
            action,n,ell,split,emit,_=map(int,m.groups())
            events.append(dict(event,kind='DECIDE',time_s=w[1],reported=dict(action=['wait','emit','abort'][action],bits=n,ell=ell,split=bool(split),emit_bits=emit)))
        elif op==64:
            m=re.search(fr'^QKD_STREAM_EMITTED seq={seq} output_bits=(\d+) input_bits=(\d+) tail_bits=(\d+) passes=(\d+)',uart,re.M)
            if m:
                ell,n,tail,_=map(int,m.groups());events.append(dict(event,kind='EMIT',reported=dict(input_bits=n,output_bits=ell,tail_bits=tail)))
    return events


def validate_against_board_run(board_result_path,out_csv_path):
    events=events_from_board_run(board_result_path);rows=replay_events(events)
    decisions=[r for r in rows if r['kind']=='DECIDE'];emissions=[r for r in rows if r['kind']=='EMIT']
    fields=list(dict.fromkeys(k for r in rows for k in r));p=Path(out_csv_path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    return decisions,emissions


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',required=True,type=Path);ap.add_argument('--output',required=True,type=Path);args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    decisions,emissions=validate_against_board_run(args.run,args.output/'events.csv')
    accepted=bool(decisions) and all(r['all_fields_match'] for r in decisions+emissions)
    receipt=dict(scope='RETROSPECTIVE_RAW_EVENT_MODEL_REGRESSION_NOT_PROSPECTIVE_OR_SECURITY_PROOF',model_agreement=accepted,decisions=len(decisions),emissions=emissions,
                 source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output/'REPORT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if not accepted:raise SystemExit('MODEL_EVENT_MISMATCH')
    print('FINITE_KEY_RAW_EVENT_REGRESSION_PASS',len(decisions),'decisions',len(emissions),'emissions')
if __name__=='__main__':main()
