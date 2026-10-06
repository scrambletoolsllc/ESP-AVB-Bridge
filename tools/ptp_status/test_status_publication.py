#!/usr/bin/env python3
"""Exercise actual daemon status publication through ready/holdover/source loss."""
from pathlib import Path
import subprocess
import tempfile
component = Path('/home/dev/Development/esp_ptp')
source = (component/'ptp.c').read_text()
start = source.index('/* 12.4 for the STA port: media support')
function = source[start:source.index('\n/* Main PTPD task */', start)]
harness = r'''
#include <assert.h>
#define FAR
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <semaphore.h>
#include "esp_ptp.h"
#include "ptp.h"
#include "ptp_timing_snapshot.h"
#include "ptp_status_path.h"
#include "ptp_peer_exchange.h"
#include "ptp_peer_capability.h"
#include "ptp_capable_receive.h"
#include "ptp_peer_rate.h"
#include "ptp_wifi_neighbor.h"
#include "ptp_wifi_capable.h"
#define portENTER_CRITICAL(lock) ((void)0)
#define portEXIT_CRITICAL(lock) ((void)0)
#ifndef CONFIG_ESP_PTP_DOMAIN
#define CONFIG_ESP_PTP_DOMAIN 0
#endif
static int64_t current_us=1000000;
static int64_t esp_timer_get_time(void) { return current_us; }
struct ptp_state_s {
 struct { struct ptpd_status_s *dest; sem_t *done; } status_req;
 ptp_profile_e active_ptp_profile;
 bool selected_source_valid;
 ptp_path_trace_t selected_path;
 struct ptp_announce_s own_identity, selected_source;
 struct timespec last_delta_timestamp;
 int64_t last_delta_ns, last_adjtime_ns;
 long drift_ppb;
 struct ptp_port_s {
  ptp_port_medium_e medium;
  ptp_port_wifi_mode_e wifi_mode;
  ptp_wifi_neighbor_t wifi_neighbor;
  bool peer_is_endpoint, enabled, link_up;
  long delayreq_interval_ms;
  ptp_peer_exchange_t peer_exchange;
  ptp_peer_capability_t peer_capability;ptp_capable_receive_t capable_receive;ptp_peer_rate_t peer_rate;
  long path_delay_ns, peer_delay_ns;
  struct timespec last_received_multicast, last_received_announce, last_received_sync;
  struct timespec last_transmitted_sync, last_transmitted_announce;
  struct timespec last_transmitted_delayresp, last_transmitted_delayreq;
 } port[1];
};
static bool ptp_is_gptp(struct ptp_state_s *state) { return state->active_ptp_profile == ptp_profile_gptp; }
static bool ready, s_use_sw_clock = true;
static bool media_known;static ptp_wifi_media_t media_state;
bool ptp_wifi_sta_media(int port_index, ptp_wifi_media_t *media) { (void)port_index; if (media_known) *media = media_state; return media_known; }
static bool ready_fn(uint32_t generation) { assert(generation==7); return ready; }
static bool (*ptp_ftm_clock_ready)(uint32_t) = ready_fn;
bool ptpd_timing_snapshot(ptp_timing_snapshot_t *snapshot) { snapshot->generation=7; return true; }
'''
checks = r'''
int main(void) {
 struct ptp_state_s state = {.selected_source_valid=true};
 state.port[0].medium = ptp_port_medium_wifi_ftm;
 struct ptpd_status_s status;
 memset(&status, 0xee, sizeof(status));
 state.own_identity.header.sourceidentity[0]=9;
 state.own_identity.btc_identity[0]=9;
 state.own_identity.utcoffset[1]=37;
 state.selected_source.header.sourceidentity[0]=2;
 state.selected_source.btc_identity[0]=1;
 state.selected_source.utcoffset[1]=37;
 state.selected_path.count=2;
 state.selected_path.identities[0][0]=1;
 state.selected_path.identities[1][0]=2;
 for (unsigned transition=0; transition<3; ++transition) {
  ready = transition==1;
  state.status_req.dest=&status;
  ptp_process_statusreq(&state);
  assert(status.clock_source_selected && status.clock_source_valid==ready);
  assert(!status.as_capable);
  assert(status.clock_source_info.id[0]==2 && status.clock_source_info.btc_id[0]==1);
  assert(status.clock_source_info.utcoffset==37 && status.own_identity_info.utcoffset==37);
  assert(status.selected_path.count==2 && status.selected_path.identities[1][0]==2);
  assert(!state.status_req.dest);
 }
 state.port[0].medium = ptp_port_medium_eth_hwts;
 ready = true;
 state.status_req.dest = &status;
 ptp_process_statusreq(&state);
 assert(!status.as_capable); /* Source selection alone does not qualify the link. */
 state.active_ptp_profile=ptp_profile_gptp;
 state.port[0].enabled=state.port[0].link_up=true;
 state.port[0].delayreq_interval_ms=1000;
 state.port[0].peer_capability=(ptp_peer_capability_t){.qualified=true,.received_us=current_us};
 if (CONFIG_ESP_PTP_DOMAIN != 0) {
  assert(!ptp_wired_capability(&state));
  state.port[0].peer_rate.responder[7]=2;
  ptp_capable_message_t indication={0};
  memcpy(indication.source_port,state.port[0].peer_rate.responder,10);
  assert(ptp_capable_receive(&state.port[0].capable_receive,&indication,
      state.port[0].peer_rate.responder,0,current_us));
  assert(ptp_wired_capability(&state));
  state.port[0].peer_rate.responder[9]=2;
  assert(!ptp_wired_capability(&state));
  state.port[0].peer_rate.responder[9]=0;
  current_us+=9000000;
  state.port[0].peer_capability.received_us=current_us;
  assert(!ptp_wired_capability(&state));
  assert(ptp_capable_receive(&state.port[0].capable_receive,&indication,
      state.port[0].peer_rate.responder,0,current_us));
 }
 state.status_req.dest=&status;
 ptp_process_statusreq(&state);
 assert(status.as_capable);
 state.selected_source.btc_priority1=255;state.status_req.dest=&status;
 ptp_process_statusreq(&state);
 assert(status.clock_source_selected && !status.clock_source_valid && status.as_capable);
 state.selected_source.btc_priority1=248;state.status_req.dest=&status;
 ptp_process_statusreq(&state);assert(status.clock_source_valid);
 state.selected_source_valid=false;
 state.status_req.dest=&status;
 ptp_process_statusreq(&state);
 assert(!status.clock_source_selected && !status.clock_source_valid && status.as_capable);
 assert(status.selected_path.count==0 && status.clock_source_info.btc_id[0]==0);
 assert(ptpd_status_source(&status)->btc_id[0]==9);
 current_us+=3000000;
 state.status_req.dest=&status;
 ptp_process_statusreq(&state);
 assert(!status.as_capable);
 puts("Actual status publication preserves selected source through acquisition/holdover and clears it on source loss");
}
'''
with tempfile.TemporaryDirectory() as temporary:
 path=Path(temporary); (path/'test.c').write_text(harness+function+checks)
 for domain in (0,1):
  subprocess.run(['cc',f'-DCONFIG_ESP_PTP_DOMAIN={domain}','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
     '-I',str(component),'-I',str(component/'include'),str(path/'test.c'),'-o',str(path/'test')],check=True)
  subprocess.run([str(path/'test')],check=True)
