#!/usr/bin/env python3
"""Validate captured initial-interval capability messages independently of firmware."""
import argparse
import json
import statistics
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('capture', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--source', default='80:f1:b2:d2:ca:a9')
args = parser.parse_args()
packets = json.loads(subprocess.check_output([
    'tshark', '-r', str(args.capture), '-Y',
    f'eth.src=={args.source} && ptp.v2.messagetype==12', '-T', 'json', '-x'],
    text=True))
rows = []
errors = []
for packet in packets:
    layers = packet['_source']['layers']
    wire = bytes.fromhex(layers['ptp_raw'][0])
    frame = layers['frame']
    checks = {
        'length': len(wire) == 60,
        'header': wire[:6] == bytes.fromhex('1c12003c0000'),
        'flags_correction_reserved': wire[6:20] == bytes(14),
        'control_interval': wire[32:34] == bytes.fromhex('007f'),
        'wildcard': wire[34:44] == bytes([255])*10,
        'capable_tlv': wire[44:] == bytes.fromhex('8000000c0080c2000004000000000000'),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed: errors.append({'frame': frame['frame.number'], 'failed': failed})
    rows.append({'epoch': float(frame['frame.time_epoch']),
                 'interface': frame['frame.interface_id_tree']['frame.interface_name'],
                 'sequence': int.from_bytes(wire[30:32], 'big'),
                 'identity': wire[20:30].hex()})
intervals = [current['epoch']-previous['epoch'] for previous, current in zip(rows, rows[1:])]
gaps = [{'previous': previous['sequence'], 'current': current['sequence']}
        for previous, current in zip(rows, rows[1:])
        if (current['sequence']-previous['sequence']) % 65536 != 1]
summary = {'frames': len(rows), 'errors': errors, 'sequence_gaps': gaps,
           'interfaces': sorted({row['interface'] for row in rows}),
           'identities': sorted({row['identity'] for row in rows}),
           'interval_seconds': {'min': min(intervals), 'median': statistics.median(intervals),
                                'max': max(intervals)} if intervals else None,
           'scope': 'Domain-zero initial one-second capability messages; not full interval negotiation.'}
args.output.write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary, indent=2))
raise SystemExit(bool(errors or gaps or len(rows)<2))
