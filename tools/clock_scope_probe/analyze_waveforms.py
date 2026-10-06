#!/usr/bin/env python3
"""Compare paired rising edges using the scope's waveform preambles."""
import argparse
import json
import statistics


def rising_edge(channel, threshold=1.65):
    preamble = list(map(float, channel['preamble'].split(',')))
    increment, origin, reference = preamble[4:7]
    scale, offset, zero = preamble[7:10]
    voltage = [(code-offset-zero)*scale for code in channel['codes']]
    crossings = []
    for index in range(1, len(voltage)):
        if voltage[index-1] < threshold <= voltage[index]:
            fraction = (threshold-voltage[index-1])/(voltage[index]-voltage[index-1])
            crossings.append(origin+(index-1+fraction-reference)*increment)
    if not crossings:
        raise ValueError('No rising crossing')
    return min(crossings, key=abs), increment


def analyze(data):
    delays = []
    intervals = []
    for record in data['records']:
        first, sample = rising_edge(record['channels']['1'])
        second, other_sample = rising_edge(record['channels']['2'])
        delays.append((second-first)*1e9)
        intervals.extend([sample*1e9, other_sample*1e9])
    return {'captures': len(delays), 'threshold_v': 1.65,
            'ch2_minus_ch1_ns': {'min': min(delays), 'median': statistics.median(delays), 'max': max(delays)},
            'sample_interval_ns': sorted(set(intervals)),
            'note': 'Linear interpolation at a common voltage threshold. Same-pin result includes probe and channel mismatch; it is not an absolute timing calibration.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('capture')
    args = parser.parse_args()
    with open(args.capture) as source:
        print(json.dumps(analyze(json.load(source)), indent=2))
