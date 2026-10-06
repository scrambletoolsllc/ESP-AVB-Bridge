#!/usr/bin/env python3
"""Summarize complete reports captured before driver buffer release."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
from statistics import median


def distribution(values):
    return dict(min=min(values), median=median(values), max=max(values)) if values else None


def parse_reports(text):
    text=re.sub(r'\x1b\[[0-9;]*m','',text)
    if text.count('FTMDEBUG_BEGIN,1')!=1:
        raise ValueError('exactly one boot required')
    reports=[]
    current=None
    for line in text.splitlines():
        header=re.search(r'\bFTMDEBUG,([^\r\n]+)',line)
        entry=re.search(r'\bFTMREJECT,([^\r\n]+)',line)
        if header:
            if current is not None: raise ValueError('incomplete report before next header')
            values=list(map(int,header[1].split(',')))
            if len(values)!=13 or not 0<=values[7]<=16: raise ValueError('bad header')
            current=dict(zip(('sequence','time_us','status','public_count','allocated','received','source','count','word72','word74','rtt_raw','rtt_est','dropped'),values))
            current['entries']=[]
            if not current['count']: reports.append(current);current=None
        elif entry:
            values=list(map(int,entry[1].split(',')))
            if len(values)!=10 or current is None: raise ValueError('orphan or malformed entry')
            sequence,index,token,rssi,rtt,t1,t2,t3,t4,ppm=values
            if sequence!=current['sequence'] or index!=len(current['entries']): raise ValueError('reordered entry')
            current['entries'].append(dict(token=token,rssi=rssi,rtt=rtt,t1=t1,t2=t2,t3=t3,t4=t4,ppm=ppm))
            if len(current['entries'])==current['count']: reports.append(current);current=None
    if not reports: raise ValueError('no complete reports')
    return reports, current is not None


def analyze(text):
    text=re.sub(r'\x1b\[[0-9;]*m','',text)
    reports, omitted = parse_reports(text)
    groups={}
    for status in sorted({report['status'] for report in reports}):
        selected=[report for report in reports if report['status']==status]
        categories=Counter()
        differences=[];rssis=[];disagreements=0;unsigned_examples=[]
        for report in selected:
            wrapped=[entry['rtt'] for entry in report['entries'] if 0x80000000<=entry['rtt']<0xffffffff]
            if wrapped:
                legacy=[entry['rtt'] for entry in report['entries'] if entry['rtt'] not in (0,0xffffffff)]
                positive=[entry['rtt'] for entry in report['entries'] if 0<entry['rtt']<0x80000000]
                unsigned_examples.append(dict(sequence=report['sequence'],fields=wrapped,
                    legacy_average_ps=sum(legacy)//len(legacy),
                    positive_average_ps=sum(positive)//len(positive) if positive else None))
            for entry in report['entries']:
                if not all(entry[key] for key in ('t1','t2','t3','t4')):
                    categories['missing_timestamp']+=1
                    continue
                if entry['t4']<entry['t1'] or entry['t3']<entry['t2']:
                    categories['backward_timestamp']+=1
                    continue
                delta=(entry['t4']-entry['t1'])-(entry['t3']-entry['t2'])
                differences.append(delta)
                rssis.append(entry['rssi'])
                categories['negative' if delta<0 else 'zero' if delta==0 else 'positive']+=1
                expected=(delta & 0xffffffff) if -25000<=delta<=10000000 else 0xffffffff
                # Aborted sessions expose partial entries before RTT classification.
                if status in (0,5): disagreements+=entry['rtt']!=expected
        groups[status]=dict(reports=len(selected),entries=sum(report['count'] for report in selected),
            sources=dict(Counter(report['source'] for report in selected)),
            public_counts=dict(Counter(report['public_count'] for report in selected)),
            timestamp_categories=dict(categories), reconstructed_rtt_ps=distribution(differences),
            rssi_dbm=distribution(rssis), rtt_field_disagreements=disagreements,
            rtt_fields_classified=status in (0,5),
            unsigned_average_affected_reports=len(unsigned_examples),
            unsigned_average_examples=unsigned_examples[:3],
            context_words=sorted({(report['word72'],report['word74']) for report in selected}))
    return dict(reports=len(reports),duration_s=(reports[-1]['time_us']-reports[0]['time_us'])/1e6,
        dropped=reports[-1]['dropped'],omitted_in_progress_report=omitted,
        statuses=groups,elf_ids=re.findall(r'ELF file SHA256:\s+(\S+)',text),
        panic=bool(re.search(r'Guru Meditation|Stack canary|Task watchdog got triggered',text)))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('log',type=Path)
    args=parser.parse_args()
    print(json.dumps(analyze(args.log.read_text(errors='replace')),indent=2))
