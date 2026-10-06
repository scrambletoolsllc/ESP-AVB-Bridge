#!/usr/bin/env python3
"""Correlate finite source-loss diagnostics with independent packet and management evidence."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory', type=Path)
parser.add_argument('--date', default='2026-09-25')
args = parser.parse_args()
root = args.directory

def stamp(clock):
    return datetime.fromisoformat(args.date+'T'+clock).replace(tzinfo=timezone.utc).timestamp()

def records(name, label):
    pattern = re.compile(r'^\[(\d\d:\d\d:\d\d)\].*'+label+r',([^\r\n]+)')
    result = []
    for line in (root/name).read_text(errors='replace').splitlines():
        found = pattern.search(line)
        if found:
            result.append({'epoch': stamp(found[1]), 'values': found[2].split(',')})
    return result

phases = records('host-source-loss-live.log', 'SOURCELOSS')
assert [int(row['values'][0]) for row in phases] == list(range(5)), phases
starts = [row['epoch'] for row in phases]
errors = []
if not int(phases[2]['values'][1]) or not int(phases[4]['values'][2]):
    errors.append('Diagnostic did not discard both message classes')
ready = [row for row in records('endpoint-sta-policy-live.log', 'FTMREADY')
         if starts[0] <= row['epoch'] < starts[4]+40]
for first, last, wanted in [(0, 1, '1'), (1, 2, '0'), (2, 3, '1'), (3, 4, '0')]:
    if not any(starts[first] <= row['epoch'] < starts[last]+1 and row['values'][0] == wanted for row in ready):
        errors.append(f'Missing readiness {wanted} in phase {first}')
if not any(row['epoch'] >= starts[4] and row['values'][0] == '1' for row in ready):
    errors.append('No final readiness recovery')

motu = '0001f2fffeff3b14'
bridge = '80f1b2fffed2caa9'
endpoint = 'fc012cfffefdfe80'
windows = [('announce expired', starts[1]+4, starts[2], bridge, [bridge, endpoint]),
           ('announce restored', starts[2]+8, starts[3], motu, [motu, bridge, endpoint]),
           ('sync absent', starts[3]+2, starts[4], motu, [motu, bridge, endpoint]),
           ('sync restored', starts[4]+4, starts[4]+30, motu, [motu, bridge, endpoint])]
management = json.loads((root/'source-loss-management.json').read_text())
management_report = []
for label, first, last, btc, path in windows:
    selected = [row for row in management if first <= datetime.fromisoformat(row['utc']).timestamp() < last]
    good = [row for row in selected if row.get('avb_info_status') == 0 and row.get('path_status') == 0]
    mismatches = [row for row in good if row.get('btc') != btc or row.get('path') != path]
    if not good or mismatches:
        errors.append(f'Management identity/path failure: {label}')
    management_report.append({'phase': label, 'queries': len(selected), 'both_ok': len(good), 'mismatches': mismatches})

def packets(name):
    decoded = json.loads(subprocess.check_output(['tshark', '-r', str(root/name), '-Y', 'ptp', '-T', 'json', '-x'], stderr=subprocess.DEVNULL))
    for packet in decoded:
        layers = packet['_source']['layers']
        interface = layers['frame'].get('frame.interface_id_tree', {}).get('frame.interface_name')
        if not interface:
            raise ValueError('Capture is missing interface provenance')
        yield float(layers['frame']['frame.time_epoch']), bytes.fromhex(layers['ptp_raw'][0]), interface

announces = []
for epoch, wire, interface in packets('source-loss-peer.pcapng'):
    if wire[0] != 0x1b: continue
    path_length = int.from_bytes(wire[66:68], 'big')
    assert wire[64:66] == b'\x00\x08' and path_length % 8 == 0 and len(wire) == 68+path_length
    announces.append({'epoch': epoch, 'btc': wire[53:61].hex(), 'source': wire[20:30].hex(),
                      'path': [wire[index:index+8].hex() for index in range(68, len(wire), 8)],
                      'sequence': int.from_bytes(wire[30:32], 'big')})
if not announces or len({row['source'] for row in announces}) != 1 or any(row['source'][:16] != bridge for row in announces):
    errors.append('Announce logical source identity changed')
discontinuities = [{'earlier': earlier, 'later': later} for earlier, later in zip(announces, announces[1:])
                   if (later['sequence']-earlier['sequence']) % 65536 != 1]
if discontinuities:
    errors.append('Announce sequence discontinuity')
peer_report = []
for label, first, last, btc, path in windows:
    selected = [row for row in announces if first <= row['epoch'] < last]
    if not selected or any(row['btc'] != btc or row['path'] != path[:-1] for row in selected):
        errors.append(f'Captured Announce identity/path failure: {label}')
    peer_report.append({'phase': label, 'announces': selected})

wired = list(packets('source-loss-taps.pcapng'))
ingress = {interface for epoch, wire, interface in wired if wire[0]&15 == 3 and len(wire) >= 54 and wire[44:54].hex() == bridge+'0001'}
if len(ingress) != 1: errors.append('Ambiguous bridge inbound tap')
wire_report = []
for label, first, last, kinds in [('announce discarded', starts[1]+1, starts[2], [11]), ('sync discarded', starts[3]+1, starts[4], [0, 8])]:
    counts = Counter(wire[0]&15 for epoch, wire, interface in wired if interface in ingress and first <= epoch < last and wire[20:28].hex() == motu)
    if any(not counts[kind] for kind in kinds): errors.append(f'No independent upstream traffic: {label}')
    wire_report.append({'phase': label, 'ptp_type_counts': dict(counts)})
report = {'phases': phases, 'readiness': ready, 'management_windows': management_report,
          'management_total': len(management), 'avb_info_timeouts': sum(bool(row.get('avb_info_timeout')) for row in management),
          'path_timeouts': sum(bool(row.get('path_timeout')) for row in management),
          'peer_announce_windows': peer_report, 'bridge_inbound_tap': sorted(ingress), 'upstream_capture': wire_report,
          'sequence_discontinuities': discontinuities,
          'source_loss_behavior_pass': not [error for error in errors if error != 'Announce sequence discontinuity'],
          'errors': errors, 'functional_pass': not errors,
          'note': 'Host serial event times have one-second resolution. Guarded windows exclude transitions. Scope accuracy is summarized separately. No final-standard conformance claim.'}
(root/'source-loss-result.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({key: value for key, value in report.items() if key != 'peer_announce_windows'}, indent=2))
if errors: raise SystemExit(1)
