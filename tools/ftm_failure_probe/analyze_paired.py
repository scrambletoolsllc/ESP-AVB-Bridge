#!/usr/bin/env python3
"""Match responder captures to the exact timestamp pairs received by a STA."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from analyze import distribution, parse_reports

PERIOD = 1 << 48


def parse_responder(text):
    if text.count('FTMRESP_BEGIN,1') != 1:
        raise ValueError('exactly one responder boot required')
    records = []
    for match in re.finditer(r'\bFTMRESP,([^\r\n]+)', text):
        fields = match[1].split(',')
        if len(fields) != 12:
            raise ValueError('malformed responder record')
        keys = ('sequence', 'time_us', 'peer', 'token', 'raw_t1', 'raw_t4',
                't1', 't4', 'compensation', 'rssi', 'context_found', 'dropped')
        record = dict(zip(keys, [value if index == 2 else int(value)
                                for index, value in enumerate(fields)]))
        if records and record['sequence'] <= records[-1]['sequence']:
            raise ValueError('unordered responder capture')
        records.append(record)
    if not records:
        raise ValueError('no responder records')
    return records


def ticks_to_ps(ticks):
    return ticks * 1562 + ticks // 2


def analyze(endpoint_text, responder_text, peer='fc012cfdfe80', allow_responder_reboots=False):
    reports, omitted = parse_reports(endpoint_text)
    if allow_responder_reboots:
        boot_texts = responder_text.split('FTMRESP_BEGIN,1')[1:]
        if not boot_texts:
            raise ValueError('no responder boot markers')
        boots = []
        for portion in boot_texts:
            # A startup boot can finish without any FTM session.
            boots.append(parse_responder('FTMRESP_BEGIN,1' + portion)
                         if re.search(r'\bFTMRESP,', portion) else [])
    else:
        boots = [parse_responder(responder_text)]
    records = []
    for boot, items in enumerate(boots, 1):
        for record in items:
            record['boot'] = boot
            records.append(record)
    if not records:
        raise ValueError('no responder records')
    lookup = {}
    conversion_errors = Counter()
    for record in records:
        if record['peer'] != peer or not record['context_found']:
            continue
        if ticks_to_ps(record['raw_t1'] + record['compensation']) != record['t1']:
            conversion_errors['t1'] += 1
        if ticks_to_ps(record['raw_t4']) != record['t4']:
            conversion_errors['t4'] += 1
        key = record['t1'] % PERIOD, record['t4'] % PERIOD
        lookup.setdefault(key, []).append(record)
    groups = {}
    boot_measurements = {}
    for status in sorted({report['status'] for report in reports}):
        matched = missing_timestamps = unmatched = ambiguous = token_mismatches = 0
        raw_rtt = []
        tx_mod16 = Counter()
        rx_mod16 = Counter()
        compensation = Counter()
        matched_by_boot = Counter()
        for report in reports:
            if report['status'] != status:
                continue
            for entry in report['entries']:
                if not entry['t1'] or not entry['t4']:
                    missing_timestamps += 1
                    continue
                matches = lookup.get((entry['t1'], entry['t4']), [])
                if not matches:
                    unmatched += 1
                    continue
                if len(matches) != 1:
                    ambiguous += 1
                    continue
                record = matches[0]
                matched += 1
                matched_by_boot[record['boot']] += 1
                boot_data = boot_measurements.setdefault(record['boot'],
                    dict(status_counts=Counter(), rtt_ps=[], compensation=Counter(),
                         rtt_by_compensation={}))
                boot_data['status_counts'][status] += 1
                boot_data['compensation'][record['compensation']] += 1
                token_mismatches += record['token'] != entry['token']
                tx_mod16[record['raw_t1'] % 16] += 1
                rx_mod16[record['raw_t4'] % 16] += 1
                compensation[record['compensation']] += 1
                if entry['t2'] and entry['t3']:
                    rtt = (entry['t4'] - entry['t1']) % PERIOD - (entry['t3'] - entry['t2'])
                    raw_rtt.append(rtt)
                    boot_data['rtt_ps'].append(rtt)
                    boot_data['rtt_by_compensation'].setdefault(record['compensation'], []).append(rtt)
        groups[status] = dict(matched_entries=matched, unmatched_entries=unmatched,
                             missing_remote_timestamps=missing_timestamps,
                             ambiguous_matches=ambiguous, token_mismatches=token_mismatches,
                             rtt_ps=distribution(raw_rtt),
                             responder_tx_ticks_mod16=dict(tx_mod16),
                             responder_rx_ticks_mod16=dict(rx_mod16),
                             matched_by_responder_boot=dict(matched_by_boot),
                             responder_compensation=dict(compensation))
    for boot_data in boot_measurements.values():
        boot_data['rtt_ps'] = distribution(boot_data['rtt_ps'])
        boot_data['rtt_by_compensation'] = {key: distribution(values)
            for key, values in boot_data['rtt_by_compensation'].items()}
    return dict(reports=len(reports), responder_records=len(records),
                omitted_in_progress_report=omitted, responder_boots=len(boots),
                responder_dropped=sum(items[-1]['dropped'] for items in boots if items),
                endpoint_dropped=reports[-1]['dropped'],
                matched_by_responder_boot=boot_measurements,
                responder_conversion_errors=dict(conversion_errors), statuses=groups,
                note='Exact T1/T4 matching, independent of host log time. '
                     'Does not independently measure antenna propagation or timestamp bias.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('endpoint', type=Path)
    parser.add_argument('responder', type=Path)
    parser.add_argument('--require-matches', action='store_true')
    parser.add_argument('--allow-responder-reboots', action='store_true')
    args = parser.parse_args()
    result = analyze(args.endpoint.read_text(errors='replace'),
                     args.responder.read_text(errors='replace'),
                     allow_responder_reboots=args.allow_responder_reboots)
    if args.require_matches:
        if result['responder_conversion_errors'] or result['endpoint_dropped'] or result['responder_dropped']:
            raise ValueError('conversion mismatch or diagnostic queue loss')
        if not sum(group['matched_entries'] for group in result['statuses'].values()):
            raise ValueError('no paired exchanges')
        if any(group['ambiguous_matches'] or group['token_mismatches'] or group['unmatched_entries']
               for group in result['statuses'].values()):
            raise ValueError('missing, ambiguous or inconsistent paired exchanges')
    print(json.dumps(result, indent=2))
