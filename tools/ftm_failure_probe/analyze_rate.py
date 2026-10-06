#!/usr/bin/env python3
"""Offline clock-rate diagnostic, including rejected FTM timestamp quartets."""
import argparse
from collections import Counter
import json
from pathlib import Path

from analyze import distribution, parse_reports

PERIOD = 1 << 48


def fit_rate(entries, remote_key, local_key):
    first = entries[0]
    local = [entry[local_key] - first[local_key] for entry in entries]
    remote = [(entry[remote_key] - first[remote_key]) % PERIOD for entry in entries]
    if any(right <= left for left, right in zip(local, local[1:])):
        raise ValueError('nonmonotonic local timestamps')
    if any(right <= left for left, right in zip(remote, remote[1:])):
        raise ValueError('nonmonotonic remote timestamps')
    if not 1_000_000_000 <= local[-1] <= 1_000_000_000_000:
        raise ValueError('rate fit requires 1 ms to 1 s span')
    correction = [remote_value - local_value
                  for remote_value, local_value in zip(remote, local)]
    mean_local = sum(local) / len(local)
    mean_correction = sum(correction) / len(correction)
    variance = sum((value - mean_local)**2 for value in local)
    rate = sum((local_value - mean_local) * (delta - mean_correction)
               for local_value, delta in zip(local, correction)) / variance
    residual = [delta - mean_correction - rate * (local_value - mean_local)
                for local_value, delta in zip(local, correction)]
    return rate, max(abs(value) for value in residual)


def measure(report):
    # Selection uses timestamp integrity, never the driver's positive-RTT gate.
    entries = [entry for entry in report['entries']
               if all(entry[key] for key in ('t1', 't2', 't3', 't4'))
               and 0 <= entry['t1'] < PERIOD and 0 <= entry['t4'] < PERIOD
               and 0 < entry['t3'] - entry['t2'] < 10_000_000_000
               and 0 < (entry['t4'] - entry['t1']) % PERIOD < 10_000_000_000]
    if len(entries) < 4:
        raise ValueError('fewer than four complete quartets')
    receive_rate, receive_residual = fit_rate(entries, 't1', 't2')
    transmit_rate, transmit_residual = fit_rate(entries, 't4', 't3')
    local_turnaround = [entry['t3'] - entry['t2'] for entry in entries]
    raw = [(entry['t4'] - entry['t1']) % PERIOD - turnaround
           for entry, turnaround in zip(entries, local_turnaround)]
    return dict(receive_rate_ppm=receive_rate * 1e6,
                transmit_rate_ppm=transmit_rate * 1e6,
                receive_fit_max_residual_ps=receive_residual,
                transmit_fit_max_residual_ps=transmit_residual,
                raw_rtt_ps=raw,
                rate_contribution_ps=[receive_rate * value for value in local_turnaround],
                rate_adjusted_rtt_ps=[value - receive_rate * turnaround
                                      for value, turnaround in zip(raw, local_turnaround)])


def analyze(text, first=0, last=None):
    reports, omitted = parse_reports(text)
    selected = [report for report in reports if report['sequence'] >= first
                and (last is None or report['sequence'] <= last)]
    if not selected:
        raise ValueError('no selected reports')
    groups = {}
    for status in sorted({report['status'] for report in selected}):
        measured = []
        excluded = Counter()
        for report in selected:
            if report['status'] != status:
                continue
            try:
                measured.append(measure(report))
            except ValueError as error:
                excluded[str(error)] += 1
        group = dict(measured_reports=len(measured), excluded_reports=dict(excluded))
        if measured:
            for key in measured[0]:
                values = [item[key] for item in measured]
                if isinstance(values[0], list):
                    values = [value for batch in values for value in batch]
                group[key] = distribution(values)
        groups[status] = group
    return dict(selected_reports=len(selected), omitted_in_progress_report=omitted,
                statuses=groups,
                note='Offline rate estimate assuming stable propagation within each report. '
                     'Rate-adjusted RTT is not calibrated distance or a firmware correction.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('log', type=Path)
    parser.add_argument('--first', type=int, default=0)
    parser.add_argument('--last', type=int)
    args = parser.parse_args()
    print(json.dumps(analyze(args.log.read_text(errors='replace'), args.first, args.last), indent=2))
