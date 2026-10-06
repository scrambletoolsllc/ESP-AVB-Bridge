#!/usr/bin/env python3
"""Exercise actual wired and wireless periodic origination eligibility."""
from pathlib import Path
import subprocess
import tempfile
component=Path('/home/dev/Development/esp_ptp')
source=(component/'ptp.c').read_text()
start=source.index('  /* If there is no better timetransmitter clock')
body=source[start:source.index('  /* §12.2 Announce emission',start)].replace('#endif /* CONFIG_ESP_PTP_SERVER */','')
harness=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdint.h>
#include <time.h>
#include "ptp.h"
#define CONFIG_ESP_PTP_NUM_PORTS 2
#define CONFIG_ESP_PTP_ANNOUNCE_INTERVAL_MS 1000
#define CONFIG_ESP_PTP_SYNC_INTERVAL_MS 125
#define ptp_port_medium_eth_hwts 1
#define ptp_port_medium_wifi_ftm 2
struct ptp_port_s {bool enabled;int medium,ptp_socket;struct timespec last_transmitted_announce,last_transmitted_sync;
 void (*sync_egress_cb)(int,const uint8_t*,size_t,void*);void *sync_egress_ctx;};
struct ptp_state_s {bool gptp,capable,selected_source_valid;struct ptp_port_s port[2];struct ptp_announce_s own_identity,selected_source;};
static unsigned wired_announce,wired_sync,wireless_sync;
static bool ptp_is_gptp(struct ptp_state_s *state){return state->gptp;}
static bool ptp_wired_capability(struct ptp_state_s *state){return state->capable;}
static int fake_clock_gettime(int clock_id,struct timespec *stamp){(void)clock_id;*stamp=(struct timespec){10,0};return 0;}
#define clock_gettime fake_clock_gettime
static void clock_timespec_subtract(const struct timespec *later,const struct timespec *earlier,struct timespec *result){result->tv_sec=later->tv_sec-earlier->tv_sec;result->tv_nsec=0;}
static int64_t timespec_to_ms(const struct timespec *stamp){return stamp->tv_sec*1000;}
static void ptp_send_announce(struct ptp_state_s *state){(void)state;++wired_announce;}
static void ptp_send_sync(struct ptp_state_s *state){(void)state;++wired_sync;}
static void ptp_marshal_follow_up_for_beacon_ie(struct ptp_state_s *state,struct ptp_follow_up_s *message,int port){(void)state;(void)message;assert(port==1);}
static void wireless_send(int port,const uint8_t *message,size_t length,void *context){(void)message;(void)context;assert(port==1 && length==sizeof(struct ptp_follow_up_s));++wireless_sync;}
'''
checks=r'''
int main(void){
 for(unsigned priority=0;priority<=255;++priority){
  for(unsigned selected=0;selected<2;++selected){
   struct ptp_state_s state={.gptp=true,.capable=true,.selected_source_valid=selected};
   state.own_identity.btc_priority1=priority;
   state.port[0].enabled=true;state.port[0].medium=1;
   state.port[1].enabled=true;state.port[1].medium=2;state.port[1].sync_egress_cb=wireless_send;
   wired_announce=wired_sync=wireless_sync=0;publish(&state);
   assert(wired_announce==!selected);assert(wired_sync==(!selected && priority<255));
   assert(wireless_sync==(selected || priority<255));
   if(selected){
    state.selected_source.btc_priority1=255;state.port[1].last_transmitted_sync=(struct timespec){0};
    wireless_sync=0;publish(&state);assert(wireless_sync==0);
   }
   if(!selected && priority==255){
    assert(state.port[0].last_transmitted_sync.tv_sec==0 && state.port[1].last_transmitted_sync.tv_sec==0);
   }
  }
 }
 puts("Actual periodic egress: all 256 priorities, local/selected-source roles, wired Announce/Sync and wireless Sync passed");
}
'''
with tempfile.TemporaryDirectory() as temporary:
    path=Path(temporary);(path/'test.c').write_text(harness+'static void publish(struct ptp_state_s *state){\n'+body+'}\n'+checks)
    subprocess.run(['cc','-std=c11','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(component),str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
