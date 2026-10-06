#!/usr/bin/env python3
"""Summarize repeated MAC transition intervals and held-out checks."""
import argparse
import json
import re
import statistics
from pathlib import Path

FIELDS = ('round', 'start_us', 'duration_us', 'train', 'held', 'invalid',
          'unchanged', 'lower', 'upper', 'held_lower', 'held_upper',
          'violations', 'miss_max', 'width_min', 'width_max')


def summarize(text):
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    records = re.findall(r'MAC_TRANSITION,([^\r\n]+)', text)
    if not records or any(len(record.split(',')) != len(FIELDS) for record in records):
        raise ValueError('Missing or malformed diagnostic records')
    rows = [dict(zip(FIELDS, map(int, record.split(',')))) for record in records]
    for index, row in enumerate(rows):
        if row['round'] != index or (index and row['start_us'] <= rows[index-1]['start_us']):
            raise ValueError('Missing, reordered or mixed-boot records')
        counts = [row[key] for key in ('train', 'held', 'invalid', 'unchanged')]
        if (min(counts) < 0 or sum(counts) != 2048 or row['train'] > 1024 or
                row['held'] > 1024 or not 0 <= row['violations'] <= row['held'] or
                row['miss_max'] < 0 or row['duration_us'] <= 0):
            raise ValueError('Invalid observation counts')
        if row['train'] + row['held'] and not 0 <= row['width_min'] <= row['width_max'] <= 400:
            raise ValueError('Invalid accepted-read brackets')
    good = [row for row in rows if row['train'] and row['held'] and
            row['lower'] <= row['upper'] and row['held_lower'] <= row['held_upper']]
    result = {
        'rounds': len(rows), 'usable_rounds': len(good),
        'completed': 'MAC_TRANSITION_END' in text and 'MAC_TRANSITION_ABORT' not in text,
        'complete_run': 'MAC_TRANSITION_END' in text and 'MAC_TRANSITION_ABORT' not in text and len(rows) == 120,
        'unusable_rounds': len(rows)-len(good),
        'sampling_span_s': (rows[-1]['start_us'] + rows[-1]['duration_us'] - rows[0]['start_us']) / 1e6,
        'timer_mode': re.findall(r'MAC_TRANSITION_MODE,([^\r\n]+)', text),
        'read_mode': re.findall(r'MAC_TRANSITION_READ,([^\r\n]+)', text),
        'transitions': sum(row['train'] + row['held'] for row in rows),
        'rejected_reads': sum(row['invalid'] for row in rows),
        'heldout_midpoint_violations': sum(row['violations'] for row in rows),
        'note': 'Conditional MAC-to-timer mapping intervals, not absolute FTM or wired-clock accuracy. Fixed read/counter bias is not calibrated.',
    }
    if good:
        widths = [(row['upper']-row['lower'])*25 for row in good]
        midpoints = [(row['lower']+(row['upper']-row['lower'])//2)*25 for row in good]
        result.update({
            'training_interval_width_ns': {'min': min(widths), 'median': statistics.median(widths), 'max': max(widths)},
            'training_midpoint_span_ns': max(midpoints)-min(midpoints),
            'heldout_max_miss_ns': max(row['miss_max'] for row in good)*25,
            'global_interval_width_ns': (min(min(row['upper'], row['held_upper']) for row in good)-
                                         max(max(row['lower'], row['held_lower']) for row in good))*25,
            'single_bracket_ns': {'min': min(row['width_min'] for row in good)*25,
                                  'max': max(row['width_max'] for row in good)*25},
        })
    result['consistent'] = bool(good) and len(good) == len(rows) and not result['heldout_midpoint_violations'] and result['global_interval_width_ns'] >= 0
    result['validated_run'] = result['complete_run'] and result['consistent']
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.log.read_text(errors='replace')), indent=2))
