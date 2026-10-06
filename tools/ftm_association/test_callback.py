#!/usr/bin/env python3
"""Compile the actual FTM selection/emission block with the production emitter."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
source=(root/'components/ftm_clock_probe/ftm_clock_probe.c').read_text()
start=source.index('#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP',source.index('static IRAM_ATTR int capture_frame('))
body=source[start+len('#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP'):source.index('#else',start)]
helper_start=source.index('/* Per-port Follow_Up sequenceId pools')
helper=source[helper_start:source.index('#endif',helper_start)]
harness=r'''
#include <assert.h>
#include <stdio.h>
#include "ftm_radio_association.h"
#include "ftm_follow_up_tx.h"
#define TX_SNAPSHOT_COUNT 8
#define portENTER_CRITICAL_ISR(lock) ((void)0)
#define portEXIT_CRITICAL_ISR(lock) ((void)0)
#define IRAM_ATTR
static int64_t now=300;
static int64_t esp_timer_get_time(void){return now;}
static ftm_radio_association_t radio_associations;
static ftm_association_state_t association_map;
static uint32_t admitted_radio_generation,tx_next,tx_valid_frames,tx_invalid_frames;
static ftm_follow_up_tx_t tx_snapshots[8];
static int64_t tx_prepared_us[8];
'''
checks=r'''
int main(void){
 ftm_association_packet_t packet={.host_boot=1,.radio_boot=2,.publication=1,.count=2,.clock_identity={2},
 .entries={{.mac={2,1},.port_number=2,.association=3},{.mac={2,2},.port_number=18,.association=4}}};
 ftm_radio_association_change(&radio_associations,packet.entries[0].mac,true);
 uint32_t generation=ftm_radio_association_change(&radio_associations,packet.entries[1].mac,true);
 ftm_radio_association_forwarded(&radio_associations,generation,true);
 assert(ftm_association_apply(&association_map,&packet,1,2,100));
 admitted_radio_generation=generation;
 tx_snapshots[0]=(ftm_follow_up_tx_t){.valid=true,.anchor_ps=1000000,.not_before_ps=1000000,
 .expires_us=1000,.rate_q32=INT64_C(4294967296)};
 tx_snapshots[0].ie[2]=0;tx_snapshots[0].ie[3]=0x80;tx_snapshots[0].ie[4]=0xc2;
 tx_prepared_us[0]=200;tx_next=1;
 uint8_t output[84];memset(output,0xa5,sizeof(output));uint16_t length=82;
 assert(!emit(packet.entries[0].mac,1000000,7,output,&length));
 assert(length==82 && output[26]==2 && output[35]==2 && output[36]==0 && output[37]==1 && output[82]==0xa5);
 length=82;assert(!emit(packet.entries[1].mac,1000000,8,output,&length));assert(output[35]==18 && output[36]==0 && output[37]==1);
 length=82;assert(!emit(packet.entries[0].mac,1000000,9,output,&length));assert(output[35]==2 && output[37]==2);
 length=82;assert(!emit(packet.entries[1].mac,1000000,9,output,&length));assert(output[35]==18 && output[37]==2);
 packet.entries[0].sync_stopped=true;packet.entries[0].sync_revision=1;packet.publication++;
 assert(ftm_association_apply(&association_map,&packet,1,2,250));
 length=82;assert(emit(packet.entries[0].mac,1000000,8,output,&length));
 length=82;assert(!emit(packet.entries[1].mac,1000000,8,output,&length));
 packet.entries[0].sync_stopped=false;packet.entries[0].sync_revision=2;packet.publication++;
 assert(ftm_association_apply(&association_map,&packet,1,2,260));
 length=82;assert(emit(packet.entries[0].mac,1000000,8,output,&length));
 tx_prepared_us[0]=270;
 length=82;assert(!emit(packet.entries[0].mac,1000000,8,output,&length));
 uint8_t unknown[6]={2,3};length=82;assert(emit(unknown,1000000,8,output,&length));
 length=82;assert(emit(packet.entries[0].mac,999999,8,output,&length));
 tx_prepared_us[0]=100;length=82;assert(emit(packet.entries[0].mac,1000000,8,output,&length));
 tx_prepared_us[0]=200;now=1000100;length=82;assert(emit(packet.entries[0].mac,1000000,8,output,&length));
 now=300;ftm_radio_association_change(&radio_associations,packet.entries[0].mac,true);
 length=82;assert(emit(packet.entries[0].mac,1000000,8,output,&length));
 assert(tx_valid_frames==6 && tx_invalid_frames==7);
 puts("Actual FTM callback: per-peer identity, unknown peer, old timestamp, activation, map expiry and radio epoch retirement passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)
    (path/'test.c').write_text(harness+helper+'static int emit(const uint8_t peer[6],uint64_t departure,uint8_t followup,uint8_t *buffer,uint16_t *length){'+body+'}\n'+checks)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    '-I',str(root/'components/ftm_clock_probe'),'-I',str(root/'components/ftm_follow_up/include'),
                    str(path/'test.c'),str(root/'components/ftm_follow_up/ftm_follow_up_tx.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
