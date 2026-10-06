#!/usr/bin/env python3
"""Verify optional-path omission/restoration without losing the selected clock."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory',type=Path)
parser.add_argument('--date',default='2026-09-25')
args=parser.parse_args();root=args.directory

def epoch(clock):
 return datetime.fromisoformat(args.date+'T'+clock).replace(tzinfo=timezone.utc).timestamp()
phases=[]
for line in (root/'host-announce-path-probe-live.log').read_text().splitlines():
 match=re.search(r'^\[(\d\d:\d\d:\d\d)\].*ANNPATH,1,(\d+)',line)
 if match:phases.append({'phase':int(match[2]),'epoch':epoch(match[1])})
assert [row['phase'] for row in phases]==[0,1,2],phases
omitted,restored=phases[1]['epoch'],phases[2]['epoch']
packets=json.loads(subprocess.check_output(['tshark','-r',str(root/'announce-path-peer.pcapng'),'-Y','ptp','-T','json','-x'],stderr=subprocess.DEVNULL))
announces=[];errors=[]
for packet in packets:
 layers=packet['_source']['layers'];wire=bytes.fromhex(layers['ptp_raw'][0])
 if wire[0]!=0x1b:continue
 announces.append({'epoch':float(layers['frame']['frame.time_epoch']),'length':len(wire),'source':wire[20:30].hex(),'btc':wire[53:61].hex(),'sequence':int.from_bytes(wire[30:32],'big')})
if not announces or len({row['source'] for row in announces})!=1 or any(row['source'][:16]!='80f1b2fffed2caa9' or row['btc']!='0001f2fffeff3b14' for row in announces):errors.append('Unexpected Announce identity')
if any((later['sequence']-earlier['sequence'])%65536!=1 for earlier,later in zip(announces,announces[1:])):errors.append('Announce sequence discontinuity')
management=json.loads((root/'announce-path-management.json').read_text())
full_path=['0001f2fffeff3b14','80f1b2fffed2caa9','fc012cfffefdfe80']
changes=[]
for row in announces:
 if not changes or row['length']!=changes[-1]['length']:changes.append(row)
if [row['length'] for row in changes]!=[84,64,84]:errors.append('Unexpected wire path transitions')
assert len(changes)==3,changes
wire_omitted,wire_restored=changes[1]['epoch'],changes[2]['epoch']
if abs(wire_omitted-omitted)>1 or abs(wire_restored-restored)>1:errors.append('Wire transition does not match diagnostic phase')
unknown_reply=next((row for row in management if row.get('path')==[] and datetime.fromisoformat(row['utc']).timestamp()>=wire_omitted),None)
restored_reply=next((row for row in management if row.get('path')==full_path and datetime.fromisoformat(row['utc']).timestamp()>=wire_restored),None)
latencies={}
for label,row,changed in [('omission',unknown_reply,wire_omitted),('restoration',restored_reply,wire_restored)]:
 latency=datetime.fromisoformat(row['utc']).timestamp()-changed if row else None
 latencies[label]=latency
 # AVB caches PTP status every 3000 ms; allow one query cycle beyond that.
 if latency is None or not 0<=latency<=3.5:errors.append(f'Management update outside cache cadence: {label}')
windows=[]
for label,start,end,length,path in [('known before',wire_omitted-5,wire_omitted-1,84,full_path),('unknown',wire_omitted+3.5,wire_restored-.5,64,[]),('restored',wire_restored+3.5,wire_restored+12,84,full_path)]:
 messages=[row for row in announces if start<=row['epoch']<end]
 replies=[row for row in management if start<=datetime.fromisoformat(row['utc']).timestamp()<end]
 good=[row for row in replies if row.get('avb_info_status')==0 and row.get('path_status')==0]
 if len(messages)<2 or any(row['length']!=length for row in messages):errors.append(f'Announce length mismatch: {label}')
 if not good or any(row.get('btc')!='0001f2fffeff3b14' or row.get('path')!=path for row in good):errors.append(f'Management source/path mismatch: {label}')
 windows.append({'phase':label,'announces':len(messages),'lengths':sorted({row['length'] for row in messages}),'queries':len(replies),'both_ok':len(good),'expected_path':path})
ready=[]
for line in (root/'endpoint-announce-qualification-live.log').read_text().splitlines():
 match=re.search(r'^\[(\d\d:\d\d:\d\d)\].*FTMREADY,([01]),(\d+)',line)
 if match:ready.append({'epoch':epoch(match[1]),'ready':int(match[2]),'generation':int(match[3])})
if not any(row['ready'] and row['epoch']<omitted for row in ready):errors.append('Endpoint not ready before omission')
if any(not row['ready'] and omitted<=row['epoch']<=restored+10 for row in ready):errors.append('Readiness lost across omission/restoration')
report={'phases':phases,'wire_transitions':changes,'management_update_latency_s':latencies,'windows':windows,'readiness':ready,'management_total':len(management),'avb_timeouts':sum(bool(row.get('avb_info_timeout')) for row in management),'path_timeouts':sum(bool(row.get('path_timeout')) for row in management),'announces_total':len(announces),'errors':errors,'functional_pass':not errors,'note':'Wire evidence is received at an associated control peer. Serial phase times have one-second resolution; management uses the existing 3-second status cache. Native tests separately exercise missing-path ingress and actual relay construction. Not full role/BTCA or normative conformance proof.'}
(root/'announce-path-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if errors:raise SystemExit(1)
