#!/usr/bin/env python3
"""Compare capability TX scheduling and transport times with endpoint receipt."""
import argparse,json,re,statistics
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('bridge',type=Path);parser.add_argument('endpoint',type=Path)
parser.add_argument('output',type=Path);args=parser.parse_args()
transmits=[tuple(map(int,row)) for row in re.findall(r'CAPTX,(\d+),(\d+),(\d+),(\d+),(-?\d+),(-?\d+)',args.bridge.read_text(errors='replace'))]
receives=[tuple(map(int,row)) for row in re.findall(r'CAPTEST_RX,(\d+),(\d+),(-?\d+)',args.endpoint.read_text(errors='replace'))]
fast=[row for row in transmits if row[4]==-3]
matched=[row for row in receives if row[2]==-3 and row[1] in {item[3] for item in fast}]
def summary(values):
 if not values:return None
 ordered=sorted(values)
 return {'minimum':min(values),'median':statistics.median(values),'mean':statistics.mean(values),'maximum':max(values),'p95':ordered[min(len(ordered)-1,int(.95*(len(ordered)-1)))]}
def cadence(rows,column):
 periods=[right[column]-left[column] for left,right in zip(rows,rows[1:])]
 return {'period_us':summary(periods),'mean_hz':1e6/statistics.mean(periods) if periods else None}
report={'fast_transmits':len(fast),'matched_receives':len(matched),'transport_errors':sum(row[5]!=0 for row in fast),
 'queue_to_submission_us':summary([row[1]-row[0] for row in fast]),
 'transport_call_us':summary([row[2]-row[1] for row in fast]),
 'queue_cadence':cadence(fast,0),'submission_cadence':cadence(fast,1),'receive_cadence':cadence(matched,0),
 'note':'Local clocks differ; only intervals are compared. Transport acceptance is not a radio acknowledgement.'}
args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
