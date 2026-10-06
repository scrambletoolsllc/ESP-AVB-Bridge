#!/usr/bin/env python3
"""Join verified responder input fields to initiator quartets and RX metadata."""
import argparse,csv,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ftm_failure_probe'))
from analyze import parse_reports,distribution
from analyze_paired import parse_responder,ticks_to_ps
from analyze_rate import measure
from analyze_rxmeta import reconstruct
from analyze_fields import decode

def join(endpoint,responder):
    lookup={}
    for boot,portion in enumerate(responder.split('FTMRESP_BEGIN,1')[1:],1):
        if 'FTMRESP,' not in portion:continue
        fields={}
        for match in re.finditer(r'\bFTMRESPMETA,([^\r\n]+)',portion):
            values=list(map(int,match[1].split(',')))
            if len(values)!=8:raise ValueError('incorrect metadata schema')
            if values[0] in fields:raise ValueError('duplicate metadata')
            fields[values[0]]=values
        for record in parse_responder('FTMRESP_BEGIN,1'+portion):
            if not record['raw_t1'] or not record['raw_t4']:continue
            values=fields.get(record['sequence'])
            if not values or values[2]!=1 or values[3]:continue
            decoded=decode(values[4:7])
            if decoded['tx_ticks']!=record['raw_t1'] or decoded['rx_ticks']!=record['raw_t4']:
                raise ValueError('raw reconstruction differs')
            if ticks_to_ps(record['raw_t1']+record['compensation'])!=record['t1'] or ticks_to_ps(record['raw_t4'])!=record['t4']:
                raise ValueError('converted timestamp differs')
            lookup.setdefault((record['t1']%(1<<48),record['t4']%(1<<48)),[]).append((boot,record,decoded))
    local={}
    for match in re.finditer(r'\bFTMRXMETA,([0-9,]+)',endpoint):
        fields=list(map(int,match[1].split(',')))
        if len(fields)!=9:raise ValueError('incorrect endpoint metadata')
        local[tuple(fields[:2])]=fields
    reports,_=parse_reports(endpoint);rows=[];excluded={}
    for report in reports:
        try:rate=measure(report)['receive_rate_ppm']/1e6
        except ValueError:rate=None
        for index,entry in enumerate(report['entries']):
            if not all(entry[key] for key in ('t1','t2','t3','t4')):
                excluded['missing_timestamp']=excluded.get('missing_timestamp',0)+1;continue
            matches=lookup.get((entry['t1'],entry['t4']),[])
            if len(matches)!=1:raise ValueError('missing or ambiguous verified remote fields')
            boot,record,decoded=matches[0]
            if record['token']!=entry['token']:raise ValueError('token mismatch')
            fields=local.get((report['sequence'],index))
            if fields is None:raise ValueError('missing local fields')
            local_t2,local_t3,raw_ok=reconstruct(fields,report['word74'])
            if not raw_ok or local_t2!=entry['t2'] or local_t3!=entry['t3']:
                raise ValueError('local reconstruction differs')
            correction=fields[6] if fields[6]<=1023 else 2048-fields[6]
            raw=(entry['t4']-entry['t1'])%(1<<48)-(entry['t3']-entry['t2'])
            fine_ticks=(8*(decoded['rx_phase']-decoded['tx_phase']-fields[8]+fields[5])
                        +decoded['correction']+correction-16384
                        -record['compensation']-report['word74'])
            residual=(raw-fine_ticks*1562.5+500000)%1000000-500000
            if abs(residual)>2:raise ValueError('combined fine-field RTT identity differs')
            rows.append(dict(report=report['sequence'],time_us=report['time_us'],status=report['status'],index=index,responder_boot=boot,token=entry['token'],raw_rtt_ps=raw,rate_ppm=rate*1e6 if rate is not None else None,adjusted_rtt_ps=raw-rate*(entry['t3']-entry['t2']) if rate is not None else None,remote_correction_ticks=decoded['correction'],local_correction_ticks=correction,remote_rx_minus_tx_phase=(decoded['rx_phase']-decoded['tx_phase'])%80,local_tx_minus_rx_phase=(fields[8]-fields[5])%80,remote_compensation=record['compensation'],local_compensation=report['word74'],endpoint_rssi=entry['rssi'],responder_rssi=record['rssi']))
    summary={}
    for status in sorted({row['status'] for row in rows}):
        selected=[row for row in rows if row['status']==status]
        summary[status]=dict(entries=len(selected))
        for key in ('raw_rtt_ps','adjusted_rtt_ps','remote_correction_ticks','local_correction_ticks','remote_rx_minus_tx_phase','local_tx_minus_rx_phase','endpoint_rssi','responder_rssi'):
            summary[status][key]=distribution([row[key] for row in selected if row[key] is not None])
    return rows,dict(statuses=summary,excluded=excluded)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('endpoint',type=Path);parser.add_argument('responder',type=Path);parser.add_argument('csv',type=Path);args=parser.parse_args()
    rows,summary=join(args.endpoint.read_text(errors='replace'),args.responder.read_text(errors='replace'))
    with args.csv.open('w') as output:
        writer=csv.DictWriter(output,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps(summary,indent=2))
