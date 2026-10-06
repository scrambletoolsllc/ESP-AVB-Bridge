#!/usr/bin/env python3
"""Exercise the actual daemon AP scheduling and value-only completion dispatch."""
from pathlib import Path
import subprocess
import tempfile
component = Path('/home/dev/Development/esp_ptp')
source = (component / 'ptp.c').read_text()
start = source.index('/* Radio completion records')
body = source[start:source.index('/* Check if we need to send packets */', start)]
reset_start = source.index('  /* Retire radio work before resetting interval state')
reset_body = source[reset_start:source.index('  ptp_invalidate_timing();', reset_start)]
body += 'static void reset_profile(struct ptp_state_s *state) {\n' + reset_body + '}\n'
wait_start = source.index('    /* Capability deadlines must not depend on incoming Ethernet traffic. */')
wait_body = source[wait_start:source.index('    ret = poll(pollfds, 1, wait_ms);', wait_start)]
body += 'static int poll_wait(struct ptp_state_s *state, int wait_ms) {\n' + wait_body + 'return wait_ms;}\n'

harness = r'''
#include <assert.h>
#include <stdio.h>
#include "ptp.h"
#include "ptp_wifi_peers.h"
#include "ptp_wifi_neighbor.h"
#include "ptp_wired_capable.h"
#include "ptp_peer_rate.h"
#include "ptp_peer_exchange.h"
#include "ptp_sync_receipt.h"
#define CONFIG_ESP_PTP_NUM_PORTS 2
#define CONFIG_ESP_PTP_DOMAIN 0
#define ptp_port_medium_wifi_ftm 2
#define ptp_port_medium_eth_hwts 1
#define ptp_port_wifi_mode_ap 1
#define ptp_port_wifi_mode_sta 2
static bool locked;
#define portENTER_CRITICAL(lock) do {assert(!locked);locked=true;} while(0)
#define portEXIT_CRITICAL(lock) do {assert(locked);locked=false;} while(0)
struct ptp_port_s {bool enabled,link_up;int medium,wifi_mode,ptp_socket;ptp_capable_receive_t capable_receive;ptp_wired_capable_t wired_capable;ptp_peer_rate_t peer_rate;ptp_peer_exchange_t peer_exchange;ptp_wifi_peers_t wifi_peers;ptp_wifi_neighbor_t wifi_neighbor;uint8_t intf_hw_addr[6];ptp_sync_receipt_t sync_receipt;};
struct ptp_state_s {struct ptp_port_s port[2];struct ptp_announce_s own_identity;bool selected_source_valid;struct ptp_announce_s selected_source;};
static bool ptp_is_gptp(struct ptp_state_s *state){(void)state;return true;}
static unsigned wired_sends;static bool wired_fail,wired_transition;
static int ptp_net_send(struct ptp_state_s *state,void *message,uint16_t length,void *stamp){
 (void)stamp;assert(!locked && length==60 && ((uint8_t*)message)[0]==0x1c);
 ++wired_sends;if(wired_transition)++state->port[0].peer_exchange.lifecycle;
 return wired_fail?-1:74;}
static int64_t now_us;
static uint32_t generation=1;
static uint32_t s_injected_generation[2]={10,20};
static bool queued,queue_fail;
static unsigned sends, expected_source_port=2;
static ptp_wifi_capable_result_t completion;
static int64_t esp_timer_get_time(void){return now_us;}
uint32_t ptp_wifi_link_generation(int index){assert(index==1);return generation;}
bool ptp_wifi_capable_result(ptp_wifi_capable_result_t *result){
 assert(!locked);if(!queued)return false;*result=completion;queued=false;return true;}
int ptp_wifi_send_capable_peer(int index,bool ap,const uint8_t source[6],const uint8_t destination[6],
 uint32_t epoch,uint32_t association,uint32_t token,const uint8_t *message,uint16_t length){
 (void)source;(void)ap;assert(!locked && index==1 && length==60 && message[29]==expected_source_port);
 ++sends;if(queue_fail)return -1;
 completion=(ptp_wifi_capable_result_t){.port_index=index,.generation=epoch,
  .association=association,.token=token,.accepted=true,.completed_us=now_us+1};
 memcpy(completion.destination,destination,6);queued=true;return 0;}
'''
checks = r'''
int main(void){
 struct ptp_state_s state={0};state.port[1].wifi_mode=1;uint8_t address[6]={2,1};
 ptp_wifi_peer_t *peer=ptp_wifi_peers_join(&state.port[1].wifi_peers,address);
#if CONFIG_ESP_PTP_HAS_AP_VIA_COPROCESSOR
 state.port[1].enabled=true;state.port[1].link_up=true;state.port[1].medium=2;
 ptp_wifi_ap_capable_send(&state,1,true);assert(!sends && !queued);
 assert(poll_wait(&state,500)==500);
 const uint8_t macs[1][6]={{2,1}};
 assert(ptp_wifi_peers_reconcile(&state.port[1].wifi_peers,7,1,macs,1));
 ptp_wifi_ap_capable_send(&state,1,true);assert(sends==1 && queued);
 ptp_wifi_capable_completions(&state);
 ptp_wifi_peers_advance(&state.port[1].wifi_peers);
 now_us=2000000;
 ptp_wifi_ap_capable_send(&state,1,true);assert(sends==1 && !queued);
 assert(poll_wait(&state,500)==500);
 assert(ptp_wifi_peers_reconcile(&state.port[1].wifi_peers,7,2,macs,1));
 ptp_wifi_ap_capable_send(&state,1,true);assert(sends==2 && queued);
 ptp_wifi_capable_completions(&state);
 puts("Hosted AP capability publication and deadlines wait for radio reconciliation");
 return 0;
#endif
 assert(ptp_capable_schedule_request(&peer->transmit,2));
 ptp_wifi_ap_capable_send(&state,1,true);assert(sends==1 && queued);
 ptp_wifi_ap_capable_send(&state,1,true);assert(sends==1);
 ptp_wifi_capable_completions(&state);assert(peer->transmit.interval.slowdown_remaining==8);
 now_us=1000000;queue_fail=true;ptp_wifi_ap_capable_send(&state,1,true);
 assert(sends==2 && !peer->transmit.pending && peer->transmit.interval.slowdown_remaining==8);
 queue_fail=false;now_us=2000000;ptp_wifi_ap_capable_send(&state,1,true);
 assert(sends==3);++generation;ptp_wifi_capable_completions(&state);
 assert(peer->transmit.interval.slowdown_remaining==8);
 now_us=3000000;ptp_wifi_ap_capable_send(&state,1,true);assert(sends==4);
 ptp_wifi_peers_join(&state.port[1].wifi_peers,address);
 ptp_wifi_capable_completions(&state);assert(!peer->transmit.active);
 ptp_wifi_ap_capable_send(&state,1,false);assert(sends==4);
 ptp_wifi_ap_capable_send(&state,1,true);assert(sends==5);
 assert(peer->transmit.interval.log_interval==0);
 uint32_t serial=peer->transmit.serial;
 peer->sync_stopped=true;peer->sync_revision=UINT32_MAX;peer->capable.valid=true;
 state.port[1].capable_receive.valid=true;
 state.port[1].wifi_neighbor.sync_stopped=true;state.port[1].wifi_neighbor.sync_revision=7;
 peer->announce.serial=42;peer->announce.sequence=19;peer->announce.revision=UINT32_MAX-1;
 assert(ptp_announce_request(&peer->announce,0,127));
 reset_profile(&state);
 assert(s_injected_generation[0]==11 && s_injected_generation[1]==21);
 assert(!peer->transmit.pending && !peer->transmit.active && peer->transmit.serial==serial);
 assert(peer->associated);
 assert(!peer->sync_stopped && peer->sync_revision==1 && !peer->capable.valid);
 assert(!state.port[1].capable_receive.valid);
 assert(!state.port[1].wifi_neighbor.sync_stopped && state.port[1].wifi_neighbor.sync_revision==8);
 assert(!peer->announce.initialized && peer->announce.revision==1 && peer->announce.sequence==19 && peer->announce.serial==42);
 int8_t advertised;uint16_t announce_sequence;
 assert(!ptp_announce_begin(&peer->announce,0,UINT32_MAX,1,now_us,&advertised,&announce_sequence));
 assert(ptp_announce_begin(&peer->announce,0,1,1,now_us,&advertised,&announce_sequence)==43);
 assert(advertised==0 && announce_sequence==20);
 state.port[1].enabled=true;state.port[1].link_up=true;
 state.port[1].medium=2;state.port[1].wifi_mode=1;
 assert(poll_wait(&state,500)==0);
 assert(ptp_capable_schedule_request(&peer->transmit,-3));
 ptp_wifi_ap_capable_send(&state,1,true);
 assert(poll_wait(&state,500)==125); /* Drains completion before waiting. */
 now_us+=120001;assert(poll_wait(&state,500)==5);
 now_us+=5000;assert(poll_wait(&state,500)==0);
 state.port[1].link_up=false;assert(poll_wait(&state,500)==500);
 state.port[1].link_up=true;state.port[1].wifi_mode=2;
 ptp_wifi_neighbor_t *neighbor=&state.port[1].wifi_neighbor;
 ptp_wifi_neighbor_associate(neighbor,address);
 assert(ptp_capable_schedule_request(&neighbor->transmit,-3));
 unsigned before=sends;ptp_wifi_sta_capable_send(&state,1,true);assert(sends==before+1);
 assert(poll_wait(&state,500)==125 && !neighbor->transmit.pending);
 now_us+=125000;ptp_wifi_sta_capable_send(&state,1,true);assert(sends==before+2);
 ptp_wifi_neighbor_associate(neighbor,address);ptp_wifi_capable_completions(&state);
 assert(!neighbor->transmit.active && neighbor->transmit.interval.log_interval==0);
 assert(poll_wait(&state,500)==0);
 assert(ptp_capable_schedule_request(&neighbor->transmit,127));
 assert(poll_wait(&state,500)==500);
 ptp_wifi_sta_capable_send(&state,1,true);assert(sends==before+2);
 struct ptp_port_s *wired=&state.port[0];wired->enabled=true;wired->link_up=true;wired->medium=1;
 wired->peer_exchange.lifecycle=7;wired->peer_rate.lifecycle=7;wired->peer_rate.anchored=true;
 wired->peer_rate.responder[7]=3;wired->peer_rate.responder[9]=1;
 ptp_wired_capable_send(&state);assert(wired_sends==1 && !wired->wired_capable.transmit.pending);
 assert(wired->wired_capable.bound);
 ptp_capable_message_t request={.log_interval=1};memcpy(request.source_port,wired->peer_rate.responder,10);
 assert(ptp_wired_capable_request(&wired->wired_capable,7,&request));
 wired_fail=true;ptp_wired_capable_send(&state);
 assert(wired_sends==2 && wired->wired_capable.transmit.interval.slowdown_remaining==9);
 wired_fail=false;now_us+=1000000;ptp_wired_capable_send(&state);
 assert(wired_sends==3 && wired->wired_capable.transmit.interval.slowdown_remaining==8);
 now_us+=1000000;wired_transition=true;ptp_wired_capable_send(&state);
 assert(wired_sends==4 && wired->wired_capable.transmit.interval.slowdown_remaining==8);
 wired_transition=false;ptp_wired_capable_send(&state);
 assert(wired_sends==5 && wired->wired_capable.transmit.interval.log_interval==0 && !wired->wired_capable.bound);
 assert(poll_wait(&state,2000)==1000);
 struct ptp_state_s multiple={0};multiple.port[1].wifi_mode=1;
 ptp_wifi_peer_t *first=ptp_wifi_peers_join(&multiple.port[1].wifi_peers,address);
 assert(ptp_capable_schedule_request(&first->transmit,127));
 uint8_t second_address[6]={2,2};
 ptp_wifi_peer_t *second=ptp_wifi_peers_join(&multiple.port[1].wifi_peers,second_address);
 expected_source_port=18;unsigned previous_sends=sends;
 ptp_wifi_ap_capable_send(&multiple,1,true);
 assert(sends==previous_sends+1 && completion.association==second->association);
 assert(!memcmp(completion.destination,second_address,6));
 ptp_wifi_capable_completions(&multiple);assert(!second->transmit.pending);
 puts("Actual wired/AP/STA scheduler: nonblocking dispatch, enqueue failure, generation retirement, association replacement and completion accounting passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path / 'test.c').write_text(harness + body + checks)
    for hosted in (0, 1):
      subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    f'-DCONFIG_ESP_PTP_HAS_AP_VIA_COPROCESSOR={hosted}',
                    '-fsanitize=address,undefined', '-I', str(component),
                    str(path / 'test.c'), '-o', str(path / 'test')], check=True)
      subprocess.run([str(path / 'test')], check=True)
