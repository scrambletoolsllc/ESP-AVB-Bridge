#!/usr/bin/env python3
"""Check per-association requests and interval isolation from an independent capture."""
import argparse,json,subprocess,statistics
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('capture',type=Path);parser.add_argument('output',type=Path)
args=parser.parse_args()
packets=json.loads(subprocess.check_output(['tshark','-r',str(args.capture),'-Y','ptp','-T','json','-x'],text=True,stderr=subprocess.DEVNULL))
requests={};replies=[];announces=[]
for packet in packets:
    layers=packet['_source']['layers'];wire=bytes.fromhex(layers['ptp_raw'][0]);epoch=float(layers['frame']['frame.time_epoch'])
    if len(wire)<34:continue
    record={'epoch':epoch,'sequence':int.from_bytes(wire[30:32],'big'),'source_port':wire[20:30].hex()}
    if wire[0]==0x1b:announces.append(record);continue
    if wire[0]!=0x1c or len(wire)<58:continue
    if wire[44:54] not in (bytes.fromhex('8000000c0080c2000004'),bytes.fromhex('8000000a0080c2000005')):continue
    record['interval']=int.from_bytes(wire[54:55],'big',signed=True)
    record['target_port']=wire[34:44].hex()
    if layers['eth']['eth.src']=='02:19:f8:16:a4:67':requests[record['sequence']]=record
    else:replies.append(record)
errors=[]
expected={1:(0,18),2:(-3,18),3:(127,2),4:(127,18),5:(126,18),6:(126,18)}
for sequence,(interval,port) in expected.items():
    row=requests.get(sequence)
    if not row or row['interval']!=interval or row['target_port']!=f'80f1b2fffed2caa9{port:04x}' or row['source_port']!='0219f8fffe16a4670001':
        errors.append(f'Request {sequence} missing or incorrect')
if not replies or not announces or any(row['source_port']!='80f1b2fffed2caa90012' for row in replies+announces):
    errors.append('Unexpected or absent association source identities')
phases=[]
if not errors:
    for sequence,label,expected_interval in [(2,'fast',-3),(3,'wrong target stop',-3),(4,'correct target stop',None),(5,'reset',0)]:
        start=requests[sequence]['epoch']+.25;end=requests[sequence+1]['epoch']
        rows=[row for row in replies if start<=row['epoch']<end]
        gaps=[b['epoch']-a['epoch'] for a,b in zip(rows,rows[1:])]
        phases.append({'phase':label,'count':len(rows),'seconds':end-start,'intervals':sorted(set(row['interval'] for row in rows)),
            'mean_rate_hz':(len(rows)-1)/(rows[-1]['epoch']-rows[0]['epoch']) if len(rows)>1 else None,
            'minimum_gap_ms':min(gaps)*1000 if gaps else None,'maximum_gap_ms':max(gaps)*1000 if gaps else None})
        if expected_interval is None:
            if rows:errors.append('Targeted stop continued after grace')
        elif len(rows)<(25 if expected_interval==-3 else 2) or any(row['interval']!=expected_interval for row in rows):
            errors.append(f'Unexpected behavior in {label}')
report={'captured_requests':requests,'announce_count':len(announces),'reply_count':len(replies),'phases':phases,'errors':errors,
        'functional_pass':not errors,'note':'Associated Linux control-plane peer, not a second FTM initiator. Grace 250 ms; timing conformance unproven.'}
args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if errors:raise SystemExit(1)
