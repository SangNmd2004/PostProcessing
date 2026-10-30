"""Prepare file-based UART vectors from every CSV bit and controlled QBER sweeps.

No physical hardware is used here. JSON distinguishes model decoding outcome from
future hardware comparison. Tail blocks overlap to cover all rows without padding.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import struct
import sys
import zlib
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'model'))
import eval_csv as ev
import ir_model as m
import puncture as pu

def encode(cfg, cfg2, pre, expected, counts, errcnt, ch, syn, rev, key):
    words = [cfg, cfg2, pre, len(expected), len(syn), errcnt, len(rev)]
    words += list(expected) + list(counts) + list(ch) + list(syn) + list(rev)
    for v in key:
        words += [int(v) & 0xffffffff, int(v) >> 32]
    return struct.pack('<'+'I'*len(words), *map(int, words))

def hexes(directory, name):
    return [int(x,16) for x in (directory/name).read_text().split()]

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--csv', type=Path, default=ROOT/'Test/bb84_key_test_Sim_20260618_002028.csv')
    ap.add_argument('--out', type=Path, default=ROOT/'build/zc702/uart_campaign')
    ap.add_argument('--repeats', type=int, default=10)
    ap.add_argument('--native-only', action='store_true', help='Only original CSV bits with all four codes; no baseline or injected errors')
    ap.add_argument('--cn', choices=['oms','nms75'], default='oms')
    ap.add_argument('--puncturing', choices=['random','gs'], default='random')
    args = ap.parse_args()
    if args.repeats < 1:
        ap.error('--repeats must be positive')
    args.out.mkdir(parents=True, exist_ok=False)
    records = []
    def save(payload, metadata):
        seq = len(records)
        path = args.out/f'{seq:04d}.bin'
        path.write_bytes(payload)
        records.append(dict(seq=seq, file=path.name, bytes=len(payload),
                            sha256=hashlib.sha256(payload).hexdigest(),
                            crc32=f'{zlib.crc32(payload):08x}', **metadata))
        (args.out/'campaign.json').write_text(json.dumps({'complete':False,'records':records},indent=2)+'\n')
        print(f"PREPARED {seq} {metadata['source']} {metadata.get('group','')} {metadata.get('code','')} "
              f"q={metadata.get('qber_pct','')} outcome={metadata['model_outcome']}",flush=True)
    data = ROOT/'data/tb'
    for b in range(0 if args.native_only else hexes(data,'nblk.hex')[0]):
        meta = hexes(data,f'blk_{b}.hex'); cfg,cfg2,pre,a = meta[:4]
        counts=meta[5:4+2*a:2]
        rev=hexes(data,f'rev_{b}.hex')[:pre+sum(counts)]
        expected=meta[4:4+2*a:2]
        save(encode(cfg,cfg2,pre,expected,counts,meta[-1],hexes(data,f'ch_{b}.hex'),
                    hexes(data,f'syn_{b}.hex'),rev,hexes(data,f'key_{b}.hex')),
             {'source':'baseline','block':b,'model_outcome':'CONVERGED' if expected[-1]>>31 else 'DISCARD',
              'attempts':a,'expected_errcnt':meta[-1]})
    rows=list(csv.DictReader(args.csv.open(encoding='utf-8-sig',newline='')))
    groups={}
    for row in sorted(rows,key=lambda r:(int(r['turb_level']),int(r['test_id']))):
        a,b=row['key_alice'].strip(),row['key_bob'].strip()
        if not a or len(a)!=len(b) or len(a)!=int(row['key_length']) or set(a+b)-set('01'):
            raise ValueError('invalid CSV bit string: '+row['test_id'])
        errors=sum(x!=y for x,y in zip(a,b))
        if errors!=int(row['n_mismatch_bits']) or abs(100*errors/len(a)-float(row['QBER_pct']))>0.00011:
            raise ValueError('CSV QBER/error mismatch: '+row['test_id'])
        g=groups.setdefault(row['turb_name'],{'a':'','b':'','ids':[], 'rows':[]})
        g['rows'].append({'test_id':int(row['test_id']), 'start':len(g['a']), 'bits':len(a),
                          'errors':errors, 'qber_pct':100*errors/len(a)})
        g['a']+=a;g['b']+=b;g['ids'].append(int(row['test_id']))
    codes=m.load_codes(128)
    def evaluate(blk, code, seed, metadata):
        m.CN_MODE=args.cn
        positions=pu.order(code,codes[code],128,ev.D) if args.puncturing=='gs' else None
        result=ev.run_block(blk,codes[code],seed,pos_d=positions)
        sym=result['sym'];sbits=result['syn'].reshape(-1)
        ch=[sum(int(sym[t*16+k])<<(2*k) for k in range(16)) for t in range(ev.N//16)]
        syn=[sum(int(sbits[t*32+k])<<k for k in range(32)) for t in range(len(sbits)//32)]
        cfg=m.CODE_ORDER.index(code)|(m.LQ_DEFAULT<<2)|(ev.ITER_MAX<<8)|(ev.PP[0]<<16)|(ev.PP[1]<<18)|(ev.PP[2]<<20)
        exp=[(int(t['conv'])<<31)|(t['pp']<<28)|(t['usc']<<16)|t['iters'] for t in result['trace']]
        counts=[t['nrev'] for t in result['trace']]
        key=[sum(int(result['hard'][w*64+i])<<i for i in range(64)) for w in range(48)]
        save(encode(cfg,ev.ET | (32 if args.cn=='nms75' else 0),0,exp,counts,result['errcnt'],ch,syn,result['revs'],key),
             dict(metadata,code=code,seed=seed,cn=args.cn,puncturing=args.puncturing,qber_pct=100*blk['q_block'],
                  model_outcome='SUCCESS' if result['success'] else 'UNDETECTED' if result['undetected'] else 'DISCARD',
                  residual_errors=result['resid'],attempts=result['attempts'],revealed=result['revealed'],
                  expected_errcnt=result['errcnt']))
    coverage=[]
    for name,g in groups.items():
        a=np.frombuffer(g['a'].encode(),dtype=np.uint8).astype(np.int64)-48
        b=np.frombuffer(g['b'].encode(),dtype=np.uint8).astype(np.int64)-48
        if len(a)<ev.NKEY: raise ValueError('insufficient group bits')
        starts=list(range(0,len(a)-ev.NKEY+1,ev.NKEY))
        if starts[-1]!=len(a)-ev.NKEY:starts.append(len(a)-ev.NKEY)
        coverage.append({'group':name,'unique_bits':len(a),'test_ids':g['ids'],'rows':g['rows'],'block_starts':starts,
                         'tail_overlaps':starts[-1]%ev.NKEY!=0})
        for idx,start in enumerate(starts):
            aa,bb=a[start:start+ev.NKEY],b[start:start+ev.NKEY]
            blk={'alice':aa,'bob':bb,'q_block':float((aa!=bb).mean())}
            input_rows=[]
            for row in g['rows']:
                lo=max(start,row['start']); hi=min(start+ev.NKEY,row['start']+row['bits'])
                if hi>lo:
                    input_rows.append({'test_id':row['test_id'],'row_bit_start':lo-row['start'],
                                       'block_bit_start':lo-start,'bits':hi-lo})
            for code in m.CODE_ORDER:
                evaluate(blk,code,1000+idx,{'source':'csv_native','group':name,'block':idx,'bit_start':start,
                                         'input_rows':input_rows})
    alice=np.frombuffer(''.join(g['a'] for g in groups.values()).encode(),dtype=np.uint8).astype(np.int64)-48
    for target in ([] if args.native_only else [0,0.5,1,2,3,4,5,6,7,8,10,12,15,18,20]):
        for rep in range(args.repeats):
            seed=50000+int(target*100)*100+rep
            rng=np.random.default_rng(seed)
            start=(rep*ev.NKEY)%(len(alice)-ev.NKEY+1)
            a=alice[start:start+ev.NKEY].copy();b=a.copy()
            flips=int(round(target/100*ev.NKEY))
            b[rng.choice(ev.NKEY,flips,replace=False)]^=1
            blk={'alice':a,'bob':b,'q_block':flips/ev.NKEY}
            evaluate(blk,ev.pick_code(target/100),seed,
                     {'source':'controlled_qber','target_qber_pct':target,'repeat':rep,'alice_start':start})
    campaign={'complete':True,'csv':str(args.csv.resolve()),'csv_sha256':hashlib.sha256(args.csv.read_bytes()).hexdigest(),
              'n':ev.N,'key_bits':ev.NKEY,'punctured_bits':ev.D,'coverage':coverage,'records':records,
              'native_only':args.native_only,
              'decoder':args.cn,'puncturing':args.puncturing,
              'notes':'Native tails overlap; controlled Bob is synthetic. Model success is not a hardware receipt.'}
    (args.out/'campaign.json').write_text(json.dumps(campaign,indent=2)+'\n',encoding='utf-8')
    print('UART_CAMPAIGN_PREPARED',len(records),args.out,flush=True)

if __name__=='__main__':main()
