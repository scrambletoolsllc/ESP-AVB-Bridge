#!/usr/bin/env python3
"""Verify raw descriptor reconstruction against the recorded FTM report."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from analyze import distribution, parse_reports


def reconstruct(values, compensation):
    _, _, _, raw_t3, rx_coarse, rx_phase, correction, tx_coarse, tx_phase = values
    folded = correction if correction <= 1023 else 2048 - correction
    rx_ticks = rx_coarse * 640 - 13312 + rx_phase * 8 + folded
    tx_ticks = (tx_coarse * 80 + tx_phase - 640) * 8
    to_ps = lambda ticks: ticks * 1562 + ticks // 2
    return to_ps(rx_ticks), to_ps(tx_ticks + compensation), tx_ticks == raw_t3


def analyze(text):
    reports, omitted = parse_reports(text)
    metadata = {}
    for match in re.finditer(r'\bFTMRXMETA,([0-9,]+)', text):
        values = tuple(map(int, match[1].split(',')))
        if len(values) != 9 or values[:2] in metadata:
            raise ValueError('malformed or duplicate metadata')
        metadata[values[:2]] = values
    groups = {}
    for status in sorted({report['status'] for report in reports}):
        missing = missing_with_t3 = mismatches = matched = 0
        rx_phase = Counter()
        tx_phase = Counter()
        phase_delta = Counter()
        corrections = []
        for report in reports:
            if report['status'] != status:
                continue
            for index, entry in enumerate(report['entries']):
                values = metadata.get((report['sequence'], index))
                if values is None:
                    missing += 1
                    missing_with_t3 += bool(entry['t3'])
                    continue
                matched += 1
                t2, t3, raw_ok = reconstruct(values, report['word74'])
                mismatches += not raw_ok or t2 != entry['t2'] or t3 != entry['t3']
                rx_phase[values[5]] += 1
                tx_phase[values[8]] += 1
                phase_delta[(values[8] - values[5]) % 80] += 1
                corrections.append(values[6] if values[6] <= 1023 else 2048-values[6])
        groups[status] = dict(matched_entries=matched, missing_entries=missing,
                             missing_entries_with_t3=missing_with_t3,
                             reconstruction_mismatches=mismatches,
                             rx_phase=dict(sorted(rx_phase.items())),
                             tx_phase=dict(sorted(tx_phase.items())),
                             tx_minus_rx_phase_mod80=dict(sorted(phase_delta.items())),
                             rx_phase_odd=sum(count for phase, count in rx_phase.items() if phase % 2),
                             tx_phase_odd=sum(count for phase, count in tx_phase.items() if phase % 2),
                             folded_rx_correction_ticks=distribution(corrections))
    return dict(reports=len(reports), omitted_in_progress_report=omitted, statuses=groups)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.log.read_text(errors='replace')), indent=2))
