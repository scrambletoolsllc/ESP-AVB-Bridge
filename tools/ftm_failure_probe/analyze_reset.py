#!/usr/bin/env python3
"""Compare explicit reset-test stages without merging their observations."""
import argparse
import json
from pathlib import Path
import re
from analyze import analyze


def stages(text):
    if text.count('FTMDEBUG_BEGIN,1')!=1:
        raise ValueError('exactly one boot required')
    markers=list(re.finditer(r'^.*\bFTMRESET,(reconnect_begin|radio_stop_begin|complete),[^\r\n]+',text,re.M))
    names=['baseline','after_reconnect','after_radio_restart','after_complete']
    expected=['reconnect_begin','radio_stop_begin','complete']
    if [marker[1] for marker in markers]!=expected[:len(markers)]:
        raise ValueError('unexpected reset marker order')
    boundaries=[0]+[marker.start() for marker in markers]+[len(text)]
    result={}
    for index,(start,end) in enumerate(zip(boundaries,boundaries[1:])):
        portion=text[start:end]
        if 'FTMDEBUG,' not in portion:
            continue
        if index: portion='FTMDEBUG_BEGIN,1\n'+portion
        result[names[index]]=analyze(portion)
    calls=re.findall(r'FTMRESET,((?:reconnect|radio_stop|radio_start)_result),(-?\d+),(\d+)',text)
    return dict(stages=result,calls=[dict(action=name,result=int(code),time_us=int(time)) for name,code,time in calls],
                completed=len(markers)==3,boots=text.count('FTMDEBUG_BEGIN'),
                disconnect_lines=[line for line in text.splitlines() if 'Disconnected' in line],
                unexpected_radio_recovery='restarting Wi-Fi driver' in text)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('log',type=Path)
    parser.add_argument('--require-complete',action='store_true')
    args=parser.parse_args()
    result=stages(args.log.read_text(errors='replace'))
    if args.require_complete:
        if not result['completed'] or len(result['calls'])!=3 or any(call['result'] for call in result['calls']):
            raise ValueError('reset test incomplete or API call failed')
        if any(name not in result['stages'] for name in ('baseline','after_reconnect','after_radio_restart')):
            raise ValueError('missing stage data')
        if result['unexpected_radio_recovery']:
            raise ValueError('unplanned application radio recovery')
        if any(group['rtt_field_disagreements'] for stage in result['stages'].values() for group in stage['statuses'].values()):
            raise ValueError('timestamp and RTT fields disagree')
        if any(stage['dropped'] or stage['panic'] for stage in result['stages'].values()):
            raise ValueError('capture drops or panic')
    print(json.dumps(result,indent=2))
