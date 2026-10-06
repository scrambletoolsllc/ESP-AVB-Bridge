#!/usr/bin/env python3
"""Finite associated-station Signaling test; capture with dumpcap independently."""
import argparse,json,socket,time
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('output',type=Path)
parser.add_argument('--interface',required=True)
parser.add_argument('--destination',required=True)
parser.add_argument('--source-port',required=True)
parser.add_argument('--target-port',required=True)
args=parser.parse_args()
def decode(value,length):
    result=bytes.fromhex(value.replace(':',''))
    if len(result)!=length:parser.error('Incorrect address length')
    return result
destination=decode(args.destination,6)
source=decode(Path('/sys/class/net',args.interface,'address').read_text().strip(),6)
identity=decode(args.source_port,10);target=decode(args.target_port,10)
records=[];sequence=0
with socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(0x88f7)) as transport:
    transport.bind((args.interface,0))
    def send(interval,port,capability=False):
        global sequence
        sequence+=1
        message=bytearray(60 if capability else 58)
        message[:4]=bytes([0x1c,0x12,0,len(message)])
        message[20:30]=identity;message[30:32]=sequence.to_bytes(2,'big');message[33]=127
        message[34:44]=target;message[42:44]=port.to_bytes(2,'big')
        message[44:54]=bytes([0x80,0,0,12 if capability else 10,0,0x80,0xc2,0,0,4 if capability else 5])
        message[54]=interval&255
        sent=transport.send(destination+source+bytes.fromhex('88f7')+message)
        records.append({'epoch':time.time(),'sequence':sequence,'capability':capability,'interval':interval,'target_port':port,'bytes':sent})
        args.output.write_text(json.dumps(records,indent=2)+'\n')
    port=int.from_bytes(target[-2:],'big')
    send(0,port,True)
    try:
        time.sleep(3)
        for interval,address,duration in [(-3,port,6),(127,2,6),(127,port,3),(126,port,4)]:
            send(interval,address);time.sleep(duration)
    finally:
        send(126,port)
