#!/usr/bin/env python3
"""Exercise the actual local-root publisher and separate snapshot readers."""
from pathlib import Path
import subprocess
import tempfile
component = Path('/home/dev/Development/esp_ptp')
source = (component/'ptp.c').read_text()
readers = source[source.index('static void ptp_invalidate_timing('):source.index('/* Hardware PTP clock backend')]
publisher = source[source.index('static void ptp_publish_local_source('):source.index('/* Send PTP server synchronization packet */')]
harness = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "ptp.h"
#include "include/ptp_timing_snapshot.h"
#define FAR
#define OK 0
#define portENTER_CRITICAL(lock) ((void)0)
#define portEXIT_CRITICAL(lock) ((void)0)
static ptp_timing_snapshot_t s_timing_snapshot, s_local_source_snapshot;
static bool s_use_sw_clock;
static int64_t now_us=1000000;
static int clock_result;
struct ptp_state_s {bool gptp,selected_source_valid;struct ptp_announce_s own_identity;int32_t freq_trim_ppb;};
static int64_t esp_timer_get_time(void){return now_us;}
static bool ptp_is_gptp(struct ptp_state_s *state){return state->gptp;}
static int ptp_gettime(struct ptp_state_s *state,struct timespec *stamp){(void)state;*stamp=(struct timespec){123,456};return clock_result;}
static int64_t timespec_to_ns(const struct timespec *stamp){return stamp->tv_sec*INT64_C(1000000000)+stamp->tv_nsec;}
static void timespec_to_ptp_format(const struct timespec *stamp,uint8_t *output){
 uint64_t seconds=stamp->tv_sec;for(int index=5;index>=0;--index){output[index]=seconds;seconds>>=8;}
 uint32_t fraction=stamp->tv_nsec;for(int index=9;index>=6;--index){output[index]=fraction;fraction>>=8;}
}
static void ptp_marshal_follow_up_for_beacon_ie(struct ptp_state_s *state,struct ptp_follow_up_s *message,int port){
 (void)state;assert(port==0);memset(message,0,sizeof(*message));message->header.messagetype=0x18;
}
'''
checks = r'''
int main(void){
 struct ptp_state_s state={.gptp=true,.freq_trim_ppb=1234};
 state.own_identity.btc_priority1=248;state.own_identity.btc_identity[0]=9;
 state.own_identity.header.sourceidentity[0]=9;
 ptp_timing_snapshot_t actual;
 assert(!ptpd_time_source_snapshot(NULL));assert(!ptpd_time_source_snapshot(&actual));
 ptp_publish_local_source(&state);assert(ptpd_time_source_snapshot(&actual));
 assert(actual.generation==1 && actual.reference_ns==123000000456 && actual.local_receive_ns==actual.reference_ns);
 assert(actual.offset_ns==0 && actual.correction_ns==0 && actual.peer_delay_ns==0 && actual.hardware_clock);
 assert(actual.btc_identity[0]==9 && actual.own_identity[0]==9 && actual.trim_ppb==1234);
 assert(actual.follow_up[0]==0x18 && actual.follow_up[39]==123 && actual.follow_up[42]==1 && actual.follow_up[43]==200);
 assert(!ptpd_timing_snapshot(&actual)); /* Local timing must not masquerade as received Sync. */
 now_us=1500000;assert(ptpd_time_source_snapshot(&actual));
 now_us=1500001;assert(!ptpd_time_source_snapshot(&actual));
 now_us=999999;assert(!ptpd_time_source_snapshot(&actual));now_us=2000000;
 ptp_publish_local_source(&state);ptp_invalidate_timing();assert(!ptpd_time_source_snapshot(&actual));
 state.selected_source_valid=true;
 s_timing_snapshot=(ptp_timing_snapshot_t){.generation=2,.received_us=now_us,.reference_ns=999,.valid=true};
 ptp_publish_local_source(&state);assert(ptpd_time_source_snapshot(&actual) && actual.reference_ns==999);
 now_us+=500001;assert(!ptpd_time_source_snapshot(&actual)); /* Sync loss alone cannot invent a root. */
 ptp_invalidate_timing();state.selected_source_valid=false;ptp_publish_local_source(&state);
 assert(ptpd_time_source_snapshot(&actual) && actual.generation==3 && actual.reference_ns==123000000456);
 state.own_identity.btc_priority1=255;ptp_publish_local_source(&state);assert(!ptpd_time_source_snapshot(&actual));
 state.own_identity.btc_priority1=248;s_use_sw_clock=true;ptp_publish_local_source(&state);assert(!ptpd_time_source_snapshot(&actual));
 s_use_sw_clock=false;state.gptp=false;ptp_publish_local_source(&state);assert(!ptpd_time_source_snapshot(&actual));
 state.gptp=true;clock_result=-1;ptp_publish_local_source(&state);assert(!ptpd_time_source_snapshot(&actual));
 puts("Actual local-root publisher: identity, timestamps, retained trim, separate upstream validity, freshness, handover, eligibility and read failure passed");
}
'''
with tempfile.TemporaryDirectory() as temporary:
    path=Path(temporary)
    (path/'test.c').write_text(harness+readers+publisher+checks)
    subprocess.run(['cc','-std=c11','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(component),str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
