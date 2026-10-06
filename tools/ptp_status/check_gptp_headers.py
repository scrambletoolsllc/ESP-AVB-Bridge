#!/usr/bin/env python3
"""Inspect transmitted header/reserved bytes independently of firmware helpers."""
from pathlib import Path
import argparse,collections,json,subprocess
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('capture',type=Path);parser.add_argument('output',type=Path)
parser.add_argument('--source',default='80:f1:b2:d2:ca:a9')
args=parser.parse_args()
packets=json.loads(subprocess.check_output(['tshark','-r',str(args.capture),'-Y',
 f'eth.src=={args.source} && ptp','-T','json','-x'],stderr=subprocess.DEVNULL,text=True))
counts=collections.Counter();errors=[];interfaces=set()
for packet in packets:
 layers=packet['_source']['layers'];wire=bytes.fromhex(layers['ptp_raw'][0]);frame=layers['frame']
 if wire[0]>>4!=1:continue
 kind=wire[0]&15;counts[kind]+=1
 interfaces.add(frame['frame.interface_id_tree']['frame.interface_name'])
 failures=[]
 if wire[1]!=0x12:failures.append('version')
 if wire[5]!=0:failures.append('minor_sdo')
 if wire[16:20]!=bytes(4):failures.append('message_specific')
 if wire[32]!=0:failures.append('control')
 if kind==12 and wire[33]!=127:failures.append('signaling_interval')
 if kind==2 and (len(wire)<54 or wire[34:54]!=bytes(20)):failures.append('request_reserved')
 if kind==11 and (len(wire)<64 or wire[34:44]!=bytes(10) or wire[46]):failures.append('announce_reserved')
 if kind==0 and wire[6]&2 and (len(wire)<44 or wire[34:44]!=bytes(10)):failures.append('sync_reserved')
 if failures:errors.append({'frame':frame['frame.number'],'type':kind,'failed':failures})
summary={'message_counts':dict(counts),'errors':errors,'interfaces':sorted(interfaces),
 'scope':'Captured source only; absent message types are not validated.'}
args.output.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
raise SystemExit(bool(errors or not counts))
