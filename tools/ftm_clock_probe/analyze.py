#!/usr/bin/env python3
"""Describe clock-probe exchanges; software RTT does not establish accuracy."""
import argparse
import collections
import json
import math
import re
import statistics

FIELDS = ('host_boot cp_boot sequence host_before host_ptp host_after '
          'cp_receive mac_before mac mac_after tsf_before tsf tsf_after '
          'cp_send host_receive receive_ptp receive_after').split()


def parse(lines):
    groups = collections.defaultdict(list)
    rejected = 0
    seen = set()
    for line in lines:
        if not re.search(r'\bCLOCK,', line):
            continue
        match = re.search(r'CLOCK,([0-9,\-]+)', line)
        try:
            values = list(map(int, match.group(1).split(',')))
            if len(values) != len(FIELDS):
                raise ValueError('field count')
            row = dict(zip(FIELDS, values))
            key = (row['host_boot'], row['cp_boot'], row['sequence'])
            host = [row[name] for name in ('host_before', 'host_after', 'host_receive', 'receive_after')]
            coprocessor = [row[name] for name in ('cp_receive', 'mac_before', 'mac_after', 'tsf_before', 'tsf_after', 'cp_send')]
            if key in seen or host != sorted(host) or coprocessor != sorted(coprocessor):
                raise ValueError('duplicate or timestamp ordering')
            seen.add(key)
            groups[key[:2]].append(row)
        except (AttributeError, ValueError):
            rejected += 1
    return groups, rejected


def summary(values):
    values = sorted(values)
    if not values:
        return None
    return {'min': values[0], 'p50': statistics.median(values),
            'p99': values[max(0, math.ceil(.99 * len(values)) - 1)], 'max': values[-1]}


def slope(points):
    center_x = statistics.mean(point[0] for point in points)
    center_y = statistics.mean(point[1] for point in points)
    denominator = sum((point[0] - center_x)**2 for point in points)
    return (sum((point[0] - center_x) * (point[1] - center_y) for point in points)
            / denominator if denominator else 1.0)


def analyze(rows):
    rows = sorted(rows, key=lambda row: row['host_before'])
    rtt = lambda row: row['host_receive'] - row['host_after'] - (row['cp_send'] - row['cp_receive'])
    best = sorted(rows, key=rtt)[:max(2, math.ceil(len(rows) * .2))]
    midpoint = lambda row: ((row['host_after'] + row['host_receive']) / 2,
                            (row['cp_receive'] + row['cp_send']) / 2)
    rate = slope([midpoint(row) for row in best])
    origin = rows[0]['host_after']
    offsets = [midpoint(row)[1] - rate * (midpoint(row)[0] - origin) for row in rows]
    lower = max(row['cp_send'] - rate * (row['host_receive'] - origin) for row in rows)
    upper = min(row['cp_receive'] - rate * (row['host_after'] - origin) for row in rows)
    mac_offsets = []
    previous_mac = None
    unwrapped = 0
    for row in rows:
        if previous_mac is None:
            unwrapped = row['mac']
        else:
            # Valid when consecutive samples are less than half a MAC wrap apart.
            unwrapped += ((row['mac'] - previous_mac + 2**31) % 2**32) - 2**31
        previous_mac = row['mac']
        mac_offsets.append(unwrapped - (row['mac_before'] + row['mac_after']) / 2)
    ptp_discontinuities = []
    for earlier, later in zip(rows, rows[1:]):
        ptp_elapsed = (later['host_ptp'] - earlier['host_ptp']) / 1000
        minimum = later['host_before'] - earlier['host_after']
        maximum = later['host_after'] - earlier['host_before']
        excess = ptp_elapsed - min(max(ptp_elapsed, minimum), maximum)
        if abs(excess) > 100:
            ptp_discontinuities.append({'sequence': later['sequence'], 'outside_bracket_us': excess})
    return {
        'samples': len(rows), 'duration_s': (rows[-1]['host_after'] - origin) / 1e6,
        'transport_rtt_us_approx': summary([rtt(row) for row in rows]),
        'cp_processing_us': summary([row['cp_send'] - row['cp_receive'] for row in rows]),
        'ptp_read_bracket_us': summary([row['host_after'] - row['host_before'] for row in rows]),
        'mac_read_bracket_us': summary([row['mac_after'] - row['mac_before'] for row in rows]),
        'tsf_read_bracket_us': summary([row['tsf_after'] - row['tsf_before'] for row in rows]),
        'estimated_cp_relative_rate_ppm': (rate - 1) * 1e6,
        'offset_interval_width_us_at_fitted_rate': upper - lower,
        'midpoint_offset_spread_us': max(offsets) - min(offsets),
        'mac_minus_local_spread_us': max(mac_offsets) - min(mac_offsets),
        'tsf_minus_local_us': summary([row['tsf'] - (row['tsf_before'] + row['tsf_after']) / 2 for row in rows if row['tsf'] > 0]),
        'ptp_discontinuities_over_100us': ptp_discontinuities,
        'accuracy_verified': False,
        'limitations': 'Rate is a low-RTT fit. Offset interval is conditional on that rate; negative width rejects the model. Delay asymmetry and timestamp quantization remain unmeasured. MAC continuity assumes gaps below 2^31 us. PTP discontinuities include large slews.'
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log')
    args = parser.parse_args()
    with open(args.log) as source:
        lines = list(source)
    groups, rejected = parse(lines)
    frames = collections.defaultdict(list)
    for line in lines:
        match = re.search(r'\bFTMCLOCK,([0-9,]+)', line)
        if match:
            values = list(map(int, match.group(1).split(',')))
            if len(values) == 9:
                frames[tuple(values[:2])].append(values)
    frame_results = {}
    for boot, observations in frames.items():
        elapsed = [((row[4] - row[8] / 1e6 + 2**31) % 2**32) - 2**31 for row in observations]
        tsf_differences = []
        for frame in observations:
            candidates = groups.get(boot, [])
            if not candidates:
                continue
            anchor = min(candidates, key=lambda row: abs(row['tsf_before'] - frame[5]))
            if anchor['tsf'] <= 0 or abs(anchor['tsf_before'] - frame[5]) > 1000000:
                continue
            estimated_tsf = anchor['tsf'] + (frame[5] + frame[6] - anchor['tsf_before'] - anchor['tsf_after']) / 2
            tsf_differences.append(estimated_tsf - frame[8] / 1e6)
        frame_results[f'{boot[0]}:{boot[1]}'] = {
            'observations': len(observations),
            'callback_mac_minus_previous_ack_us_mod32': summary(elapsed),
            'mac_read_bracket_us': summary([row[6] - row[5] for row in observations]),
            'ack_minus_departure_us': summary([(row[8] - row[7]) / 1e6 for row in observations]),
            'estimated_callback_tsf_minus_previous_ack_us': summary(tsf_differences),
            'limitations': 'Latest callback only, not every frame. Callback time is later than the previous ACK; difference includes interframe scheduling and does not measure simultaneous clock offset.'
        }
    print(json.dumps({'rejected': rejected, 'boots': {f'{key[0]}:{key[1]}': analyze(rows) for key, rows in groups.items()}, 'ftm_frames': frame_results}, indent=2))
