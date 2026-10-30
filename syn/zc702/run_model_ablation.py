"""Paired model-only ablation: OMS/random -> OMS/GS -> NMS/GS.

Identical Alice/Bob and private puncture-bit RNG per trial; only position scheme
and check-node rule change. Not FPGA measurements or a secret-key-rate claim.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,hashlib,json,statistics,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'model'))
import ir_model as m
import eval_csv as ev
import puncture as pu
from experiment_metrics import wilson_interval
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--trials',type=int,default=1000);ap.add_argument('--qber',type=float,default=.03)
ap.add_argument('--code',choices=m.CODE_ORDER,default='r23');ap.add_argument('--seed-base',type=int,default=1600000)
args=ap.parse_args()
if args.trials<1 or not 0<=args.qber<=.2:ap.error('invalid trials/QBER')
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'reports'/('model_ablation_'+stamp);out.mkdir(parents=True)
base=m.load_codes(128)[args.code];gs=pu.order(args.code,base,128,307)
config={'scope':'MODEL_ONLY_NOT_BOARD','trials':args.trials,'code':args.code,'qber':args.qber,'seed_base':args.seed_base,
        'fixed':{'n':3072,'d':307,'lq':8,'iter_max':50,'PP':[1,2,16],'ET':12,'r0':0,'reveal_step':77},
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
          [ROOT/'model/eval_csv.py',ROOT/'model/ir_model.py',ROOT/'model/codes.json',ROOT/'model/punct.json',Path(__file__)]}}
(out/'frozen_config.json').write_text(json.dumps(config,indent=2)+'\n')
fields=['trial','configuration','seed','input_sha256','actual_qber','outcome','attempts','revealed','residual_errors','f_ir','f_with_64bit_tag','scope']
summaries={name:[] for name in ['OMS_random','OMS_GS','NMS_GS']}
with (out/'trials.csv').open('w',encoding='utf-8-sig',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    for trial in range(args.trials):
        rng=np.random.default_rng(args.seed_base+trial)
        alice=rng.integers(0,2,2765,dtype=np.int64);bob=alice^(rng.random(2765)<args.qber).astype(np.int64)
        input_hash=hashlib.sha256(alice.astype(np.uint8).tobytes()+bob.astype(np.uint8).tobytes()).hexdigest()
        actual=float((alice!=bob).mean());random_pos=np.random.default_rng(args.seed_base+20000000+trial).choice(3072,307,replace=False)
        for name,cn,pos in [('OMS_random','oms',random_pos),('OMS_GS','oms',gs),('NMS_GS','nms75',gs)]:
            m.CN_MODE=cn
            res=ev.run_block({'alice':alice,'bob':bob,'q_block':actual},base,args.seed_base+10000000+trial,pos_d=pos)
            outcome='SUCCESS' if res['success'] else 'WRONG_CODEWORD' if res['undetected'] else 'DISCARD'
            denom=2765*m.h2(actual)
            row={'trial':trial,'configuration':name,'seed':args.seed_base+trial,'input_sha256':input_hash,'actual_qber':actual,
                 'outcome':outcome,'attempts':res['attempts'],'revealed':res['revealed'],'residual_errors':res['resid'],
                 'f_ir':res['leak']/denom if res['success'] and denom else '',
                 'f_with_64bit_tag':(res['leak']+64)/denom if res['success'] and denom else '',
                 'scope':'MODEL_ONLY_NOT_BOARD'}
            writer.writerow(row);summaries[name].append(row)
        stream.flush()
        if (trial+1)%100==0:print('MODEL_ABLATION_PROGRESS',trial+1,'/',args.trials,flush=True)
summary=[]
for name,rows in summaries.items():
    ok=[r for r in rows if r['outcome']=='SUCCESS'];discard=sum(r['outcome']=='DISCARD' for r in rows)
    wrong=sum(r['outcome']=='WRONG_CODEWORD' for r in rows);errors=len(rows)-len(ok)
    summary.append({'configuration':name,'trials':len(rows),'success':len(ok),'discard':discard,'wrong_codeword':wrong,
                    'FER':errors/len(rows),'wilson_two_sided_95':str(wilson_interval(errors,len(rows))),
                    'mean_attempts_all':statistics.mean(r['attempts'] for r in rows),
                    'mean_f_ir_success_only':statistics.mean(r['f_ir'] for r in ok) if ok else '',
                    'mean_revealed_all':statistics.mean(r['revealed'] for r in rows),'scope':'MODEL_ONLY_NOT_BOARD'})
with (out/'summary.csv').open('w',encoding='utf-8-sig',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(summary[0]));writer.writeheader();writer.writerows(summary)
result={'complete':True,'hardware_capture':False,'scope':'MODEL_ONLY_NOT_BOARD','config':config,'summary':summary}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
lines=['# Ablation ghép cặp trên mô hình','',
       f"{args.trials} trial BSC QBER={args.qber:g}, code={args.code}. Mỗi trial có cùng Alice/Bob và RNG bit D; "
       'chỉ đổi vị trí puncture và quy tắc check node. Không có thí nghiệm board trong báo cáo này.','',
       '| Cấu hình | Thành công | Discard | Sai codeword | Attempts TB | f IR TB trên success |',
       '|---|---:|---:|---:|---:|---:|']
for r in summary:lines.append(f"| {r['configuration']} | {r['success']} | {r['discard']} | {r['wrong_codeword']} | {r['mean_attempts_all']:.3f} | {r['mean_f_ir_success_only']} |")
lines+=['','f IR không gồm tag; cột f_with_64bit_tag có riêng trong trials.csv. '
        'FER dùng discard hoặc codeword sai theo ground truth; không gọi sai codeword là verification đã bắt vì phép thử không chạy tag. '
        'Đây mới là ba tầng ablation; dynamic, switching và đa context phải thêm phép thử riêng. '
        'Không chuyển thời gian chạy Python thành thông lượng FPGA hoặc khóa bí mật.','']
(out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
print('MODEL_ABLATION_COMPLETE',out,flush=True)
