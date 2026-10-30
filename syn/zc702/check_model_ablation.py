"""Check paired trial accounting and quantify contrasts without rerunning models."""
from pathlib import Path
import argparse,collections,csv,hashlib,json,math,statistics
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('directory',type=Path);args=ap.parse_args();folder=args.directory
with (folder/'trials.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
config=json.loads((folder/'frozen_config.json').read_text());n=config['trials']
by_trial=collections.defaultdict(dict)
for row in rows:
    trial=int(row['trial']);name=row['configuration'];assert name not in by_trial[trial]
    by_trial[trial][name]=row
assert set(by_trial)==set(range(n))
for trial,group in by_trial.items():
    assert set(group)=={'OMS_random','OMS_GS','NMS_GS'}
    assert len({r['input_sha256'] for r in group.values()})==1
    assert len({r['seed'] for r in group.values()})==1
    assert all(r['scope']=='MODEL_ONLY_NOT_BOARD' for r in group.values())
common=[g for g in by_trial.values() if all(r['outcome']=='SUCCESS' for r in g.values())]
comparisons=[]
for a,b in [('OMS_random','OMS_GS'),('OMS_GS','NMS_GS')]:
    delta=[int(g[b]['attempts'])-int(g[a]['attempts']) for g in by_trial.values()]
    mean=statistics.mean(delta);half=1.959963984540054*statistics.stdev(delta)/math.sqrt(n)
    fdelta=[float(g[b]['f_ir'])-float(g[a]['f_ir']) for g in common]
    fixed=sum(g[a]['outcome']!='SUCCESS' and g[b]['outcome']=='SUCCESS' for g in by_trial.values())
    worsened=sum(g[a]['outcome']=='SUCCESS' and g[b]['outcome']!='SUCCESS' for g in by_trial.values())
    discord=fixed+worsened
    p=min(1.,2*sum(math.comb(discord,k) for k in range(min(fixed,worsened)+1))/2**discord) if discord else 1.
    comparisons.append({'from':a,'to':b,'paired_trials':n,'delta_mean_attempts':mean,'approx_95_lower':mean-half,
                        'approx_95_upper':mean+half,'common_success_trials':len(common),
                        'delta_mean_f_ir_common_success':statistics.mean(fdelta) if fdelta else '',
                        'failures_fixed':fixed,'failures_introduced':worsened,'mcnemar_exact_two_sided_p':p,
                        'scope':'MODEL_ONLY_NOT_BOARD'})
with (folder/'paired_contrasts.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(comparisons[0]));w.writeheader();w.writerows(comparisons)
proof={'hardware_capture':False,'paired_input_hashes_verified':True,'independent_inputs':n,'configuration_evaluations':len(rows),
       'common_success_trials':len(common),'paired_contrasts':comparisons,
       'files':{name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ['trials.csv','summary.csv','frozen_config.json']}}
(folder/'verified_evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
note=['# Kiểm tra thống kê ablation mô hình','',
      f'{n} bộ Alice/Bob ghép cặp đúng input hash; {len(rows)} lần đánh giá cấu hình. Không phải số đo board.',
      f'f được so thêm trên cùng {len(common)} trial mà cả ba cấu hình đều sửa đúng, tránh dùng các tập success khác nhau.','',
      'CI của chênh lệch attempts là xấp xỉ chuẩn cho trung bình ghép cặp. McNemar dùng kiểm định nhị thức chính xác trên các cặp discordant. '
      'Số fail rất ít nên chênh lệch FER quan sát được không đủ để kết luận cải thiện FER có ý nghĩa chỉ từ các số đếm này. '
      'Không coi f/attempts mô hình là throughput hoặc số đo FPGA.','']
(folder/'STATISTICAL_CHECK.md').write_text('\n'.join(note),encoding='utf-8')
print('PAIRED_MODEL_ABLATION_CHECK_PASS',n,'inputs',len(rows),'evaluations',folder)
