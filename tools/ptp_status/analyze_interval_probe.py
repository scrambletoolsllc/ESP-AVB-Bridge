#!/usr/bin/env python3
"""Evaluate finite associated-station interval probe from endpoint serial evidence."""
import argparse,json,re,statistics
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('log',type=Path)
parser.add_argument('output',type=Path)
args=parser.parse_args()
text=args.log.read_text(errors='replace')
received=[tuple(map(int,values)) for values in re.findall(r'CAPTEST_RX,(\d+),(\d+),(-?\d+)',text)]
sent=[tuple(map(int,values)) for values in re.findall(r'CAPTEST_TX,(\d+),(\d+),(-?\d+),(\d+),(-?\d+)',text)]
report={'complete':'CAPTEST_DONE' in text,'aborted':'CAPTEST_ABORT' in text,'requests':len(sent),'stages':[],'errors':[]}
if len(sent)!=7 or not report['complete'] or report['aborted']:
 report['errors'].append('Finite request sequence incomplete or association changed')
expected_requests=[(1,1,0),(2,-3,0),(3,127,1),(4,-4,0),(5,127,0),(6,126,0),(7,126,0)]
if [(item[1],item[2],item[3]) for item in sent]!=expected_requests:
 report['errors'].append('Unexpected request order or contents')
initial=[item for item in received if sent and item[0]<sent[0][0]]
initial_periods=[(right[0]-left[0])/1e6 for left,right in zip(initial,initial[1:])]
report['initial_received']=len(initial)
if len(initial_periods)<10 or any(item[2]!=0 for item in initial) or not .75<=statistics.median(initial_periods)<=1.25:
 report['errors'].append('Initial one-second cadence not established')
for index,record in enumerate(sent[:-1]):
 start,sequence,requested,wrong,status=record
 end=sent[index+1][0]
 samples=[item for item in received if start<=item[0]<end]
 periods=[(right[0]-left[0])/1e6 for left,right in zip(samples,samples[1:])]
 row={'sequence':sequence,'requested':requested,'wrong_identity':bool(wrong),'transport_status':status,
      'received':len(samples),'advertised':sorted(set(item[2] for item in samples)),
      'periods_s':periods,'mean_rate_hz':1/statistics.mean(periods) if periods else None,
      'sequence_gaps':sum(((right[1]-left[1]) & 65535)!=1 for left,right in zip(samples,samples[1:])),
      'first_delay_s':(samples[0][0]-start)/1e6 if samples else None}
 errors=[]
 if status:errors.append('Request transport failure')
 expected=1 if sequence==1 else -3 if sequence in (2,3,4) else 0
 if sequence==5:
  late=[item for item in samples if item[0]>start+250000]
  if late:errors.append('Capability messages continued after stop grace period')
 elif not samples or row['advertised']!=[expected]:errors.append('Missing or unexpected advertised interval')
 elif sequence==1:
  if len(periods)<9 or not all(.75<=period<=1.25 for period in periods[:8]) or periods[8]<1.75:
   errors.append('Nine-notice slowdown timing not observed')
 elif sequence in (2,3,4):
  if len(periods)<8 or not .09<=statistics.median(periods)<=.18:
   errors.append('125 ms cadence not observed')
 elif sequence==6:
  if len(periods)<3 or not all(.75<=period<=1.25 for period in periods):errors.append('Initial cadence not restored')
 row['errors']=errors;report['stages'].append(row)
 report['errors'].extend(f'Stage {sequence}: {error}' for error in errors)
report['functional_pass']=not report['errors']
report['timing_conformance']='Unproven; arrival jitter and mean rate are reported without a normative tolerance claim'
args.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
