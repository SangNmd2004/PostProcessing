"""Merge explicitly selected CSV views with provenance; no aggregation/double counting."""
from pathlib import Path
import argparse,csv,hashlib,json
ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('files',nargs='+',type=Path)
args=ap.parse_args();fields=['record_type','source_csv'];rows=[];originals=[]
for path in args.files:
    if path.resolve()==args.out.resolve():ap.error('output must differ from every input')
    with path.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);columns=reader.fieldnames
        if not columns or any(k in columns for k in fields[:2]):ap.error('input already contains merge wrapper columns')
        values=list(reader)
    originals.append((path,columns,values))
    fields.extend(k for k in columns if k not in fields)
    rows.extend(dict(record_type=path.stem,source_csv=str(path),**r) for r in values)
args.out.parent.mkdir(parents=True,exist_ok=True)
with args.out.open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
with args.out.open(encoding='utf-8-sig',newline='') as f:merged=list(csv.DictReader(f))
for path,columns,values in originals:
    recovered=[{k:r[k] for k in columns} for r in merged if r['source_csv']==str(path)]
    assert recovered==values
proof={'rows':len(merged),'sha256':hashlib.sha256(args.out.read_bytes()).hexdigest(),
       'sources':{str(p):{'rows':len(v),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p,c,v in originals},
       'note':'Different views of the same trials; do not sum counts across record_type'}
args.out.with_suffix('.manifest.json').write_text(json.dumps(proof,indent=2)+'\n')
print('CSV_VIEWS_MERGE_VERIFY_PASS',len(merged),args.out)
