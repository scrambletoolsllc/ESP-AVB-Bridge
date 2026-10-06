#!/usr/bin/env python3
"""Check priority-255 Announce participation and absence of locally originated Sync."""
from pathlib import Path
import json,re,subprocess
from datetime import datetime,timezone
root=Path('build-ftm-discipline')
def records(name,label):
 result=[]
 for line in (root/name).read_text(errors='replace').splitlines():
  match=re.search(r'^\[(\d\d:\d\d:\d\d)\].*\b'+label+r',([^\r\n]+)',line)
  if match:result.append((datetime.fromisoformat('2026-09-25T'+match[1]).replace(tzinfo=timezone.utc).timestamp(),match[2].split(',')))
 return result
phases=records('host-root-ineligible-probe-live.log','SOURCELOSS');assert [int(row[1][0]) for row in phases]==list(range(5))
first=phases[1][0]+5;last=phases[2][0]-1
bridge='80f1b2fffed2caa9';motu='0001f2fffeff3b14';endpoint='fc012cfffefdfe80'
def packets(name):
 data=json.loads(subprocess.check_output(['tshark','-r',str(root/name),'-Y','ptp','-T','json','-x'],stderr=subprocess.DEVNULL))
 result=[]
 for packet in data:
  layers=packet['_source']['layers'];frame=layers['frame'];payload=bytes.fromhex(layers['ptp_raw'][0])
  result.append((float(frame['frame.time_epoch']),payload,frame['frame.interface_id_tree']['frame.interface_name']))
 return result
wired=packets('root-ineligible-taps.pcapng');peer=packets('root-ineligible-peer.pcapng')
outbound={interface for _,wire,interface in wired if wire[0]&15==2 and wire[20:30].hex()==bridge+'0001'}
inbound={interface for _,wire,interface in wired if len(wire)>=54 and wire[0]&15==3 and wire[44:54].hex()==bridge+'0001'}
errors=[]
if len(outbound)!=1 or len(inbound)!=1:errors.append('Ambiguous tap mapping')
results={}
for name,rows,interfaces in [('wired',wired,outbound),('wireless',peer,{'ftmtest0'})]:
 selected=[wire for stamp,wire,interface in rows if first<=stamp<last and interface in interfaces and wire[20:28].hex()==bridge]
 counts={kind:sum(wire[0]&15==kind for wire in selected) for kind in [0,8,11,12]}
 announce=[wire for wire in selected if wire[0]&15==11]
 if not announce or any(wire[47]!=255 or wire[53:61].hex()!=bridge for wire in announce):errors.append(name+' Announce priority/identity')
 if counts[0] or counts[8]:errors.append(name+' originated timing without an eligible root')
 if not counts[12]:errors.append(name+' stopped capability discovery')
 results[name]=counts
radio=[values for stamp,values in records('coprocessor-sync-probe-live.log','FTMTX') if first<=stamp<last]
if len(radio)<5 or len({int(row[0]) for row in radio})!=1:errors.append('Responder generated valid FTM payload during no-root window')
source=[values for stamp,values in records('host-root-ineligible-probe-live.log','TIMINGSOURCE') if first<=stamp<last]
if not source or any(row[1]!='0' for row in source):errors.append('Host published valid timing without an eligible root')
management=json.loads((root/'root-ineligible-management.json').read_text())
windows=[]
for name,start,end,btc in [('no eligible bridge root',first,last,endpoint),('upstream restored',phases[4][0]+8,phases[4][0]+40,motu)]:
 rows=[row for row in management if start<=datetime.fromisoformat(row['utc']).timestamp()<end]
 good=[row for row in rows if row.get('avb_info_status')==0 and row.get('path_status')==0]
 if not good or any(row.get('btc')!=btc for row in good):errors.append('Management source '+name)
 windows.append({'name':name,'queries':len(rows),'both_ok':len(good),'btc':btc})
announces=[wire for _,wire,_ in peer if wire[0]&15==11]
sequences=[int.from_bytes(wire[30:32],'big') for wire in announces]
if any((later-earlier)%65536!=1 for earlier,later in zip(sequences,sequences[1:])):errors.append('Wireless Announce sequence discontinuity')
if not any(wire[53:61].hex()==motu for stamp,wire,_ in peer if stamp>phases[4][0]+5 and wire[0]&15==11):errors.append('No restored upstream relay Announce')
report={'phases':phases,'guarded_window':[first,last],'wired_outbound_tap':sorted(outbound),'wired_inbound_tap':sorted(inbound),'message_counts':results,
 'radio_samples':len(radio),'radio_first_last':radio[::len(radio)-1] if len(radio)>1 else radio,'invalid_source_snapshots':len(source),
 'wireless_announces':len(announces),'management_total':len(management),'management_both_ok':sum(row.get('avb_info_status')==0 and row.get('path_status')==0 for row in management),
 'management_windows':windows,'no_root_behavior_pass':not [error for error in errors if error!='Wireless Announce sequence discontinuity'],'functional_pass':not errors,'errors':errors,
 'note':'Announce remains active at priority255 while local timing is absent. This checks no-root behavior, not complete role selection or Sync receipt timeout.'}
(root/'root-ineligible-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if errors:raise SystemExit(1)
