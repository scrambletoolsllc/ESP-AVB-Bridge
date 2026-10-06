#!/usr/bin/env python3
"""Exercise actual source expiry with advertised intervals and independent Sync freshness."""
from pathlib import Path
import subprocess
import tempfile
component = Path('/home/dev/Development/esp_ptp')
source = (component / 'ptp.c').read_text()
start = source.index('static int64_t ptp_announce_receipt_timeout_ns(')
body = source[start:source.index('\nbool ptpd_ftm_source_observed(', start)]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <time.h>
#include "ptp.h"
#include "ptp_sync_receipt.h"
#define FAR
#define CONFIG_ESP_PTP_ANNOUNCE_INTERVAL_MS 1000
#define CONFIG_ESP_PTP_TIMEOUT_MS 10000
#define ptp_port_medium_eth_hwts 1
#define ESP_LOGD(...) ((void)0)
struct ptp_state_s {
 bool gptp, capable;
 struct {int medium; struct timespec last_received_sync;ptp_sync_receipt_t sync_receipt;} port[1];
 struct ptp_announce_s selected_source;
 struct timespec last_selected_announce;
};
static struct timespec now;
static int64_t esp_timer_get_time(void){return now.tv_sec*INT64_C(1000000)+now.tv_nsec/1000;}
static bool ptp_is_gptp(struct ptp_state_s *state){return state->gptp;}
static bool ptp_wired_capability(struct ptp_state_s *state){return state->capable;}
static int64_t timespec_delta_ns(const struct timespec *later,const struct timespec *earlier){
 return (later->tv_sec-earlier->tv_sec)*INT64_C(1000000000)+later->tv_nsec-earlier->tv_nsec;
}
static int fake_clock_gettime(int clock_id,struct timespec *result){(void)clock_id;*result=now;return 0;}
#define clock_gettime fake_clock_gettime
static void clock_timespec_subtract(const struct timespec *later,const struct timespec *earlier,struct timespec *delta){
 int64_t difference=timespec_delta_ns(later,earlier);
 delta->tv_sec=difference/1000000000;delta->tv_nsec=difference%1000000000;
}
static int64_t timespec_to_ms(const struct timespec *value){return value->tv_sec*1000+value->tv_nsec/1000000;}
static struct timespec from_ns(int64_t value){return (struct timespec){value/1000000000,value%1000000000};}
'''
checks = r'''
int main(void){
 struct ptp_state_s state={.gptp=true,.capable=true};state.port[0].medium=1;
 state.port[0].sync_receipt=(ptp_sync_receipt_t){.armed=true,.interval_us=INT64_MAX};
 state.selected_source.header.messagetype=PTP_MSGTYPE_ANNOUNCE|0x10;
 state.last_selected_announce=from_ns(1000000000);
 for(int logarithm=-24;logarithm<=24;++logarithm){
  state.selected_source.header.logmessageinterval=(uint8_t)logarithm;
  int64_t expected=logarithm>=0?INT64_C(3000000000)<<logarithm:
   (INT64_C(3000000000)+(INT64_C(1)<<-logarithm)-1)/(INT64_C(1)<<-logarithm);
  assert(ptp_announce_receipt_timeout_ns(&state.selected_source)==expected);
  now=from_ns(999999999+expected);state.port[0].last_received_sync=now;
  assert(is_selected_source_valid(&state));
  now=from_ns(1000000000+expected);state.port[0].last_received_sync=now;
  assert(!is_selected_source_valid(&state)); /* Sync cannot renew expired Announce. */
 }
 state.selected_source.header.logmessageinterval=0;
 now=from_ns(999999999);state.port[0].last_received_sync=now;
 assert(!is_selected_source_valid(&state));
 now=from_ns(1000000000);assert(is_selected_source_valid(&state));
 state.capable=false;assert(!is_selected_source_valid(&state));state.capable=true;
 state.selected_source.header.messagetype=0;assert(!is_selected_source_valid(&state));
 state.selected_source.header.messagetype=PTP_MSGTYPE_ANNOUNCE|0x10;
 for(int logarithm=-128;logarithm<=127;++logarithm){
  if(logarithm>=-24 && logarithm<=24)continue;
  state.selected_source.header.logmessageinterval=(uint8_t)logarithm;
  assert(ptp_announce_receipt_timeout_ns(&state.selected_source)==3000000000);
 }
 state.selected_source.header.logmessageinterval=0;
 state.last_selected_announce=from_ns(2000000000);
 ptp_sync_receipt_start(&state.port[0].sync_receipt,2000000,375000);
 now=from_ns(2374999000);assert(is_selected_source_valid(&state));
 now=from_ns(2375000000);assert(!is_selected_source_valid(&state));
 state.last_selected_announce=now;assert(!is_selected_source_valid(&state));
 state.selected_source.btc_priority1=255;assert(is_selected_source_valid(&state));
 state.selected_source.btc_priority1=248;
 assert(ptp_sync_receipt_observe(&state.port[0].sync_receipt,2375000,-3,2375000));
 assert(is_selected_source_valid(&state));
 puts("Actual source timeout: all supported rates, exact expiry boundary, negative age, qualification, and Sync independence passed");
}
'''
with tempfile.TemporaryDirectory() as temporary:
    path = Path(temporary)
    (path/'test.c').write_text(harness+body+checks)
    subprocess.run(['cc','-std=c11','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined','-I',str(component),str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
