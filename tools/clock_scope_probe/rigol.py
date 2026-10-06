#!/usr/bin/env python3
"""Fixed bench scope setup and readback for clock pulse diagnostics."""
import argparse
import json
import socket

parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['status', 'compensation', 'timing'])
args = parser.parse_args()
with socket.create_connection(('192.168.4.78', 5555), timeout=5) as scope:
    scope.settimeout(5)
    stream = scope.makefile('rb')
    def write(command):
        scope.sendall((command+'\n').encode())
    def query(command):
        write(command)
        return stream.readline().decode().strip()
    identity = query('*IDN?')
    if not identity.startswith('RIGOL TECHNOLOGIES,DHO804,'):
        raise RuntimeError('Unexpected instrument: '+identity)
    if args.action != 'status':
        for channel in (1, 2):
            for setting in ['DISPlay ON', 'PROBe 10', 'COUPling DC', 'SCALe 1', 'OFFSet 0', 'BWLimit OFF']:
                write(f':CHANnel{channel}:{setting}')
        for channel in (3, 4):
            write(f':CHANnel{channel}:DISPlay OFF')
        for command in [':ACQuire:TYPE NORMal', ':TRIGger:MODE EDGE',
                        ':TRIGger:EDGE:SOURce CHANnel1', ':TRIGger:EDGE:SLOPe POSitive',
                        ':TRIGger:EDGE:LEVel 1.6', ':TIMebase:MAIN:OFFSet 0']:
            write(command)
        write(':TIMebase:MAIN:SCALe '+('0.0002' if args.action == 'compensation' else '0.005'))
        write(':TRIGger:SWEep '+('AUTO' if args.action == 'compensation' else 'NORMal'))
        write(':RUN')
        query('*OPC?')
    result = {'identity': identity}
    for command in [':TRIGger:STATus?', ':TIMebase:MAIN:SCALe?',
                    ':CHANnel1:PROBe?', ':CHANnel2:PROBe?',
                    ':MEASure:ITEM? VPP,CHANnel1', ':MEASure:ITEM? FREQuency,CHANnel1',
                    ':MEASure:ITEM? VPP,CHANnel2', ':MEASure:ITEM? FREQuency,CHANnel2',
                    ':SYSTem:ERRor?']:
        result[command] = query(command)
    print(json.dumps(result, indent=2))
