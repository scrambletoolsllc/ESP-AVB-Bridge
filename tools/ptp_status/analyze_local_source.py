#!/usr/bin/env python3
"""Correlate finite local-root handover evidence without hiding transition errors."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import statistics
import math
import subprocess
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory',type=Path)
parser.add_argument('--date',default='2026-09-25')
args=parser.parse_args();root=args.directory

def epoch(clock):
    return datetime.fromisoformat(args.date+'T'+clock).replace(tzinfo=timezone.utc).timestamp()

def records(file,label):
    pattern=re.compile(r'^\[(\d\d:\d\d:\d\d)\].*\b'+label+r',([^\r\n]+)')
    result=[]
    for line in (root/file).read_text(errors='replace').splitlines():
        found=pattern.search(line)
        if found: result.append({'epoch':epoch(found[1]),'values':found[2].split(',')})
    return result
phases=records('host-local-source-probe-live.log','SOURCELOSS')
assert [int(row['values'][0]) for row in phases]==list(range(5)),phases
starts=[row['epoch'] for row in phases]
assert 23 <= starts[2]-starts[1] <=25
motu='0001f2fffeff3b14';bridge='80f1b2fffed2caa9';endpoint='fc012cfffefdfe80'
windows=[('upstream before expiry',starts[0]+16,starts[1]+2,motu),
         ('local root steady',starts[1]+10,starts[2]-1,bridge),
         ('upstream recovered',starts[2]+8,starts[3]-1,motu),
         ('sync missing',starts[3]+2,starts[4],motu),
         ('final recovery',starts[4]+8,starts[4]+45,motu)]
management=json.loads((root/'local-source-probe-management-retry.json').read_text())
scope=json.loads((root/'local-source-probe-scope-summary.json').read_text())
ready=[row for row in records('endpoint-announce-qualification-live.log','FTMREADY') if starts[0]-10<=row['epoch']<=starts[4]+45]
source=records('host-local-source-probe-live.log','UPSTREAM') + records('host-local-source-probe-live.log','TIMINGSOURCE')
errors=[];window_reports=[]
for name,first,last,btc in windows:
    status=[row for row in management if first<=datetime.fromisoformat(row['utc']).timestamp()<last]
    good=[row for row in status if row.get('avb_info_status')==0 and row.get('path_status')==0]
    path=[bridge,endpoint] if btc==bridge else [motu,bridge,endpoint]
    mismatches=[row for row in good if row.get('btc')!=btc or row.get('path')!=path]
    if not good or mismatches:errors.append('Management source/path: '+name)
    selected_snapshots=[row for row in source if first<=row['epoch']<last]
    if not selected_snapshots or any(row['values'][-1]!=btc for row in selected_snapshots):
        errors.append('Timing source identity: '+name)
    if name != 'sync missing' and any(row['values'][1]!='1' for row in selected_snapshots):
        errors.append('Timing source validity: '+name)
    measured=[row for row in scope['rows'] if first<=datetime.fromisoformat(row['utc']).timestamp()<last]
    values=[row['ch2_minus_ch1_ns'] for row in measured if 'ch2_minus_ch1_ns' in row]
    numeric={}
    if values:
        ordered=sorted(abs(value) for value in values)
        numeric={'min_ns':min(values),'max_ns':max(values),'median_ns':statistics.median(values),
                 'absolute_p95_ns':ordered[math.ceil(.95*len(ordered))-1],'within_1us':sum(abs(value)<1000 for value in values)}
    window_reports.append({'phase':name,'start_epoch':first,'end_epoch':last,'management_queries':len(status),'both_ok':len(good),
                           'mismatches':mismatches,'scope_acquisitions':len(measured),'paired_edges':len(values),**numeric})
    if name in ('local root steady','final recovery') and (not values or len(values)!=len(measured)):
        errors.append('Missing steady-state scope pairs: '+name)
if not any(starts[1]+3<=row['epoch']<starts[2] and row['values'][0]=='1' for row in ready):
    errors.append('Local-root readiness was never acquired')
if not any(starts[3]<=row['epoch']<starts[4]+1 and row['values'][0]=='0' for row in ready):
    errors.append('Sync loss did not invalidate readiness')
if not any(starts[4]<=row['epoch'] and row['values'][0]=='1' for row in ready):
    errors.append('Final readiness did not recover')
local=[row for row in source if starts[1]+4<=row['epoch']<starts[2]-1]
if not local or any(row['values'][1]!='1' or row['values'][-1]!=bridge or row['values'][3]!='0' or row['values'][5]!='0' for row in local):
    errors.append('Local source snapshot identity/offset/delay invalid')
packets=json.loads(subprocess.check_output(['tshark','-r',str(root/'local-source-probe-taps.pcapng'),'-Y','ptp','-T','json','-x'],stderr=subprocess.DEVNULL))
wire=[]
for packet in packets:
    layers=packet['_source']['layers'];frame=layers['frame']
    wire.append((float(frame['frame.time_epoch']),bytes.fromhex(layers['ptp_raw'][0]),frame.get('frame.interface_id_tree',{}).get('frame.interface_name')))
inbound={interface for _,payload,interface in wire if len(payload)>=54 and payload[0]&15==3 and payload[44:54].hex()==bridge+'0001'}
if len(inbound)!=1:errors.append('Ambiguous bridge inbound tap')
observed={}
for name,first,last,types in [('announce discarded',starts[1]+1,starts[2],[11]),('sync discarded',starts[3]+1,starts[4],[0,8])]:
    counts={kind:sum(interface in inbound and first<=stamp<last and payload[0]&15==kind and payload[20:28].hex()==motu for stamp,payload,interface in wire) for kind in types}
    observed[name]=counts
    if not all(counts.values()):errors.append('Missing independent upstream traffic: '+name)
if not int(phases[2]['values'][1]) or not int(phases[4]['values'][2]):errors.append('Diagnostic failed to discard both message classes')
report={'phases':phases,'windows':window_reports,'readiness':ready,'local_snapshots':len(local),
        'bridge_inbound_tap':sorted(inbound),'independent_upstream_traffic':observed,
        'management_total':len(management),'management_both_ok':sum(row.get('avb_info_status')==0 and row.get('path_status')==0 for row in management),
        'functional_pass':not errors,'errors':errors,'note':'All-sample scope summary includes handovers separately; steady windows have explicit settling margins. One-second serial resolution. This is not final-standard conformance.'}
(root/'local-source-probe-result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
if errors:raise SystemExit(1)
