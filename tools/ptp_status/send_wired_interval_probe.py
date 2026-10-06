#!/usr/bin/env python3
"""Finite unicast interval injection; capture independently with dumpcap."""
import argparse,json,socket,time
from datetime import datetime,timezone
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('output',type=Path)
parser.add_argument('--interface',default='nic1')
parser.add_argument('--destination',required=True)
parser.add_argument('--target-port',required=True,help='Ten-byte bridge PTP identity, hex')
parser.add_argument('--peer-port',required=True,help='Ten-byte observed peer PTP identity, hex')
args=parser.parse_args()
def decode(text,length):
 value=bytes.fromhex(text.replace(':',''))
 if len(value)!=length:parser.error(f'Expected {length} bytes: {text}')
 return value
destination=decode(args.destination,6)
if destination[0]&1:parser.error('Diagnostic requires a unicast destination')
target=decode(args.target_port,10);peer=decode(args.peer_port,10)
source=decode(Path(f'/sys/class/net/{args.interface}/address').read_text().strip(),6)
records=[]
with socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(0x88f7)) as transport:
 transport.bind((args.interface,0))
 def send(sequence,interval,wrong=False):
  message=bytearray(58);message[0:4]=bytes([0x1c,0x12,0,58])
  message[20:30]=peer
  if wrong:message[29]^=0x40
  message[30:32]=sequence.to_bytes(2,'big');message[33]=127;message[34:44]=target
  message[44:58]=bytes([0x80,0,0,10,0,0x80,0xc2,0,0,5,interval&255,0,0,0])
  frame=destination+source+bytes.fromhex('88f7')+message
  before=time.time();length=transport.send(frame)
  records.append({'utc':datetime.now(timezone.utc).isoformat(),'epoch':before,'sequence':sequence,
                  'requested':interval,'wrong_identity':wrong,'sent_bytes':length})
  args.output.write_text(json.dumps({'note':'Synthetic bridge-unicast requests, not emitted by the observed peer',
       'interface':args.interface,'destination':args.destination,'target_port':args.target_port,
       'claimed_peer_port':args.peer_port,'records':records},indent=2)+'\n')
 time.sleep(15)
 try:
  for sequence,(interval,wrong,delay) in enumerate([(1,False,16),(-3,False,3),(127,True,2),
       (-4,False,2),(127,False,3),(126,False,5)],1):
   send(sequence,interval,wrong);time.sleep(delay)
 finally:
  send(7,126)
