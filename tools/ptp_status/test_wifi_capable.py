#!/usr/bin/env python3
"""Exercise real wireless capability dispatch, freshness and Ethernet wrapping."""
from pathlib import Path
import subprocess, tempfile
component=Path('/home/dev/Development/esp_ptp')
source=(component/'ptp.c').read_text()
start=source.index('  /* Capability discovery continues')
dispatch=source[start:source.index('#if defined(CONFIG_ESP_PTP_SERVER)',start)]
transport=(component/'ptp_wifi.c').read_text()
start=transport.index('typedef struct {\n  int port_index;\n  bool ap;')
helpers=transport[start:transport.index('static void wifi_capable_task',start)]
helpers=helpers.replace('static QueueHandle_t s_capable_queue;', '').replace('static QueueHandle_t s_capable_results;', '')
harness=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "ptp.h"
#include "ptp_signaling.h"
#define CONFIG_ESP_PTP_DOMAIN 0
#define CONFIG_ESP_PTP_NUM_PORTS 2
#define ETH_HDR_LEN 14
#define ESP_OK 0
#define ptp_port_medium_eth_hwts 1
#define ptp_port_medium_wifi_ftm 2
#define ptp_port_wifi_mode_ap 1
#define ptp_port_wifi_mode_sta 2
struct ptp_port_s {bool enabled,link_up;int medium,ptp_socket,wifi_mode;
 uint8_t intf_hw_addr[6];};
struct ptp_state_s {bool gptp;struct ptp_announce_s own_identity;struct ptp_port_s port[2];};
static unsigned ap_dispatch,sta_dispatch;
static void ptp_wired_capable_send(struct ptp_state_s *state){(void)state;}
static void ptp_wifi_capable_completions(struct ptp_state_s *state){(void)state;}
static void ptp_wifi_ap_capable_send(struct ptp_state_s *state,int index,bool enabled){
 (void)state;assert(index==1);if(enabled)++ap_dispatch;}
static void ptp_wifi_sta_capable_send(struct ptp_state_s *state,int index,bool enabled){
 (void)state;assert(index==0);if(enabled)++sta_dispatch;}
static int64_t now_us;static uint32_t generation=7;
static unsigned wired,radio_calls;static int radio_interface;
static uint8_t radio_frame[74];
static bool ptp_is_gptp(struct ptp_state_s *state){return state->gptp;}
static int64_t esp_timer_get_time(void){return now_us;}
uint32_t ptp_wifi_link_generation(int index){assert(index==0);return generation;}
static int esp_wifi_internal_tx(int interface,void *frame,size_t length){
 assert(length==74);radio_interface=interface;memcpy(radio_frame,frame,length);++radio_calls;return 0;}
'''
checks=r'''
int main(void){
 struct ptp_state_s state={.gptp=true};
 for(int index=0;index<2;index++)state.port[index]=(struct ptp_port_s){
  .enabled=true,.link_up=true,.medium=2,.wifi_mode=index?1:2};
 dispatch(&state);assert(sta_dispatch==1 && ap_dispatch==1 && !wired);
 state.port[0].link_up=false;dispatch(&state);assert(sta_dispatch==1 && ap_dispatch==2);
 state.gptp=false;dispatch(&state);assert(sta_dispatch==1 && ap_dispatch==2);
 now_us=3000000;
 const uint8_t destination[6]={2,3,4,5,6,7};
 wifi_capable_item_t item={.generation=7,.queued_us=3000000,.source={8,9,10,11,12,13}};
 item.message[0]=0x1c;wifi_capable_send_to(&item,destination);
 assert(radio_calls==1 && radio_interface==0 && !memcmp(radio_frame,destination,6));
 assert(!memcmp(radio_frame+6,item.source,6) && radio_frame[12]==0x88 && radio_frame[13]==0xf7 && radio_frame[14]==0x1c);
 item.ap=true;wifi_capable_send_to(&item,destination);assert(radio_calls==2 && radio_interface==1);
 ++generation;wifi_capable_send_to(&item,destination);assert(radio_calls==2);
 --generation;now_us=4000000;wifi_capable_send_to(&item,destination);assert(radio_calls==2);
 now_us=2999999;wifi_capable_send_to(&item,destination);assert(radio_calls==2);
 puts("Actual WiFi cadence, AP/STA interfaces, destination bytes, link generation and queue age passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory);(path/'test.c').write_text(harness+helpers+'static void dispatch(struct ptp_state_s *state){\n'+dispatch+'}\n'+checks)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(component),str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
