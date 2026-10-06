#!/usr/bin/env python3
"""Validate Announce interval requests from independent associated-station capture."""
import argparse,json,subprocess
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('capture',type=Path);parser.add_argument('output',type=Path)
args=parser.parse_args()
packets=json.loads(subprocess.check_output(['tshark','-r',str(args.capture),'-Y','ptp','-T','json','-x'],text=True,stderr=subprocess.DEVNULL))
requests={};announces=[];errors=[]
peer='02:19:f8:16:a4:67';source_port='80f1b2fffed2caa90012'
for packet in packets:
    layers=packet['_source']['layers'];wire=bytes.fromhex(layers['ptp_raw'][0]);epoch=float(layers['frame']['frame.time_epoch'])
    if len(wire)<34:continue
    row={'epoch':epoch,'sequence':int.from_bytes(wire[30:32],'big'),'source_port':wire[20:30].hex()}
    if wire[0]==0x1b:
        row['interval']=int.from_bytes(wire[33:34],'big',signed=True)
        row['btc']=wire[53:61].hex();announces.append(row)
    elif wire[0]==0x1c and len(wire)>=60 and layers['eth']['eth.src']==peer:
        row.update(subtype=wire[53],interval=int.from_bytes(wire[54:55] if wire[53]==4 else wire[56:57],'big',signed=True),target_port=wire[34:44].hex())
        if wire[44:53]!=bytes.fromhex('0003000c0080c20000'):errors.append('Unexpected request TLV')
        if wire[53]==2 and wire[54:56]!=bytes([128,128]):errors.append('Request changes unrelated intervals')
        requests[row['sequence']]=row
expected={1:(4,0,18),2:(2,1,18),3:(2,127,2),4:(2,127,18),5:(2,-128,18),6:(2,126,18),7:(2,-3,18),8:(2,126,18)}
for sequence,(subtype,interval,port) in expected.items():
    row=requests.get(sequence)
    if not row or row['subtype']!=subtype or row['interval']!=interval or row['target_port']!=f'80f1b2fffed2caa9{port:04x}' or row['source_port']!='0219f8fffe16a4670001':errors.append(f'Incorrect/missing request {sequence}')
if not announces or any(row['source_port']!=source_port or row['btc']!='0001f2fffeff3b14' for row in announces):errors.append('Announce identity/BTC mismatch or absent')
if any((later['sequence']-earlier['sequence'])%65536!=1 for earlier,later in zip(announces,announces[1:])):errors.append('Logical Announce sequence not contiguous in capture')
phases=[]
if len(requests)!=8:errors.append("Unexpected number of captured requests")
if len(requests)==8:
    for sequence,label,interval in [(2,'slowdown',1),(3,'wrong target stop',1),(4,'stop',None),(5,'unchanged stop',None),(6,'reset',0),(7,'closest supported faster',0)]:
        start=requests[sequence]['epoch']+.25;end=requests[sequence+1]['epoch']
        rows=[row for row in announces if start<=row['epoch']<end]
        phases.append({'phase':label,'count':len(rows),'intervals':sorted({row['interval'] for row in rows}),'gaps_s':[later['epoch']-earlier['epoch'] for earlier,later in zip(rows,rows[1:])]})
        if interval is None:
            if rows:errors.append(f'Announce continued during {label}')
        elif len(rows)<(2 if interval==1 else 3) or any(row['interval']!=interval for row in rows):errors.append(f'Unexpected Announce behavior in {label}')
    # Include the first new-interval frame, without discarding it as transition grace.
    slow=[row for row in announces if requests[2]['epoch']<=row['epoch']<requests[3]['epoch'] and row['interval']==1]
    gaps=[later['epoch']-earlier['epoch'] for earlier,later in zip(slow,slow[1:])]
    if len(slow)<6 or any(not .8<=gap<=1.3 for gap in gaps[:2]) or any(not 1.7<=gap<=2.3 for gap in gaps[2:]):errors.append('Did not observe three old-rate announcements followed by slower cadence')
else:slow=[];gaps=[]
report={'captured_requests':requests,'announces':announces,'phases':phases,'slowdown_gaps_s':gaps,'errors':errors,'functional_pass':not errors,'note':'Finite bench cadence bounds, not full timing conformance. Contiguous sequences also depend on delivery and capture completeness. Linux station is not an FTM initiator.'}
args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({key:value for key,value in report.items() if key not in ('announces','captured_requests')},indent=2))
if errors:raise SystemExit(1)
