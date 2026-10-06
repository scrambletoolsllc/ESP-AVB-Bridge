#!/usr/bin/env python3
"""Plot independently captured edge offsets without pooling configurations."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('summaries', type=Path, nargs='+')
args = parser.parse_args()
figure, axes = plt.subplots(len(args.summaries), 1, figsize=(10, 2.3 * len(args.summaries)), squeeze=False)
for axis, path in zip(axes[:, 0], args.summaries):
    summary = json.loads(path.read_text())
    pairs = [row for row in summary['rows'] if 'ch2_minus_ch1_ns' in row]
    missing = [row['index'] for row in summary['rows'] if 'missing_crossings' in row]
    axis.scatter([row['index'] for row in pairs], [row['ch2_minus_ch1_ns'] for row in pairs], s=12, color='#126c9b')
    axis.axhline(0, color='#888888', linewidth=.6)
    for limit in (-1000, 1000):
        axis.axhline(limit, color='#b45533', linestyle='--', linewidth=.8)
    for index in missing:
        axis.axvline(index, color='#d07c1a', linewidth=1.5)
    extent = max(1500, 1.1 * max((abs(row['ch2_minus_ch1_ns']) for row in pairs), default=0))
    axis.set_ylim(-extent, extent)
    axis.set_ylabel('Endpoint − bridge (ns)')
    label = path.stem.replace('ftm-', '').replace('-scope-summary', '').replace('-', ' ')
    axis.set_title(f"{label}: {summary['paired_edges']}/{summary['acquisitions']} paired; "
                   f"max |error| {max(abs(summary['min_ns']), abs(summary['max_ns'])):.0f} ns; "
                   f"missing {summary['missing_pairs']}", loc='left', fontsize=10)
    axis.grid(axis='y', alpha=.2)
axes[-1, 0].set_xlabel('Acquisition index within each run')
figure.suptitle('FTM-only clock discipline: independent Rigol output-edge measurements', fontsize=13)
figure.text(.02, .012, 'Experimental firmware; 3.2 ns sampling; no channel-skew correction. '
            'Not direct switch-clock accuracy or a conformance result.', fontsize=9)
figure.tight_layout(rect=(0, .03, 1, .96))
figure.savefig(args.output)
print(args.output)
