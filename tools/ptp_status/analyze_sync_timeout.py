#!/usr/bin/env python3
"""Correlate Sync receipt expiry, source selection, and independent wire evidence."""
from pathlib import Path
from datetime import datetime,timezone
import json,re,subprocess,statistics,math
root=Path('build-ftm-discipline')
def records(name,label):
 result=[]
 for line in (root/name).read_text(errors='replace').splitlines():
  match=re.search(r'^\[(\d\d:\d\d:\d\d)\].*\b'+label+r',([^\r\n]+)',line)
  if match:result.append({'epoch':datetime.fromisoformat('2026-09-25T'+match[1]).replace(tzinfo=timezone.utc).timestamp(),'values':match[2].split(',')})
 return result
phases=records('host-sync-receipt-probe-live.log','SOURCELOSS');assert [int(row['values'][0]) for row in phases]==list(range(5))
starts=[row['epoch'] for row in phases];bridge='80f1b2fffed2caa9';motu='0001f2fffeff3b14';endpoint='fc012cfffefdfe80'
def packets(name):
 data=json.loads(subprocess.check_output(['tshark','-r',str(root/name),'-Y','ptp','-T','json','-x'],stderr=subprocess.DEVNULL))
 result=[]
 for packet in data:
  layers=packet['_source']['layers'];frame=layers['frame'];wire=bytes.fromhex(layers['ptp_raw'][0])
  result.append((float(frame['frame.time_epoch']),wire,frame['frame.interface_id_tree']['frame.interface_name']))
 return result
wired=packets('sync-receipt-probe-taps.pcapng');peer=packets('sync-receipt-probe-peer.pcapng')
inbound={interface for _,wire,interface in wired if len(wire)>=54 and wire[0]&15==3 and wire[44:54].hex()==bridge+'0001'}
errors=[]
if len(inbound)!=1:errors.append('Ambiguous bridge inbound tap')
timeouts=[row for row in records('host-sync-receipt-probe-live.log','SYNCTIMEOUT') if starts[3]<=row['epoch']<=starts[4]]
for row in timeouts:
 now,received,interval=map(int,row['values']);row['elapsed_us']=now-received
 if interval!=375000 or not interval<=now-received<500000:errors.append('Unexpected Sync expiry timing')
if len(timeouts)<3:errors.append('Missing expiry despite repeated Announce')
if not int(phases[2]['values'][1]) or not int(phases[4]['values'][2]):errors.append('Both loss classes were not exercised')
independent_counts={kind:sum(starts[3]<=stamp<starts[4] and interface in inbound and wire[20:28].hex()==motu and wire[0]&15==kind for stamp,wire,interface in wired) for kind in [0,8,11]}
if not all(independent_counts.values()):errors.append('Missing independent upstream Sync/FU/Announce')
announces=[(stamp,wire) for stamp,wire,_ in peer if wire[0]&15==11]
source_changes=[];previous=None
for stamp,wire in announces:
 btc=wire[53:61].hex()
 if btc!=previous:source_changes.append({'utc':datetime.fromtimestamp(stamp,timezone.utc).isoformat(),'epoch':stamp,'btc':btc});previous=btc
sync_window=[row for row in source_changes if starts[3]<=row['epoch']<starts[4]+1]
if not any(row['btc']==bridge for row in sync_window):errors.append('Sync expiry did not select local clock on wire')
if not any(row['btc']==motu and row['epoch']>=starts[4] for row in source_changes):errors.append('No MOTU wire recovery')
identities={wire[20:30].hex() for _,wire in announces}
if len(identities)!=1 or not all(identity.startswith(bridge) for identity in identities):errors.append('Announce logical source identity changed')
sequences=[int.from_bytes(wire[30:32],'big') for _,wire in announces]
discontinuities=[(earlier,later) for earlier,later in zip(sequences,sequences[1:]) if (later-earlier)%65536!=1]
management=json.loads((root/'sync-receipt-probe-management.json').read_text());scope=json.loads((root/'sync-receipt-probe-scope-summary.json').read_text())
windows=[]
for name,first,last,btc in [('local root steady',starts[1]+10,starts[2]-1,bridge),('Sync outage',starts[3],starts[4],None),('final recovery',starts[4]+10,starts[4]+40,motu)]:
 rows=[row for row in management if first<=datetime.fromisoformat(row['utc']).timestamp()<last]
 good=[row for row in rows if row.get('avb_info_status')==0 and row.get('path_status')==0]
 if btc and (not good or any(row.get('btc')!=btc for row in good)):errors.append('Management selection '+name)
 measured=[row for row in scope['rows'] if first<=datetime.fromisoformat(row['utc']).timestamp()<last]
 values=[row['ch2_minus_ch1_ns'] for row in measured if 'ch2_minus_ch1_ns' in row]
 numeric={}
 if values:
  ordered=sorted(abs(value) for value in values);numeric={'min_ns':min(values),'max_ns':max(values),'median_ns':statistics.median(values),'absolute_p95_ns':ordered[math.ceil(.95*len(values))-1],'within_1us':sum(abs(value)<1000 for value in values)}
 windows.append({'name':name,'queries':len(rows),'both_ok':len(good),'reported_btc':sorted({row.get('btc','') for row in good}),'scope_pairs':len(values),'scope_missing':len(measured)-len(values),**numeric})
 if btc and (not values or len(values)!=len(measured)):errors.append('Missing steady scope pairs '+name)
report={'phases':phases,'bridge_inbound_tap':sorted(inbound),'sync_expirations':timeouts,'independent_upstream_packets':independent_counts,
 'announces':len(announces),'source_changes':source_changes,'sequence_discontinuities':discontinuities,'windows':windows,
 'management_total':len(management),'management_both_ok':sum(row.get('avb_info_status')==0 and row.get('path_status')==0 for row in management),
 'receipt_behavior_pass':not errors,'functional_pass':not errors and not discontinuities and all(row.get('avb_info_status')==0 and row.get('path_status')==0 for row in management),'errors':errors,
 'note':'Serial seconds are coarse; timeout elapsed times use internal monotonic microseconds. Repeated Announce can initiate another acquisition after aging; only complete timing renews an existing selection. Not full per-port state-machine conformance.'}
(root/'sync-receipt-probe-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if not report['functional_pass']:raise SystemExit(1)
