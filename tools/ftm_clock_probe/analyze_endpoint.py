#!/usr/bin/env python3
"""Characterize initiator clock domains without treating event latency as phase."""
import argparse
import json
import re
import statistics

PERIOD_PS = 1 << 48


def signed_delta(value, reference, period):
    return (value - reference + period // 2) % period - period // 2


def distribution(values):
    if not values:
        return None
    ordered = sorted(values)
    return dict(min=ordered[0], p50=statistics.median(ordered),
                p99=ordered[min(len(ordered)-1, int(len(ordered)*.99))],
                max=ordered[-1])


def analyze(lines):
    sessions = {}
    malformed = 0
    for line in lines:
        match = re.search(r'\bFTMLOCAL,([0-9,\-]+)', line)
        if not match:
            continue
        try:
            before, mac, after, token, receive, transmit, rtt = map(int, match[1].split(','))
            if after < before or not 0 <= mac < (1 << 32) or not 0 <= token <= 255:
                raise ValueError('invalid observation')
            if not 0 <= receive < (1 << 64) or not 0 <= transmit < (1 << 64):
                raise ValueError('invalid FTM width')
            session = sessions.setdefault(before, dict(mac=mac, after=after, entries=[]))
            if (mac, after) != (session['mac'], session['after']):
                raise ValueError('inconsistent session')
            session['entries'].append((token, receive, transmit, rtt))
        except ValueError:
            malformed += 1
    brackets, offsets, ages, turnarounds = [], [], [], []
    offset_lower, offset_upper = [], []
    wraps = 0
    epoch_crossings = 0
    previous_transmit = None
    valid_entries = 0
    for before, session in sorted(sessions.items()):
        brackets.append(session['after']-before)
        midpoint_offset = signed_delta(session['mac'], (before+session['after'])/2, 1 << 32)
        offsets.append(midpoint_offset)
        half_bracket = (session['after']-before)/2
        offset_lower.append(midpoint_offset-half_bracket-1)
        offset_upper.append(midpoint_offset+half_bracket+1)
        valid = [entry for entry in session['entries'] if entry[3] not in (0, (1 << 32)-1)]
        valid_entries += len(valid)
        for token, receive, transmit, rtt in valid:
            turnarounds.append((transmit-receive)/1e6)
        if valid:
            transmit = valid[-1][2]
            ages.append(signed_delta(session['mac']*1_000_000, transmit, (1 << 32)*1_000_000)/1e6)
            if previous_transmit is not None and transmit < previous_transmit and previous_transmit-transmit > PERIOD_PS/2:
                wraps += 1
            if previous_transmit is not None:
                epoch_crossings += max(0, transmit//PERIOD_PS-previous_transmit//PERIOD_PS)
            previous_transmit = transmit
    return dict(sessions=len(sessions), malformed=malformed, valid_entries=valid_entries,
                duration_s=(max(sessions)-min(sessions))/1e6 if sessions else 0,
                observed_t3_backwards_wraps=wraps,
                observed_t3_48bit_epoch_crossings=epoch_crossings,
                local_read_bracket_us=distribution(brackets),
                mac_minus_local_midpoint_us=distribution(offsets),
                unit_rate_mac_minus_local_interval_us=[max(offset_lower), min(offset_upper)] if offsets else None,
                unit_rate_interval_width_us=min(offset_upper)-max(offset_lower) if offsets else None,
                last_valid_t3_to_report_mac_us=distribution(ages),
                t2_to_t3_us=distribution(turnarounds), accuracy_verified=False,
                limitations='Use one uninterrupted boot with MAC/report ages less than half the 32-bit MAC period. Local T2/T3 retain more than 48 bits. MAC-to-FTM age assumes a common epoch modulo the MAC period; event scheduling and fixed counter bias cannot be separated here. MAC/local offset includes bracket uncertainty. This is not an end-to-end accuracy test.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('log')
    args = parser.parse_args()
    with open(args.log) as source:
        print(json.dumps(analyze(source), indent=2))
