#!/usr/bin/env python3
import sys,subprocess,json,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ftm_raw_probe'))
from analyze import parse
from model import RelativeModel
reports=parse(Path(sys.argv[1]).read_text(errors='replace'))
lines=[]
for report in reports:
    lines.append(f'{report.generation} {report.attempt} {report.peer} {report.before_us} {report.mac_us} {report.after_us} {len(report.entries)} {report.dropped}')
    lines.extend(f'{entry.t1} {entry.t2} {entry.t3} {entry.t4} {entry.rtt}' for entry in report.entries)
output=subprocess.check_output([sys.argv[2]],input='\n'.join(lines)+'\n',text=True)
rows=[line.split(',') for line in output.splitlines()]
assert len(rows)==len(reports)
model=RelativeModel()
differences=[]
for report,row in zip(reports,rows):
    result=model.observe(report)
    assert int(row[0])==report.attempt and int(row[1])==0,row
    assert int(row[2])==result['entries'] and int(row[8])==result['responder_wraps']
    errors=result['predicted_errors_ns']
    assert bool(int(row[3]))==bool(errors)
    if errors:
        differences.append(abs(float(row[5])-statistics.median(errors)*1000))
        differences.append(abs(float(row[6])-max(map(abs,errors))*1000))
        assert abs(float(row[4])-result['remote_rate_ppm'])<1e-8
assert max(differences,default=0)<.01
print(json.dumps(dict(reports=len(rows),maximum_prediction_difference_ps=max(differences,default=0)),indent=2))
