#!/usr/bin/env python3
"""Exercise the actual AP Announce builder with known, unknown and local-root paths."""
from pathlib import Path
import subprocess
import tempfile
component=Path('/home/dev/Development/esp_ptp')
source=(component/'ptp.c').read_text()
start=source.index('  /* §12.2 Announce emission')
body=source[start:source.index('  /* Post-fallback endpoint beacon',start)]
harness=r'''
#include <assert.h>
#include <stdio.h>
#include <time.h>
#include "ptp.h"
#include "ptp_path_trace.h"
#include "ptp_gptp_wire.h"
#define CONFIG_ESP_PTP_NUM_PORTS 2
#define CONFIG_ESP_PTP_ANNOUNCE_INTERVAL_MS 1000
#define ptp_port_medium_wifi_ftm 2
#define ptp_port_wifi_mode_ap 1
#define ptpinfo(...) ((void)0)
#ifdef CONFIG_ESP_PTP_ANNOUNCE_PATH_PROBE
static int64_t probe_now_us=1000000;
static int64_t esp_timer_get_time(void){return probe_now_us;}
#endif
struct ptp_port_s {bool enabled;int medium,wifi_mode;struct timespec last_transmitted_announce;uint8_t intf_hw_addr[6];};
struct ptp_state_s {bool selected_source_valid;struct ptp_announce_s selected_source,own_identity;ptp_path_trace_t selected_path;struct ptp_port_s port[2];};
static unsigned sent;static size_t wire_length;static uint8_t wire[PTP_ANNOUNCE_MAX_LENGTH];
static bool ptp_is_gptp(struct ptp_state_s *state){(void)state;return true;}
static int8_t msec_to_log_period(unsigned value){assert(value==1000);return 0;}
static int fake_clock_gettime(int clock_id,struct timespec *stamp){(void)clock_id;*stamp=(struct timespec){10,0};return 0;}
#define clock_gettime fake_clock_gettime
static void clock_timespec_subtract(const struct timespec *later,const struct timespec *earlier,struct timespec *result){result->tv_sec=later->tv_sec-earlier->tv_sec;result->tv_nsec=0;}
static int64_t timespec_to_ms(const struct timespec *stamp){return stamp->tv_sec*1000+stamp->tv_nsec/1000000;}
static void ptp_gettime(struct ptp_state_s *state,struct timespec *stamp){(void)state;*stamp=(struct timespec){50,0};}
static void timespec_to_ptp_format(const struct timespec *stamp,uint8_t *output){(void)stamp;memset(output,0,10);}
int ptp_wifi_ap_send_announce(int port,const uint8_t mac[6],void *message,uint16_t length){
 (void)mac;assert(port==1 && length<=sizeof(wire));++sent;wire_length=length;memcpy(wire,message,length);return 0;
}
'''
checks=r'''
int main(void){
 struct ptp_state_s state={.selected_source_valid=true};
 state.port[1].enabled=true;state.port[1].medium=2;state.port[1].wifi_mode=1;
 state.own_identity.header.sourceidentity[0]=3;state.own_identity.btc_identity[0]=3;
 state.own_identity.btc_priority1=255;
 state.selected_source.btc_identity[0]=1;state.selected_source.stepsremoved[1]=1;
 publish(&state);
 assert(sent==1 && wire_length==64 && wire[3]==64 && wire[53]==1 && wire[62]==2);
 assert(wire[20]==3 && wire[29]==2 && wire[0]==0x1b && wire[1]==0x12);
 state.port[1].last_transmitted_announce=(struct timespec){0};
 state.selected_path.count=1;state.selected_path.identities[0][0]=1;
 publish(&state);
 assert(sent==2 && wire_length==84 && wire[3]==84 && wire[65]==8 && wire[67]==16);
 assert(wire[68]==1 && wire[76]==3);
 state.port[1].last_transmitted_announce=(struct timespec){0};state.selected_source_valid=false;
 publish(&state);
 assert(sent==3 && wire_length==76 && wire[53]==3 && wire[67]==8 && wire[68]==3);
#ifdef CONFIG_ESP_PTP_ANNOUNCE_PATH_PROBE
 state.selected_source_valid=true;
 probe_now_us=31000000;state.port[1].last_transmitted_announce=(struct timespec){0};
 publish(&state);assert(sent==4 && wire_length==64 && wire[53]==1);
 probe_now_us=38999999;state.port[1].last_transmitted_announce=(struct timespec){0};
 publish(&state);assert(sent==5 && wire_length==64 && state.selected_path.count==1);
 probe_now_us=39000000;state.port[1].last_transmitted_announce=(struct timespec){0};
 publish(&state);assert(sent==6 && wire_length==84 && wire[53]==1);
#endif
 puts("Actual AP Announce builder preserves unknown paths, relays known paths, and originates a local-root path");
}
'''
with tempfile.TemporaryDirectory() as temporary:
 path=Path(temporary);(path/'test.c').write_text(harness+'static void publish(struct ptp_state_s *state){\n'+body+'}\n'+checks)
 for flags in ([],['-DCONFIG_ESP_PTP_ANNOUNCE_PATH_PROBE=1']):
  subprocess.run(['cc','-std=c11','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',*flags,'-I',str(component),str(path/'test.c'),'-o',str(path/'test')],check=True)
  subprocess.run([str(path/'test')],check=True)
