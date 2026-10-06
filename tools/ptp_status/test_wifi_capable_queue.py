#!/usr/bin/env python3
"""Run actual capability queue and worker against radio/lifecycle failures."""
from pathlib import Path
import subprocess,tempfile
component=Path('/home/dev/Development/esp_ptp')
source=(component/'ptp_wifi.c').read_text()
start=source.index('typedef struct {\n  int port_index;\n  bool ap;')
body=source[start:source.index('/* ===========================================================================\n * STA side',start)]
harness=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <setjmp.h>
#include "ptp_signaling.h"
#include "ptp.h"
#define CONFIG_ESP_PTP_NUM_PORTS 2
#define ETH_HDR_LEN 14
#define pdTRUE 1
#define pdPASS 1
#define portMAX_DELAY 0xffffffff
#define ESP_OK 0
#define ESP_FAIL -1
typedef void *QueueHandle_t;
typedef struct {int num;struct {uint8_t mac[6];}sta[4];}wifi_sta_list_t;
typedef struct {uint8_t bssid[6];}wifi_ap_record_t;
static uint8_t queue_storage[1024],result_storage[1024],frame_copy[74];
static size_t result_size;static bool result_available,tx_ok;static unsigned creations;
static size_t item_size;static bool available,create_fail,task_fail;
static unsigned calls;static int last_interface;static uint32_t generation=1;
static int64_t now_us=0;static jmp_buf finished;
static int64_t esp_timer_get_time(void){return now_us;}
uint32_t ptp_wifi_link_generation(int port){assert(port==0);return generation;}
static QueueHandle_t xQueueCreate(unsigned depth,size_t size){
 assert(depth==32);if(create_fail)return NULL;
 if(++creations%2){item_size=size;return queue_storage;}
 result_size=size;return result_storage;}
static void vQueueDelete(QueueHandle_t queue){assert(queue==queue_storage || queue==result_storage);}
static int xTaskCreatePinnedToCore(void (*function)(void*),const char *name,int stack,void *arg,int priority,void *handle,int core){
 (void)function;(void)name;(void)stack;(void)arg;(void)priority;(void)handle;assert(core==0);return task_fail?0:1;}
static int xQueueSend(QueueHandle_t queue,void *item,unsigned wait){
 assert(!wait);
 if(queue==result_storage){if(result_available)return 0;memcpy(result_storage,item,result_size);result_available=true;return 1;}
 assert(queue==queue_storage);if(available)return 0;memcpy(queue_storage,item,item_size);available=true;return 1;}
static int xQueueReceive(QueueHandle_t queue,void *item,unsigned wait){
 if(queue==result_storage){assert(!wait);if(!result_available)return 0;
 memcpy(item,result_storage,result_size);result_available=false;return 1;}
 assert(queue==queue_storage && wait==portMAX_DELAY);if(!available)longjmp(finished,1);
 memcpy(item,queue_storage,item_size);available=false;return 1;}
static int esp_wifi_internal_tx(int interface,void *frame,size_t length){
 assert(length==74);memcpy(frame_copy,frame,length);last_interface=interface;++calls;return tx_ok?ESP_OK:ESP_FAIL;}
'''
checks=r'''
static void drain(void){if(!setjmp(finished))wifi_capable_task(NULL);}
int main(void){
 uint8_t message[60]={0x1c},source[6]={0x88},destination[6]={0x22};
 ptp_wifi_capable_result_t result;
 assert(ptp_wifi_send_capable_peer(-1,true,source,destination,generation,8,12,message,60)==-1);
 assert(ptp_wifi_send_capable_peer(0,true,source,destination,generation,8,12,message,59)==-1);
 assert(ptp_wifi_send_capable_peer(0,true,NULL,destination,generation,8,12,message,60)==-1);
 assert(ptp_wifi_send_capable_peer(0,true,source,NULL,generation,8,12,message,60)==-1);
 assert(ptp_wifi_send_capable_peer(0,true,source,destination,generation,0,12,message,60)==-1);
 create_fail=true;assert(ptp_wifi_send_capable_peer(0,true,source,destination,generation,8,12,message,60)==-1);
 create_fail=false;task_fail=true;
 assert(ptp_wifi_send_capable_peer(0,true,source,destination,generation,8,12,message,60)==-1 && !s_capable_queue && !s_capable_results);
 task_fail=false;
 assert(!ptp_wifi_send_capable_peer(0,true,source,destination,generation,8,12,message,60));
 assert(ptp_wifi_send_capable_peer(0,true,source,destination,generation,8,13,message,60)==-1);
 source[0]=0x99;message[0]=0xff;destination[0]=0x44;drain();
 assert(calls==1 && frame_copy[0]==0x22 && frame_copy[6]==0x88 && frame_copy[14]==0x1c);
 assert(ptp_wifi_capable_result(&result) && result.token==12 && result.association==8 && !result.accepted);
 assert(result.destination[0]==0x22 && result.completed_us==now_us);
 tx_ok=true;assert(!ptp_wifi_send_capable_peer(0,true,source,destination,generation,8,13,message,60));drain();
 assert(ptp_wifi_capable_result(&result) && result.accepted && result.token==13 && calls==2);
 assert(!ptp_wifi_send_capable_peer(0,true,source,destination,generation,8,14,message,60));++generation;drain();
 assert(ptp_wifi_capable_result(&result) && !result.accepted && calls==2);
 assert(!ptp_wifi_send_capable_peer(0,true,source,destination,generation,8,15,message,60));now_us+=1000000;drain();
 assert(ptp_wifi_capable_result(&result) && !result.accepted && calls==2);
 assert(ptp_wifi_send_capable_peer(0,true,source,destination,generation,8,0,message,60)==-1);
 assert(!ptp_wifi_send_capable_peer(0,false,source,destination,generation,8,16,message,60));drain();
 assert(ptp_wifi_capable_result(&result) && result.accepted && last_interface==0 && frame_copy[0]==0x44);
 assert(!ptp_wifi_send_capable_peer(0,true,source,destination,generation,8,17,message,60));drain();
 assert(!ptp_wifi_send_capable_peer(0,true,source,destination,generation,8,18,message,60));drain();
 assert(ptp_wifi_capable_result(&result) && result.token==17); /* Full result queue retains its existing record. */
 assert(!ptp_wifi_capable_result(&result) && !ptp_wifi_capable_result(NULL));
 puts("Targeted capability queue: owned copies, AP/STA interfaces, bounded work/results, failed radio sends, stale generations, expiry and initialization failures passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory);(path/'test.c').write_text(harness+body+checks)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(component),str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
