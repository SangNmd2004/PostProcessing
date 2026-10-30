"""Merge the three report views into one CSV while preserving record types."""
from pathlib import Path
import argparse
import csv
import hashlib
import json

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory',type=Path)
args=parser.parse_args()
directory=args.directory.resolve()
inputs=[('block','chi_tiet_block.csv'),('summary','tong_hop.csv'),('source_row_coverage','doi_chieu_tung_dong_csv.csv')]
fields=['record_type','source_csv'];records=[];counts={};hashes={}
for kind,name in inputs:
    path=directory/name
    with path.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        assert reader.fieldnames and 'record_type' not in reader.fieldnames and 'source_csv' not in reader.fieldnames
        fields.extend(f for f in reader.fieldnames if f not in fields)
        rows=list(reader)
    counts[kind]=len(rows)
    hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    records.extend(dict(record_type=kind,source_csv=name,**row) for row in rows)
output=directory/'bao_cao_gop.csv'
with output.open('w',encoding='utf-8-sig',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=fields)
    writer.writeheader();writer.writerows(records)
with output.open(encoding='utf-8-sig',newline='') as stream:
    reread=list(csv.DictReader(stream))
assert len(reread)==len(records)
for kind,name in inputs:
    with (directory/name).open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream);columns=reader.fieldnames;original=list(reader)
    recovered=[{k:row[k] for k in columns} for row in reread if row['record_type']==kind]
    assert recovered==original, 'Merged data differs: '+name
manifest={'data_rows':len(records),'columns':len(fields),'rows_by_record_type':counts,
          'inputs_sha256':hashes,'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
          'note':'Views overlap; do not sum rows across record types. Blank columns are not applicable.'}
(directory/'bao_cao_gop_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('MERGED_CSV_VERIFY_PASS',len(records),'rows;',len(fields),'columns;',output)
