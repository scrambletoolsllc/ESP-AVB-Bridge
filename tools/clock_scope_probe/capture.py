#!/usr/bin/env python3
"""Save paired, single-acquisition DHO804 waveforms for timing comparison."""
import argparse
import json
import socket
import struct
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('output', type=Path)
parser.add_argument('--count', type=int, default=5)
parser.add_argument('--scale', type=float, default=2e-6)
parser.add_argument('--direct', action='store_true',
                    help='Reach the on-link scope without using a gateway')
args = parser.parse_args()
if not 1 <= args.count <= 1000 or not 1e-8 <= args.scale <= .1:
    parser.error('count or scale outside diagnostic limits')
records = []
rejected_arming = []
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as scope:
    scope.settimeout(5)
    if args.direct:
        scope.setsockopt(socket.SOL_SOCKET, socket.SO_DONTROUTE, 1)
    scope.connect(('192.168.4.78', 5555))
    stream = scope.makefile('rb')
    def write(command):
        scope.sendall((command+'\n').encode())
    def query(command):
        write(command)
        return stream.readline().decode().strip()
    identity = query('*IDN?')
    if not identity.startswith('RIGOL TECHNOLOGIES,DHO804,'):
        raise RuntimeError(identity)
    write(':STOP')
    write(':TRIGger:MODE EDGE')
    write(':TRIGger:EDGE:SOURce CHANnel1')
    write(':TRIGger:EDGE:SLOPe POSitive')
    write(':TRIGger:EDGE:LEVel 1.65')
    write(':TRIGger:SWEep NORMal')
    write(':ACQuire:MDEPth 10000')
    write(f':TIMebase:MAIN:SCALe {args.scale}')
    write(':WAVeform:MODE RAW')
    write(':WAVeform:FORMat WORD')
    query('*OPC?')
    try:
        for index in range(args.count):
            for attempt in range(10):
                write(':SINGle')
                query('*OPC?')
                time.sleep(.05)
                deadline = time.monotonic()+5
                trigger_states = []
                while True:
                    status = query(':TRIGger:STATus?')
                    trigger_states.append(status)
                    if status == 'STOP':
                        break
                    if time.monotonic() > deadline:
                        raise TimeoutError('No new triggered acquisition')
                    time.sleep(.05)
                if 'WAIT' in trigger_states:
                    break
                rejected_arming.append({'index': index, 'attempt': attempt,
                    'host_time': time.time(), 'trigger_states': trigger_states})
                args.output.write_text(json.dumps({'identity': identity,
                    'records': records, 'rejected_arming': rejected_arming})+'\n')
            else:
                raise RuntimeError('No observed WAIT-to-STOP transition after ten attempts')
            record = {'index': index, 'host_time': time.time(), 'trigger_states': trigger_states, 'channels': {}}
            for channel in (1, 2):
                write(f':WAVeform:SOURce CHANnel{channel}')
                write(':WAVeform:STARt 1')
                write(':WAVeform:STOP 10000')
                preamble = query(':WAVeform:PREamble?')
                write(':WAVeform:DATA?')
                if stream.read(1) != b'#':
                    raise RuntimeError('Expected IEEE binary block')
                digits = int(stream.read(1))
                length = int(stream.read(digits))
                if length > 10000000:
                    raise RuntimeError('Unexpected waveform size')
                payload = stream.read(length)
                if len(payload) != length or stream.readline() not in (b'\n', b'\r\n'):
                    raise RuntimeError('Truncated waveform')
                if length != 20000 or int(preamble.split(',')[2]) != 10000:
                    raise RuntimeError(f'Incomplete waveform: {length} bytes, preamble {preamble}')
                record['channels'][str(channel)] = {'preamble': preamble, 'codes': list(struct.unpack('<'+'H'*(len(payload)//2), payload))}
            records.append(record)
            args.output.write_text(json.dumps({'identity': identity, 'records': records, 'rejected_arming': rejected_arming})+'\n')
        print(json.dumps({'captures': len(records), 'error': query(':SYSTem:ERRor?'), 'output': str(args.output)}))
    finally:
        write(':RUN')
