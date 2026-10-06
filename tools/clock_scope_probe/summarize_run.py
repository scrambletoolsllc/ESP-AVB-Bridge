#!/usr/bin/env python3
"""Summarize paired scope acquisitions without hiding missing crossings."""
import argparse
import datetime
import json
import math
import statistics
from pathlib import Path
from analyze_waveforms import rising_edge

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('capture', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
data = json.loads(args.capture.read_text())
rows = []
intervals = set()
for record in data['records']:
    row = {'index': record['index'], 'utc': datetime.datetime.fromtimestamp(
        record['host_time'], datetime.timezone.utc).isoformat()}
    crossings = {}
    missing = []
    for channel in ('1', '2'):
        try:
            edge, interval = rising_edge(record['channels'][channel])
            crossings[channel] = edge
            intervals.add(interval * 1e9)
        except ValueError:
            missing.append(channel)
    if missing:
        row['missing_crossings'] = missing
    else:
        row['ch2_minus_ch1_ns'] = (crossings['2'] - crossings['1']) * 1e9
    rows.append(row)
values = [row['ch2_minus_ch1_ns'] for row in rows if 'ch2_minus_ch1_ns' in row]
summary = {'identity': data['identity'], 'acquisitions': len(rows),
           'rejected_arming_attempts': len(data.get('rejected_arming', [])),
           'empty_waveform_records': sum(any(not channel['codes'] for channel in record['channels'].values()) for record in data['records']),
           'paired_edges': len(values), 'missing_pairs': len(rows) - len(values),
           'sample_interval_ns': sorted(intervals), 'threshold_v': 1.65,
           'note': 'Output-edge alignment; no probe correction applied. Missing pairs are excluded from numeric percentiles and explicitly counted.'}
if values:
    ordered = sorted(abs(value) for value in values)
    summary.update(min_ns=min(values), median_ns=statistics.median(values),
                   max_ns=max(values), absolute_p95_ns=ordered[math.ceil(.95 * len(ordered)) - 1],
                   within_1us=sum(abs(value) < 1000 for value in values))
print(json.dumps(summary, indent=2))
summary['rows'] = rows
args.output.write_text(json.dumps(summary, indent=2) + '\n')
