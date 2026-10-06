#!/usr/bin/env python3
"""Exercise actual Announce queue/worker ownership, targeting and expiry."""
from pathlib import Path
import subprocess
import tempfile
component = Path('/home/dev/Development/esp_ptp')
source = (component / 'ptp_wifi.c').read_text()
start = source.index('#define PTP_AP_ANNOUNCE_MAX')
end = source.index('\ntypedef struct {', source.index('int ptp_wifi_ap_send_announce(', start))
body = source[start:end]
harness = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "ptp_wifi_association.h"
#define PTP_ANNOUNCE_MAX_LENGTH 256
#define CONFIG_ESP_PTP_NUM_PORTS 2
#define PTP_ANNOUNCE_BODY_LENGTH 64
#define pdTRUE 1
#define pdPASS 1
#define portMAX_DELAY 0
#define QueueHandle_t void*
static int64_t now_us;
static uint32_t generation=10,source_generation=20;
static uint32_t ptpd_timing_generation(void){return source_generation;}
static bool source_transition;
static unsigned sent,attempts,expected_port;
static bool snapshot_ok=true,queue_fail,task_fail,send_fail,transition,advance_time;
static ptp_wifi_association_snapshot_t registry;
static unsigned char mailbox[1024];
static size_t item_size;
static int64_t esp_timer_get_time(void){return now_us;}
static uint32_t ptp_wifi_link_generation(int port){assert(port==1);return generation;}
bool ptpd_wifi_association_snapshot(int port,ptp_wifi_association_snapshot_t *snapshot){
 assert(port==1);if(!snapshot_ok)return false;*snapshot=registry;return true;}
static unsigned completions;
static bool policy_allowed=true;
uint32_t ptpd_wifi_announce_begin(int port,const uint8_t mac[6],uint32_t association,
 uint32_t revision,uint32_t information_revision,int8_t initial,int64_t now,int8_t *advertised,uint16_t *sequence){
 assert(port==1 && mac && association && information_revision && now==now_us);
 (void)revision;*advertised=initial;*sequence=123;return policy_allowed?1:0;}
bool ptpd_wifi_announce_finish(int port,const uint8_t mac[6],uint32_t association,
 uint32_t token,bool accepted,int64_t now){
 assert(port==1 && mac && association && token==1 && now==now_us);(void)accepted;completions++;return true;}
static int wifi_ap_send_unicast_ptp(const uint8_t *source,const uint8_t *destination,void *payload,uint16_t length){
 const uint8_t *message=payload;assert(source[0]==2 && length==76);
 assert(message[28]==0 && message[29]==expected_port);
 assert(destination[5]==(expected_port==2 ? 5:6));
 ++attempts;if(source_transition)++source_generation;if(transition)++generation;if(advance_time)now_us+=1000000;
 expected_port=18;if(send_fail)return -1;++sent;return 90;}
static void *xQueueCreate(unsigned count,size_t size){assert(count==1 && size<=sizeof(mailbox));item_size=size;return queue_fail?NULL:mailbox;}
static int xQueueReceive(void *queue,void *item,unsigned delay){(void)queue;(void)item;(void)delay;return 0;}
static int xQueueOverwrite(void *queue,const void *item){assert(queue==mailbox);memcpy(mailbox,item,item_size);return pdTRUE;}
static void vQueueDelete(void *queue){assert(queue==mailbox);}
static int xTaskCreatePinnedToCore(void (*task)(void*),const char *name,unsigned stack,void *arg,unsigned priority,void *handle,unsigned core){
 (void)task;(void)name;(void)stack;(void)arg;(void)priority;(void)handle;(void)core;return task_fail?0:pdPASS;}
'''
checks = r'''
int main(void){
 uint8_t source[6]={2},message[300]={0};message[0]=0x1b;message[29]=99;
 registry.count=2;
 registry.entries[0]=(ptp_wifi_association_entry_t){.mac={2,1,2,3,4,5},.port_number=2,.association=1};
 registry.entries[1]=(ptp_wifi_association_entry_t){.mac={2,1,2,3,4,6},.port_number=18,.association=2};
 assert(ptp_wifi_ap_send_announce(1,NULL,message,76)==-1);
 assert(ptp_wifi_ap_send_announce(1,source,NULL,76)==-1);
 assert(ptp_wifi_ap_send_announce(1,source,message,20)==-1);
 assert(ptp_wifi_ap_send_announce(1,source,message,300)==-1);
 snapshot_ok=false;assert(ptp_wifi_ap_send_announce(1,source,message,76)==-1);snapshot_ok=true;
 queue_fail=true;assert(ptp_wifi_ap_send_announce(1,source,message,76)==-1);queue_fail=false;
 task_fail=true;assert(ptp_wifi_ap_send_announce(1,source,message,76)==-1);assert(!s_announce_mbox);task_fail=false;
 assert(ptp_wifi_ap_send_announce(1,source,message,76)==0);
 ap_announce_item_t item;memcpy(&item,mailbox,sizeof(item));
 registry.entries[0].port_number=99;message[29]=77;
 expected_port=2;assert(ap_send_announce_now(&item)==2 && sent==2 && message[29]==77);
 uint32_t information=ap_announce_information(&item);
 item.msg[30]++;item.msg[34]++;item.msg[33]=3;
 assert(ap_announce_information(&item)==information);
 item.msg[53]++;assert(ap_announce_information(&item)==++information);
 item.msg[64]++;assert(ap_announce_information(&item)==++information);
 item.msg[6]^=4;assert(ap_announce_information(&item)==++information);
 item.msg[20]++;assert(ap_announce_information(&item)==++information);
 ++generation;expected_port=2;assert(ap_send_announce_now(&item)==0 && sent==2);
 item.generation=generation;now_us=1000000;assert(ap_send_announce_now(&item)==0);
 now_us=-1;assert(ap_send_announce_now(&item)==0);
 now_us=0;transition=true;expected_port=2;assert(ap_send_announce_now(&item)==1);transition=false;
 item.generation=generation;advance_time=true;expected_port=2;assert(ap_send_announce_now(&item)==1);advance_time=false;
 now_us=0;send_fail=true;expected_port=2;unsigned before=attempts;
 assert(ap_send_announce_now(&item)==0 && attempts==before+2);
 policy_allowed=false;before=attempts;assert(ap_send_announce_now(&item)==0 && attempts==before);
 policy_allowed=true;assert(completions==6);
 send_fail=false;before=attempts;++source_generation;
 assert(ap_send_announce_now(&item)==0 && attempts==before);
 item.source_generation=source_generation;source_transition=true;expected_port=2;
 assert(ap_send_announce_now(&item)==1 && attempts==before+1);
 source_transition=false;
 registry.count=0;assert(ptp_wifi_ap_send_announce(1,source,message,76)==0);
 puts("Actual Announce: two logical identities, copied ownership, expiry, transition, failure and bounds passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path/'test.c').write_text(harness+body+checks)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    '-I',str(component),str(path/'test.c'),'-o',str(path/'test')],check=True)
    subprocess.run([str(path/'test')],check=True)
