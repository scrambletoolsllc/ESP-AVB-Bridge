#!/usr/bin/env python3
"""Verify the actual forwarding helper retires state before enqueue and tracks errors."""
from pathlib import Path
import subprocess
import tempfile
source = Path('/home/dev/Development/esp-hosted-mcu/slave/main/slave_wifi_std.c').read_text()
start = source.index('static void forward_ap_lifecycle(')
body = source[start:source.index('static void event_handler_wifi', start)]
harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#define ESP_OK 0
#define esp_err_t int
static unsigned stage,finished;
static bool fail,joined_value;
static uint32_t begin_impl(const uint8_t *mac,bool joined){assert(stage++==0);assert(mac==NULL);joined_value=joined;return 42;}
static void complete_impl(uint32_t token,bool queued){assert(stage++==2 && token==42 && queued==!fail);++finished;}
static uint32_t (*ftm_radio_association_begin)(const uint8_t*,bool)=begin_impl;
static void (*ftm_radio_association_complete)(uint32_t,bool)=complete_impl;
static esp_err_t send_event_data_to_host(int event,void *data,int size){assert(stage++==1 && event==7 && data==NULL && size==0);return fail?-1:0;}
'''
checks = r'''
int main(void){
 forward_ap_lifecycle(7,NULL,0,NULL,true);assert(stage==3 && finished==1 && joined_value);
 stage=0;fail=true;forward_ap_lifecycle(7,NULL,0,NULL,false);assert(stage==3 && finished==2 && !joined_value);
 ftm_radio_association_begin=NULL;ftm_radio_association_complete=NULL;
 stage=1;forward_ap_lifecycle(7,NULL,0,NULL,false);assert(stage==2 && finished==2);
 puts("Actual lifecycle hook: invalidation before enqueue, success/failure propagation, optional hooks passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)
    (path/'test.c').write_text(harness+body+checks)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
