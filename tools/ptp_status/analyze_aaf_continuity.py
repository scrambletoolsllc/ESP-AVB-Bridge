#!/usr/bin/env python3
"""Count AAF packets and sequence discontinuities per tap inside a UTC window."""
import argparse, json, subprocess
from datetime import datetime, timezone
parser = argparse.ArgumentParser()
parser.add_argument('capture'); parser.add_argument('output')
parser.add_argument('--start'); parser.add_argument('--end')
args = parser.parse_args()
def epoch(text):
    return datetime.fromisoformat(text).astimezone(timezone.utc).timestamp() if text else None
start, end = epoch(args.start), epoch(args.end)
fields = ['frame.interface_name', 'frame.time_epoch', 'eth.src', 'aaf.seqnum']
rows = subprocess.run(['tshark', '-r', args.capture, '-Y', 'aaf.seqnum', '-T', 'fields', '-E', 'separator=,'] +
                      sum((['-e', f] for f in fields), []), capture_output=True, text=True, check=True).stdout
streams = {}
for line in rows.splitlines():
    iface, when, source, seq = line.split(',')[:4]
    when = float(when)
    if (start and when < start) or (end and when > end): continue
    key = (iface, source)
    record = streams.setdefault(key, {'interface': iface, 'source': source, 'packets': 0,
                                      'sequence_discontinuities': 0, 'first_epoch': when, 'last_epoch': when, 'last_sequence': None})
    seq = int(seq)
    if record['last_sequence'] is not None and (record['last_sequence'] + 1) % 256 != seq:
        record['sequence_discontinuities'] += 1
    record['last_sequence'] = seq; record['packets'] += 1; record['last_epoch'] = when
result = {'window_utc': [args.start, args.end], 'aaf_streams': sorted(streams.values(), key=lambda r: r['interface'])}
for r in result['aaf_streams']:
    span = r['last_epoch'] - r['first_epoch']
    r['mean_pps'] = round(r['packets'] / span, 1) if span > 0 else None
json.dump(result, open(args.output, 'w'), indent=2); print(json.dumps(result, indent=2))
