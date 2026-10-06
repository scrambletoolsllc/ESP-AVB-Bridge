#!/usr/bin/env python3
"""Summarize bounded MAC/local mappings, not independent clock accuracy."""
import argparse
import json
import re
import statistics
from pathlib import Path


def analyze(lines):
    rows = []
    malformed = 0
    for line in lines:
        found = re.search(r'\bFTMLOCAL,([0-9,\-]+)', line)
        if not found:
            continue
        row = list(map(int, found[1].split(',')))
        if len(row) != 12:
            malformed += 1
            continue
        rows.append(row)
    valid = [row for row in rows if row[2]]
    offsets = [row[4] + (row[5] + row[6]) // 2 - row[3] * 1000 for row in valid]
    violations = sum(not (row[10] <= (row[5] + row[6]) // 2 <= row[11]) for row in valid)
    return {'logged_batches': len(rows), 'valid_logged': len(valid),
            'malformed': malformed, 'heldout_violations': violations,
            'generations': sorted({row[1] for row in rows}),
            'interval_widths_ns': sorted({row[6] - row[5] for row in valid}),
            'offset_ns': {'min': min(offsets), 'median': statistics.median(offsets),
                          'max': max(offsets)} if offsets else None,
            'note': 'Sparse logs; interval is local read uncertainty, not physical accuracy. '
                    'Offset range must be split at resets or coarse counter wrap.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.log.read_text().splitlines()), indent=2))
