#!/usr/bin/env python3
"""Convert captured wired probe requests/replies to the common interval checker input."""
import argparse,json,subprocess
from pathlib import Path
from decimal import Decimal
parser=argparse.ArgumentParser();parser.add_argument('capture',type=Path)
parser.add_argument('requests',type=Path);parser.add_argument('output',type=Path)
args=parser.parse_args();request_data=json.loads(args.requests.read_text())
records={row['sequence']:row for row in request_data['records']}
packets=json.loads(subprocess.check_output(['tshark','-r',str(args.capture),'-Y',
 'ptp.v2.messagetype==12','-T','json','-x'],text=True,stderr=subprocess.DEVNULL))
lines=[];seen=set();request_sources=set();reply_interfaces=set()
for packet in packets:
 layers=packet['_source']['layers'];wire=bytes.fromhex(layers['ptp_raw'][0])
 if len(wire)<58 or wire[0]!=0x1c or wire[44:54] not in (bytes.fromhex('8000000c0080c2000004'),bytes.fromhex('8000000a0080c2000005')):continue
 frame=layers['frame'];epoch=int(Decimal(frame['frame.time_epoch'])*1000000)
 sequence=int.from_bytes(wire[30:32],'big');interval=int.from_bytes(wire[54:55],'big',signed=True)
 ethernet=layers['eth'];source=ethernet['eth.src'];destination=ethernet['eth.dst']
 if source==request_data['destination'] and wire[53]==4:
  lines.append(f'CAPTEST_RX,{epoch},{sequence},{interval}')
  reply_interfaces.add(frame['frame.interface_id'])
 elif destination==request_data['destination'] and wire[53]==5 and sequence in records:
  row=records[sequence]
  expected_peer=bytearray.fromhex(request_data['claimed_peer_port'].replace(':',''))
  if row['wrong_identity']:expected_peer[9]^=0x40
  if wire[20:30]!=expected_peer or interval!=row['requested']:raise RuntimeError('Unexpected captured request')
  if sequence in seen:raise RuntimeError('Duplicate request capture, select the bridge ingress tap')
  seen.add(sequence);request_sources.add(source)
  lines.append(f"CAPTEST_TX,{epoch},{sequence},{interval},{int(row['wrong_identity'])},0")
if seen==set(range(1,8)):lines.append('CAPTEST_DONE')
args.output.write_text('\n'.join(lines)+'\n')
print(json.dumps({'captured_requests':sorted(seen),'ethernet_request_sources':sorted(request_sources),
                 'reply_interfaces':sorted(reply_interfaces),'note':'Synthetic bridge-unicast test; peer identity is supplied by the bench'},indent=2))
