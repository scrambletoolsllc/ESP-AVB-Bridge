#!/usr/bin/env python3
"""Compare GPIO hardware captures and their local clock read brackets."""
import argparse
import collections
import json
import re
import statistics
from analyze import slope, summary


def parse_edges(lines):
    hosts = {}
    coprocessors = collections.defaultdict(list)
    rejected = 0
    for line in lines:
        match = re.search(r'\b(HOSTEDGE|EDGECLOCK),([0-9,\-]+)', line)
        if not match:
            continue
        try:
            row = list(map(int, match[2].split(',')))
            if match[1] == 'HOSTEDGE' and len(row) == 6:
                if tuple(row[:2]) in hosts:
                    raise ValueError('duplicate host edge')
                hosts[tuple(row[:2])] = row
            elif match[1] == 'EDGECLOCK' and len(row) == 12:
                coprocessors[tuple(row[:2])].append(row)
            else:
                raise ValueError('field count')
        except ValueError:
            rejected += 1
    return hosts, coprocessors, rejected


def analyze_edges(hosts, rows):
    matched = []
    rejected = 0
    seen = set()
    for row in sorted(rows, key=lambda row: row[2]):
        host = hosts.get((row[0], row[11]))
        if (not host or row[2] in seen or row[2] != row[11]
                or not 0 < row[4] <= row[5] <= row[6]
                or not 0 < host[2] <= host[3] <= host[5]):
            rejected += 1
            continue
        seen.add(row[2])
        matched.append((host, row))
    if len(matched) < 3:
        return {'matched': len(matched), 'rejected': rejected, 'ready': False}
    first_host, first_cp = matched[0]
    host_ptp_origin = first_host[4]
    cp_ticks_origin = first_cp[4]
    raw_mac = first_cp[3]
    unwrapped_mac = raw_mac
    mac_pairs = []
    edge_pairs = []
    mac_bounds = []
    for host, row in matched:
        unwrapped_mac += (row[3] - raw_mac + 2**31) % 2**32 - 2**31
        raw_mac = row[3]
        before_us = (row[5] - cp_ticks_origin) / 40
        after_us = (row[6] - cp_ticks_origin) / 40
        mac_pairs.append(((before_us + after_us) / 2, unwrapped_mac))
        mac_bounds.append((before_us, after_us, unwrapped_mac))
        # Extrapolate the bracketed PTP sample back to the captured host edge.
        # This uses nominal GPTimer rate over the short read-to-edge interval.
        ptp_edge_us = (host[4] - host_ptp_origin) / 1000 - ((host[3] + host[5]) / 2 - host[2]) / 40
        edge_pairs.append(((row[4] - cp_ticks_origin) / 40, ptp_edge_us))
    edge_rate = slope(edge_pairs)
    edge_offset = statistics.mean(reference - edge_rate * local for local, reference in edge_pairs)
    residuals = [abs(reference - edge_rate * local - edge_offset) for local, reference in edge_pairs]
    mac_rate = slope(mac_pairs)
    lower = max(mac - mac_rate * after for before, after, mac in mac_bounds)
    upper = min(mac + 1 - mac_rate * before for before, after, mac in mac_bounds)
    raw_pairs = [((row[4] - cp_ticks_origin) / 40,
                  (host[2] - first_host[2]) / 40) for host, row in matched]
    raw_rate = slope(raw_pairs)
    raw_offset = statistics.mean(host - raw_rate * cp for cp, host in raw_pairs)
    raw_residuals = [abs(host - raw_rate * cp - raw_offset) for cp, host in raw_pairs]
    interpolation = []
    for previous, current, following in zip(raw_pairs, raw_pairs[1:], raw_pairs[2:]):
        fraction = (current[0] - previous[0]) / (following[0] - previous[0])
        predicted = previous[1] + fraction * (following[1] - previous[1])
        interpolation.append(abs(current[1] - predicted))
    causal_prediction = []
    for index in range(4, len(raw_pairs)):
        history = raw_pairs[index - 4:index]
        local_rate = slope(history)
        local_offset = statistics.mean(host - local_rate * cp for cp, host in history)
        current_cp, current_host = raw_pairs[index]
        causal_prediction.append(abs(current_host - local_rate * current_cp - local_offset))
    return {
        'matched': len(matched), 'rejected': rejected,
        'duration_s': (matched[-1][1][4] - cp_ticks_origin) / 40000000,
        'host_ptp_read_bracket_us': summary([(host[5] - host[3]) / 40 for host, row in matched]),
        'cp_mac_read_bracket_us': summary([(row[6] - row[5]) / 40 for host, row in matched]),
        'cp_isr_latency_upper_us': summary([(row[5] - row[4]) / 40 for host, row in matched]),
        'ptp_vs_cp_timer_rate_ppm': (edge_rate - 1) * 1e6,
        'host_timer_vs_cp_timer_rate_ppm': (raw_rate - 1) * 1e6,
        'raw_capture_linear_fit_absolute_residual_us': summary(raw_residuals),
        'raw_capture_neighbor_interpolation_absolute_residual_us': summary(interpolation),
        'raw_capture_previous_four_prediction_absolute_error_us': summary(causal_prediction),
        'ptp_edge_linear_fit_absolute_residual_us': summary(residuals),
        'mac_vs_cp_timer_rate_ppm': (mac_rate - 1) * 1e6,
        'mac_offset_interval_width_us_at_fitted_rate': upper - lower,
        'accuracy_verified': False,
        'limitations': 'Sequence matching assumes no extra or missed GPIO interrupts since boot. Fit residual measures repeatability, not fixed capture skew or absolute accuracy. MAC interval assumes 1 us quantization and fitted rate; negative width rejects that model. PTP read brackets and servo rate changes affect residuals.'
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log')
    args = parser.parse_args()
    with open(args.log) as source:
        hosts, groups, rejected = parse_edges(source)
    print(json.dumps({'malformed': rejected, 'boots': {f'{boot[0]}:{boot[1]}': analyze_edges(hosts, rows) for boot, rows in groups.items()}}, indent=2))
