#!/usr/bin/env python3
"""Exercise the actual Announce selection/refresh path with native stubs."""
from pathlib import Path
import subprocess
import tempfile
component = Path('/home/dev/Development/esp_ptp')
source = (component / 'ptp.c').read_text()
def extract(start_text, end_text):
 start = source.index(start_text)
 return source[start:source.index(end_text, start)]
functions = extract('static bool is_better_clock(', '\nstatic int64_t timespec_to_ms')
functions += extract('static int64_t ptp_announce_receipt_timeout_ns(', '\n/* Check if')
functions += extract('static int ptp_process_announce(', '\nstatic void ptp_lock_local_clock_freq')
harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "ptp.h"
#include "ptp_sync_receipt.h"
#include "ptp_path_trace.h"
#include "ptp_wifi_neighbor.h"
#include "ptp_capable_receive.h"
#define portENTER_CRITICAL(lock) ((void)0)
#define portEXIT_CRITICAL(lock) ((void)0)
#define ptp_port_medium_wifi_ftm 2
#define ptp_port_wifi_mode_sta 1
#define FAR
#define OK 0
#define CONFIG_ESP_PTP_ANNOUNCE_INTERVAL_MS 1000
#define CONFIG_ESP_PTP_SYNC_INTERVAL_MS 125
static int64_t receipt_now=1000;
static int64_t esp_timer_get_time(void){return receipt_now;}
#define ptpinfo(...) ((void)0)
#define ESP_LOG_BUFFER_HEX_LEVEL(...) ((void)0)
struct ptp_state_s {
 bool selected_source_valid, gptp;
 struct ptp_announce_s own_identity, selected_source;
 ptp_path_trace_t selected_path;
 struct timespec last_selected_announce;
 struct { struct timespec last_received_announce, last_received_sync, delayreq_time;
 int medium,wifi_mode;bool rx_source_mac_valid;uint8_t rx_source_mac[6];
 uint32_t rx_association;ptp_wifi_neighbor_t wifi_neighbor;ptp_capable_receive_t capable_receive;
 ptp_sync_receipt_t sync_receipt;bool twostep_pending; int path_delay_avgcount, path_delay_ns, peer_delay_avgcount, peer_delay_ns; } port[1];
 double correction_ns;
};
static unsigned invalidations;
static bool ptp_is_gptp(struct ptp_state_s *state) { return state->gptp; }
static void ptp_invalidate_timing(void) { ++invalidations; }
'''
checks = r'''
int main(void) {
 struct ptp_state_s state = {.gptp=true};
 state.own_identity.btc_priority1 = 200;
 state.own_identity.header.sourceidentity[0] = 3;
 struct ptp_announce_s announce = {0};
 announce.header.messagetype = PTP_MSGTYPE_ANNOUNCE;
 announce.header.messagelength[1] = sizeof(announce);
 announce.header.sourceidentity[0] = 2;
 announce.header.sourceportindex[1] = 2;
 announce.btc_identity[0] = 1;
 announce.btc_priority1 = 100;
 announce.pathtracetlv.type[1] = 8;
 announce.pathtracetlv.length[1] = 8;
 announce.pathtracetlv.pathsequence[0] = 1;
 assert(ptp_process_announce(&state, &announce, sizeof(announce)) == OK);
 assert(invalidations == 1 && state.selected_source.btc_priority1 == 100);
 assert(state.selected_path.count == 1 && state.selected_path.identities[0][0] == 1);
 assert(state.port[0].sync_receipt.armed && state.port[0].sync_receipt.received_us==receipt_now);
 state.selected_source_valid = true;
 receipt_now+=100000;ptp_process_announce(&state,&announce,sizeof(announce));
 assert(state.port[0].sync_receipt.received_us==1000); /* Repeated Announce does not renew Sync. */

 state.port[0].medium=2;state.port[0].wifi_mode=1;
 uint8_t ap[6]={2,1,2,3,4,5};
 ptp_wifi_neighbor_associate(&state.port[0].wifi_neighbor,ap);
 memcpy(state.port[0].rx_source_mac,ap,6);state.port[0].rx_source_mac_valid=true;
 state.port[0].rx_association=state.port[0].wifi_neighbor.association;
 ptp_process_announce(&state,&announce,sizeof(announce));
 assert(state.port[0].wifi_neighbor.bound);
 assert(state.port[0].wifi_neighbor.port_identity[0]==2);
 assert(state.port[0].wifi_neighbor.port_identity[9]==2);
 ptp_wifi_neighbor_associate(&state.port[0].wifi_neighbor,ap);
 struct ptp_state_s before_stale=state;
 ptp_process_announce(&state,&announce,sizeof(announce));
 assert(!state.port[0].wifi_neighbor.bound); /* Old receive association. */
 assert(!memcmp(&state,&before_stale,sizeof(state))); /* It cannot refresh or replace selection. */
 state.port[0].rx_association=state.port[0].wifi_neighbor.association;
 announce.btc_priority1=250;announce.header.sourceidentity[0]=99; /* Neighbor identity is independent of clock selection. */
 ptp_process_announce(&state,&announce,sizeof(announce));
 assert(state.port[0].wifi_neighbor.bound);
 assert(state.port[0].wifi_neighbor.port_identity[0]==99);
 assert(state.selected_source.header.sourceidentity[0]==2);
 announce.btc_priority1=100;announce.header.sourceidentity[0]=2;
 ptp_process_announce(&state,&announce,sizeof(announce));
 state.port[0].medium=0;

 announce.utcoffset[1] = 37;
 announce.btc_priority1 = 110; /* Same source quality worsens but still beats own. */
 ptp_process_announce(&state, &announce, sizeof(announce));
 assert(invalidations == 1 && state.selected_source.utcoffset[1] == 37);
 assert(state.selected_source.btc_priority1 == 110);
 assert(state.port[0].sync_receipt.received_us==receipt_now);
 struct timespec selected_time = state.last_selected_announce;
 announce.header.sourceidentity[0] = 4;
 announce.btc_priority1 = 150;
 ptp_process_announce(&state, &announce, sizeof(announce));
 assert(!memcmp(&selected_time, &state.last_selected_announce, sizeof(selected_time)));
 assert(state.selected_source.header.sourceidentity[0] == 2);
 announce.header.sourceidentity[0] = 2;
 announce.btc_priority1 = 100;
 announce.pathtracetlv.pathsequence[0] = 3; /* Loop through this clock. */
 ptp_process_announce(&state, &announce, sizeof(announce));
 assert(invalidations == 1);
 assert(!memcmp(&selected_time, &state.last_selected_announce, sizeof(selected_time)));
 announce.pathtracetlv.pathsequence[0] = 5;
 announce.btc_identity[0] = 5; /* Same peer, different selected root. */
 ptp_process_announce(&state, &announce, sizeof(announce));
 assert(invalidations == 2 && state.selected_source.btc_identity[0] == 5);
 announce.btc_priority1 = 250;
 ptp_process_announce(&state, &announce, sizeof(announce));
 assert(invalidations == 3 && !state.selected_source_valid && !state.selected_path.count);
 announce.btc_priority1 = 100;
 ptp_process_announce(&state, &announce, 40);
 assert(invalidations == 3);
 announce.header.messagelength[1] = 64;
 ptp_process_announce(&state, &announce, sizeof(announce));
 assert(invalidations == 4 && state.selected_path.count == 0); /* Optional path absent. */
 state.selected_source_valid=true;
 selected_time=state.last_selected_announce;
 memcpy(announce.header.sourceidentity,state.own_identity.header.sourceidentity,8);
 ptp_process_announce(&state,&announce,sizeof(announce));
 assert(invalidations==4 && !memcmp(&selected_time,&state.last_selected_announce,sizeof(selected_time)));
 announce.header.sourceidentity[0]=2;
 for(unsigned steps=255;steps<=65535;++steps) {
  announce.stepsremoved[0]=steps>>8;announce.stepsremoved[1]=steps;
  ptp_process_announce(&state,&announce,sizeof(announce));
  assert(invalidations==4 && !memcmp(&selected_time,&state.last_selected_announce,sizeof(selected_time)));
 }
 announce.stepsremoved[0]=0;announce.stepsremoved[1]=254;
 ptp_process_announce(&state,&announce,sizeof(announce));
 assert(state.selected_source.stepsremoved[1]==254 && invalidations==4);
 state.selected_source_valid=false;
 state.gptp = false;
 ptp_process_announce(&state, &announce, sizeof(announce));
 assert(invalidations == 5 && state.selected_path.count == 0);
 announce.header.logmessageinterval = 0;
 assert(ptp_announce_receipt_timeout_ns(&announce) == INT64_C(3000000000));
 announce.header.logmessageinterval = 1;
 assert(ptp_announce_receipt_timeout_ns(&announce) == INT64_C(6000000000));
 announce.header.logmessageinterval = (uint8_t)-3;
 assert(ptp_announce_receipt_timeout_ns(&announce) == INT64_C(375000000));
 announce.header.logmessageinterval = 0x7f;
 assert(ptp_announce_receipt_timeout_ns(&announce) == INT64_C(3000000000));
 puts("Announce refresh, foreign-source isolation, root change, loop and timeout cases passed");
}
'''
with tempfile.TemporaryDirectory() as work:
 path = Path(work) / 'test.c'; binary = Path(work) / 'test'
 path.write_text(harness + functions + checks)
 subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-g', '-I', str(component), str(path), '-o', str(binary)], check=True)
 subprocess.run([str(binary)], check=True)
