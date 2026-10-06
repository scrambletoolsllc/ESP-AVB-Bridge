#!/usr/bin/env python3
"""Exercise actual FTM source admission when a selected priority vector has no root."""
from pathlib import Path
import subprocess,tempfile
component=Path('/home/dev/Development/esp_ptp');source=(component/'ptp.c').read_text()
start=source.index('bool ptpd_ftm_source_observed(')
body=source[start:source.index('\nextern void ptp_ftm_daemon_tick',start)]
harness=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <stdio.h>
#include "ptp.h"
#include "ptp_sync_receipt.h"
#include "ptp_timing_snapshot.h"
#define CONFIG_ESP_PTP_NUM_PORTS 1
#define CONFIG_ESP_PTP_DOMAIN 0
struct ptp_state_s {bool selected_source_valid,gptp;struct ptp_announce_s selected_source;
 struct {bool link_up;struct timespec last_received_sync;ptp_sync_receipt_t sync_receipt;} port[1];};
static struct ptp_state_s *s_state;
static bool s_use_sw_clock=true;
static bool ptp_is_gptp(struct ptp_state_s *state){return state->gptp;}
static unsigned reads;
static int64_t esp_timer_get_time(void){return 1000000;}
static bool ptpd_timing_snapshot_stub(ptp_timing_snapshot_t *snapshot){++reads;snapshot->generation=9;return true;}
#define ptpd_timing_snapshot ptpd_timing_snapshot_stub
static int fake_clock_gettime(int kind,struct timespec *stamp){(void)kind;*stamp=(struct timespec){10,0};return 0;}
#define clock_gettime fake_clock_gettime
'''
checks=r'''
int main(void){
 struct ptp_state_s state={.selected_source_valid=true,.gptp=true};s_state=&state;
 state.port[0].link_up=true;state.selected_source.header.sourceidentity[0]=2;state.selected_source.header.sourceportindex[1]=18;
 uint8_t identity[10]={2};identity[9]=18;
 for(unsigned priority=0;priority<256;++priority){
  state.selected_source.btc_priority1=priority;state.port[0].last_received_sync=(struct timespec){3,0};
  uint32_t generation=77;unsigned before=reads;
  bool accepted=ptpd_ftm_source_observed(0,identity,0,-3,1000000,&generation);
  assert(accepted==(priority<255));
  assert(generation==(accepted?9:77));assert(reads==before+accepted);
  assert(state.port[0].last_received_sync.tv_sec==(accepted?10:3));
 }
 state.selected_source.btc_priority1=248;uint32_t generation=77;unsigned before=reads;
 ptp_sync_receipt_t timer_before=state.port[0].sync_receipt;
 assert(!ptpd_ftm_source_observed(0,identity,0,-3,600000,&generation));
 assert(!ptpd_ftm_source_observed(0,identity,0,-3,1000001,&generation));
 assert(!ptpd_ftm_source_observed(0,identity,0,127,1000000,&generation));
 assert(generation==77 && reads==before && !memcmp(&timer_before,&state.port[0].sync_receipt,sizeof(timer_before)));
 puts("Actual FTM admission: all root priorities; priority255 cannot refresh timing or expose a discipline generation");
}
'''
with tempfile.TemporaryDirectory() as temporary:
 path=Path(temporary);(path/'test.c').write_text(harness+body+checks)
 subprocess.run(['cc','-std=c11','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(component),'-I',str(component/'include'),str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
