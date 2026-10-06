#!/usr/bin/env python3
"""Exercise actual wired capability TX dispatch independently of source selection."""
from pathlib import Path
import subprocess,tempfile
component=Path('/home/dev/Development/esp_ptp');source=(component/'ptp.c').read_text()
start=source.index('  /* Capability discovery continues')
body=source[start:source.index('  /* Wireless discovery',start)]
helper_start=source.index('static void ptp_wired_capable_send(')
helper=source[helper_start:source.index('/* Check if we need to send packets */',helper_start)]
harness=r'''
#include <assert.h>
#include <stdio.h>
#include "ptp.h"
#include "ptp_signaling.h"
#include "ptp_wired_capable.h"
#include "ptp_peer_rate.h"
#include "ptp_peer_exchange.h"
#define portENTER_CRITICAL(lock) ((void)0)
#define portEXIT_CRITICAL(lock) ((void)0)
#define CONFIG_ESP_PTP_DOMAIN 0
#define ptp_port_medium_eth_hwts 1
struct ptp_port_s {bool enabled,link_up;int medium,ptp_socket;ptp_wired_capable_t wired_capable;ptp_peer_rate_t peer_rate;ptp_peer_exchange_t peer_exchange;};
struct ptp_state_s {
 bool gptp;struct ptp_announce_s own_identity;
 struct ptp_port_s port[1];
};
static unsigned sent;static int64_t now_us;static int send_result=60;
static bool ptp_is_gptp(struct ptp_state_s *state) {return state->gptp;}
static int64_t esp_timer_get_time(void) {return now_us;}
static int ptp_net_send(struct ptp_state_s *state,void *data,size_t length,void *timestamp) {
 (void)state;uint8_t *wire=data;assert(!timestamp && length==60);
 assert(wire[0]==0x1c && wire[1]==0x12 && wire[29]==42);
 ++sent;return send_result;
}
'''
checks=r'''
int main(void) {
 struct ptp_state_s state={.gptp=true};
 state.own_identity.header.sourceportindex[1]=42;
 state.port[0].enabled=state.port[0].link_up=true;state.port[0].medium=1;
 dispatch(&state);assert(sent==1);
 dispatch(&state);assert(sent==1);
 now_us=1000000;send_result=-1;dispatch(&state);assert(sent==2);
 dispatch(&state);assert(sent==2); /* Failed TX cannot cause a busy retry loop. */
 for(unsigned reason=0;reason<5;reason++) {
  state.gptp=reason!=0;state.port[0].enabled=reason!=1;
  state.port[0].link_up=reason!=2;state.port[0].medium=reason==3?2:1;
  state.port[0].ptp_socket=reason==4?-1:0;
  now_us+=1000000;dispatch(&state);assert(sent==2);
 }
 state.gptp=true;state.port[0].enabled=state.port[0].link_up=true;
 state.port[0].medium=1;state.port[0].ptp_socket=0;
 dispatch(&state);assert(sent==3);
 puts("Actual wired capability TX gates profile/link/port/socket, preserves source port, and bounds failed sends");
}
'''
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory);(path/'test.c').write_text(harness+helper+'static void dispatch(struct ptp_state_s *state) {\n'+body+'}\n'+checks)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(component),str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
