#!/usr/bin/env python3
"""Exercise actual complete Follow_Up admission and Sync receipt renewal."""
from pathlib import Path
import subprocess,tempfile
component=Path('/home/dev/Development/esp_ptp');source=(component/'ptp.c').read_text()
start=source.index('static int ptp_process_sync(');body=source[start:source.index('\nstatic int ptp_process_delay_req(',start)]
harness=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "ptp.h"
#include "ptp_sync_receipt.h"
#include "ptp_timing_snapshot.h"
#define FAR
#define OK 0
#define ptpwarn(...) ((void)0)
#define ptpdebug(...) ((void)0)
#define ESP_LOGD(...) ((void)0)
#define portENTER_CRITICAL(lock) ((void)0)
#define portEXIT_CRITICAL(lock) ((void)0)
struct ptp_state_s {
 bool selected_source_valid,gptp;struct ptp_announce_s own_identity,selected_source;
 int64_t correction_ns;int32_t freq_trim_ppb;struct {int32_t drift_acc;} offset_pi;
 struct {bool twostep_pending;int64_t twostep_received_us;struct ptp_sync_s twostep_packet;
 struct timespec twostep_rxtime,rxtime,last_received_sync;int32_t peer_delay_ns;ptp_sync_receipt_t sync_receipt;} port[1];
};
static ptp_timing_snapshot_t s_timing_snapshot={.generation=1};
static bool s_use_sw_clock,step;static unsigned updates;static int update_result;
static int64_t now_us=200000;
static int64_t esp_timer_get_time(void){return now_us;}
static int fake_clock_gettime(int clock_id,struct timespec *stamp){(void)clock_id;*stamp=(struct timespec){now_us/1000000,(now_us%1000000)*1000};return 0;}
#define clock_gettime fake_clock_gettime
static bool ptp_is_gptp(struct ptp_state_s *state){return state->gptp;}
static uint16_t ptp_get_sequence(const struct ptp_header_s *header){return (header->sequenceid[0]<<8)|header->sequenceid[1];}
static void ptp_format_to_timespec(const uint8_t *wire,struct timespec *stamp){(void)wire;*stamp=(struct timespec){100,0};}
static int64_t timespec_to_ns(const struct timespec *stamp){return stamp->tv_sec*INT64_C(1000000000)+stamp->tv_nsec;}
static int64_t get_correction_ns(const uint8_t *wire){(void)wire;return 0;}
bool ptpd_timing_snapshot(ptp_timing_snapshot_t *snapshot){*snapshot=s_timing_snapshot;return snapshot->valid;}
static int ptp_update_local_clock(struct ptp_state_s *state,const struct timespec *remote,const struct timespec *local){
 (void)state;(void)remote;(void)local;++updates;if(step)++s_timing_snapshot.generation;return update_result;
}
'''
checks=r'''
int main(void){
 struct ptp_state_s state={.gptp=true,.selected_source_valid=true};
 state.port[0].twostep_packet.header.logmessageinterval=(uint8_t)-3;
 state.port[0].twostep_packet.header.sourceidentity[0]=2;
 state.port[0].twostep_packet.header.sourceportindex[1]=1;
 state.port[0].twostep_packet.header.sequenceid[1]=9;
 state.port[0].twostep_rxtime.tv_sec=100;
 ptp_sync_receipt_start(&state.port[0].sync_receipt,0,375000);
 struct ptp_follow_up_s message={0};message.header=state.port[0].twostep_packet.header;
 message.header.messagetype=0x18;message.header.version=2;message.header.messagelength[1]=76;
 uint8_t *wire=(uint8_t*)&message;
 wire[45]=3;wire[47]=28;wire[49]=0x80;wire[50]=0xc2;wire[53]=1;
 assert(ptp_timing_payload_valid(wire,sizeof(message)));
 ptp_process_followup(&state,&message);assert(!updates); /* Sync alone cannot renew. */
 state.selected_source.header=state.port[0].twostep_packet.header;
 struct ptp_sync_s sync=state.port[0].twostep_packet;sync.header.flags[0]=PTP_FLAGS0_TWOSTEP;
 ptp_process_sync(&state,&sync);
 assert(state.port[0].twostep_pending && !updates && state.port[0].sync_receipt.received_us==0);
 message.header.sequenceid[1]=8;ptp_process_followup(&state,&message);assert(!updates);
 message.header.sequenceid[1]=9;message.header.sourceportindex[1]=2;
 ptp_process_followup(&state,&message);assert(!updates);message.header.sourceportindex[1]=1;
 wire[53]=2;ptp_process_followup(&state,&message);assert(!updates && !state.port[0].sync_receipt.received_us);wire[53]=1;
 state.port[0].twostep_packet.header.logmessageinterval=127;
 ptp_process_followup(&state,&message);assert(!updates);state.port[0].twostep_packet.header.logmessageinterval=(uint8_t)-3;
 ptp_process_followup(&state,&message);assert(updates==1 && !state.port[0].twostep_pending);
 assert(state.port[0].sync_receipt.received_us==now_us && state.port[0].sync_receipt.interval_us==375000);
 now_us=300000;state.port[0].twostep_pending=true;update_result=-1;
 ptp_process_followup(&state,&message);assert(updates==2 && state.port[0].sync_receipt.received_us==200000);
 update_result=0;step=true;state.port[0].twostep_pending=true;
 ptp_process_followup(&state,&message);assert(updates==3 && state.port[0].sync_receipt.received_us==300000);
 puts("Actual Follow_Up: pending pair, identity, sequence, information TLV, interval, servo failure and clock-step renewal passed");
}
'''
with tempfile.TemporaryDirectory() as temporary:
 path=Path(temporary);(path/'test.c').write_text(harness+body+checks)
 subprocess.run(['cc','-std=c11','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(component),'-I',str(component/'include'),str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
