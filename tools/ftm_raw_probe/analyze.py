#!/usr/bin/env python3
"""Analyze complete raw FTM reports with causal clock predictions."""
import argparse
import json
import re
from collections import Counter
from pathlib import Path
from statistics import median
from model import Entry, Report, RelativeModel, REMOTE_PERIOD


def parse(text):
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    if text.count('FTMRAW_BEGIN,1') != 1:
        raise ValueError('exactly one recorder boot is required')
    reports = []
    current = None
    expected = 0
    entries = []
    previous_generation = 1
    previous_attempt = 0
    previous_time = -1
    previous_dropped = 0
    for line in text.splitlines():
        header = re.search(r'\bFTMRAW,([^\r\n]+)', line)
        stamp = re.search(r'\bFTMSTAMP,([^\r\n]+)', line)
        if header:
            if current is not None:
                raise ValueError('incomplete report before next header')
            fields = header[1].split(',')
            if len(fields) != 8:
                raise ValueError('malformed report header')
            generation, attempt = map(int, fields[:2])
            peer = fields[2]
            before, mac, after, expected, dropped = map(int, fields[3:])
            if (generation < previous_generation or attempt <= previous_attempt or before <= previous_time
                    or after < before or not 0 <= mac < 1 << 32
                    or not 1 <= expected <= 16 or dropped < previous_dropped
                    or not re.fullmatch(r'[0-9a-f]{12}', peer)):
                raise ValueError('invalid or reordered report header')
            current = (generation, attempt, peer, before, mac, after, dropped)
            entries = []
            previous_generation = generation
            previous_attempt, previous_time, previous_dropped = attempt, before, dropped
        elif stamp:
            fields = list(map(int, stamp[1].split(',')))
            if len(fields) != 10 or current is None:
                raise ValueError('malformed or orphan timestamp')
            attempt, index, token, rssi, rtt, t1, t2, t3, t4, ppm = fields
            if (attempt != current[1] or index != len(entries) or not 0 <= token <= 255
                    or not -128 <= rssi <= 0 or not -32768 <= ppm <= 32767
                    or not 0 <= rtt <= 0xffffffff
                    or any(not 0 <= value < 1 << 64 for value in (t1,t2,t3,t4))):
                raise ValueError('invalid timestamp entry')
            entries.append(Entry(token,rssi,rtt,t1,t2,t3,t4,ppm))
            if len(entries) == expected:
                reports.append(Report(*current,tuple(entries)))
                current = None
    if current is not None:
        raise ValueError('incomplete final report')
    if not reports:
        raise ValueError('no reports')
    return reports


def distribution(values):
    if not values:
        return None
    ordered = sorted(values)
    return dict(min=ordered[0],median=median(ordered),
                p99=ordered[min(len(ordered)-1,int(.99*len(ordered)))],max=ordered[-1])


def analyze(reports):
    model = RelativeModel()
    errors, rates, ages = [], [], []
    rejected = Counter()
    accepted = wraps = predicted_reports = 0
    local_epoch_crossings = 0
    previous_local = None
    segments = set()
    for report in reports:
        try:
            result = model.observe(report)
        except ValueError as error:
            rejected[str(error)] += 1
            model.reset(None)
            continue
        accepted += 1
        last_local = next(entry.t3 for entry in reversed(report.entries)
                          if 0 < entry.rtt <= 0x7fffffff)
        if previous_local is not None and last_local >= previous_local:
            local_epoch_crossings += last_local//REMOTE_PERIOD-previous_local//REMOTE_PERIOD
        previous_local = last_local
        wraps += result['responder_wraps']
        segments.add(result['segment'])
        errors.extend(result['predicted_errors_ns'])
        ages.append(result['callback_age_us'])
        if result['remote_rate_ppm'] is not None:
            rates.append(result['remote_rate_ppm'])
            predicted_reports += 1
    return dict(reports=len(reports),accepted_reports=accepted,rejected_reports=dict(rejected),
                total_entries=sum(len(report.entries) for report in reports),
                invalid_rtt_entries=sum(not 0 < entry.rtt <= 0x7fffffff for report in reports for entry in report.entries),
                duration_s=(reports[-1].before_us-reports[0].before_us)/1e6,
                segments=len(segments),recorder_dropped_reports=reports[-1].dropped,
                responder_48bit_wraps=wraps,initiator_48bit_epoch_crossings=local_epoch_crossings,
                predicted_reports=predicted_reports,
                predicted_entries=len(errors),prediction_error_ns=distribution(errors),
                absolute_prediction_error_ns=distribution([abs(error) for error in errors]),
                remote_relative_rate_ppm=distribution(rates),callback_age_us=distribution(ages),
                independent_accuracy_verified=False,
                note='Relative clock fit only. Predictions use preceding reports, not current report. First responder epoch is arbitrary; absolute boot epoch, fixed bias and path asymmetry remain uncalibrated. Callback timestamps are freshness checks only.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('log',type=Path)
    args=parser.parse_args()
    print(json.dumps(analyze(parse(args.log.read_text(errors='replace'))),indent=2))
