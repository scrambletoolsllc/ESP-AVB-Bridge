#!/usr/bin/env python3
"""Verify post-callback slot reads against exact original responder timestamps."""
import argparse,json,re,sys
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ftm_failure_probe'))
from analyze_paired import parse_responder
from statistics import median

def distribution(values):
    return dict(min=min(values),median=median(values),max=max(values)) if values else None

def decode(words):
    tx_coarse,shared,rx_word=words
    tx_phase=shared&127
    rx_coarse=(shared&0xffffc000)|(rx_word>>18)
    rx_phase=rx_word&127
    encoded=(rx_word>>7)&2047
    correction=2048-encoded if encoded&1024 else encoded
    return dict(tx_ticks=((tx_coarse*80+tx_phase-640)*8)%(1<<64),
                rx_ticks=(rx_coarse*640-13312+rx_phase*8+correction)%(1<<64),
                tx_phase=tx_phase,rx_phase=rx_phase,correction=correction)

def analyze(text):
    groups=[]
    for portion in text.split('FTMRESP_BEGIN,1')[1:]:
        if 'FTMRESP,' not in portion:continue
        records=parse_responder('FTMRESP_BEGIN,1'+portion)
        metadata={}
        for match in re.finditer(r'\bFTMRESPMETA,([^\r\n]+)',portion):
            values=list(map(int,match[1].split(',')))
            if len(values)!=8 or values[0] in metadata:raise ValueError('bad metadata record')
            metadata[values[0]]=values
        counters=Counter();times=[];corrections=[];phase_delta=Counter();tx_phase=Counter();rx_phase=Counter()
        for record in records:
            if not record['raw_t1'] or not record['raw_t4']:
                counters['missing_original_timestamp']+=1;continue
            values=metadata.get(record['sequence'])
            if values is None:
                counters['missing_metadata']+=1;continue
            _,slot,matches,unstable,*fields=values
            words=fields[:3];times.append(fields[3])
            if unstable:counters['unstable']+=1
            if matches!=1 or slot>=16:
                counters['nonunique_or_absent_slot']+=1;continue
            decoded=decode(words)
            if decoded['tx_ticks']!=record['raw_t1'] or decoded['rx_ticks']!=record['raw_t4']:
                counters['reconstruction_error']+=1;continue
            counters['verified']+=1
            corrections.append(decoded['correction'])
            tx_phase[decoded['tx_phase']]+=1;rx_phase[decoded['rx_phase']]+=1
            phase_delta[(decoded['rx_phase']-decoded['tx_phase'])%80]+=1
        groups.append(dict(records=len(records),counts=dict(counters),scan_us=distribution(times),correction_ticks=distribution(corrections),tx_phase=dict(tx_phase),rx_phase=dict(rx_phase),rx_minus_tx_phase_mod80=dict(phase_delta)))
    if not groups:raise ValueError('no responder records')
    return dict(boots=groups)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('log',type=Path);args=parser.parse_args()
    print(json.dumps(analyze(args.log.read_text(errors='replace')),indent=2))
