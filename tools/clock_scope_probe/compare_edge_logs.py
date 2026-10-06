#!/usr/bin/env python3
"""Compare reported PTP pulse seconds during one settled, single-day run."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import statistics
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('bridge', type=Path)
parser.add_argument('endpoint', type=Path)
parser.add_argument('--after', required=True, help='UTC HH:MM:SS after acquisition/source changes')
parser.add_argument('--before', default='23:59:59')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
pattern = re.compile(r'^\[(\d\d:\d\d:\d\d)\].*SCOPE_EDGE,\d+,\d+,(\d+),')
def read(path):
    records = []
    for line in path.read_text(errors='replace').splitlines():
        match = pattern.search(line)
        if match and args.after <= match[1] <= args.before:
            records.append({'utc': match[1], 'target_ns': int(match[2])})
    return records
bridge, endpoint = read(args.bridge), read(args.endpoint)
if not bridge or not endpoint:
    raise SystemExit('No settled edge records in selected interval')
bridge_counts = Counter(row['target_ns'] for row in bridge)
endpoint_counts = Counter(row['target_ns'] for row in endpoint)
first = max(min(bridge_counts), min(endpoint_counts))
last = min(max(bridge_counts), max(endpoint_counts))
if first > last:
    raise SystemExit('No overlapping reported time range')
expected = set(range(first, last + 1, 1000000000))
def seconds(value):
    hour, minute, second = map(int, value.split(':'))
    return hour * 3600 + minute * 60 + second
bridge_utc = {row['target_ns']: seconds(row['utc']) for row in bridge}
endpoint_utc = {row['target_ns']: seconds(row['utc']) for row in endpoint}
log_lags = [endpoint_utc[target] - bridge_utc[target] for target in expected & bridge_utc.keys() & endpoint_utc.keys()]
report = {'after_utc': args.after, 'before_utc': args.before,
          'first_target_ns': first, 'last_target_ns': last,
          'expected_seconds': len(expected),
          'common_seconds': len(expected & bridge_counts.keys() & endpoint_counts.keys()),
          'missing_bridge': sorted(expected - bridge_counts.keys()),
          'missing_endpoint': sorted(expected - endpoint_counts.keys()),
          'duplicate_bridge': sorted(key for key, count in bridge_counts.items() if count > 1),
          'duplicate_endpoint': sorted(key for key, count in endpoint_counts.items() if count > 1),
          'host_log_lag_seconds': {'minimum': min(log_lags), 'median': statistics.median(log_lags), 'maximum': max(log_lags)} if log_lags else None,
          'note': 'Host log timestamps have one-second resolution and serial buffering. Internal reported target seconds only; pair with physical scope evidence. A source time jump requires separate intervals.'}
args.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
