#!/usr/bin/env python3
"""Exercise the actual SDIO TX handoff with queue saturation and ownership checks."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
component=root/'managed_components/espressif__esp_hosted'
source=(component/'host/drivers/transport/sdio/sdio_drv.c').read_text()
start=source.index('int esp_hosted_tx(')
body=source[start:source.index('\nvoid check_if_max_freq_used',start)]
header=(component/'host/drivers/transport/transport_drv.h').read_text()
start=header.index('#define H_FREE_PTR_WITH_FUNC')
macro=header[start:header.index('\n\n',start)]
harness=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#define ESP_PKT_STATS 0
#define ESP_OK 0
#define RET_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 0x101
#define HOSTED_BLOCK_MAX -1
#define MAX_PAYLOAD_SIZE 1600
#define ESP_STA_IF 0
#define ESP_AP_IF 1
#define ESP_SERIAL_IF 2
#define ESP_HCI_IF 3
#define PRIO_Q_OTHERS 0
#define PRIO_Q_SERIAL 1
#define PRIO_Q_BT 2
#define ESP_LOGE(...) ((void)0)
typedef struct {
 uint8_t payload_zcopy,if_type,if_num,flag;
 uint16_t payload_len;uint8_t *payload,*priv_buffer_handle;
 void (*free_buf_handle)(void*);
}interface_buffer_handle_t;
static int queues[3],semaphore;
static void *to_slave_queue[3]={&queues[0],&queues[1],&queues[2]};
static void *sem_to_slave_queue=&semaphore;
static bool ready=true;
static int result,timeout_seen,priority_seen;
static unsigned queued,posted,freed;
static void *free_expected;
static interface_buffer_handle_t received;
static uint8_t is_transport_tx_ready(void){return ready;}
static void release(void *buffer){assert(buffer==free_expected);++freed;}
static int enqueue(void *queue,void *item,int timeout){
 ++queued;timeout_seen=timeout;priority_seen=-1;
 for(int index=0;index<3;++index)if(queue==to_slave_queue[index])priority_seen=index;
 assert(priority_seen>=0);received=*(interface_buffer_handle_t*)item;return result;
}
static void post(void *sem){assert(sem==sem_to_slave_queue);++posted;}
static struct {int (*_h_queue_item)(void*,void*,int);void (*_h_post_semaphore)(void*);}functions={enqueue,post};
static struct {typeof(functions)*funcs;}g_h={&functions};
'''
checks=r'''
int main(void){
 uint8_t payload[100]={0},owner[200]={0};free_expected=owner;
 for(unsigned interface=0;interface<4;++interface)for(unsigned copy=0;copy<2;++copy)for(unsigned fail=0;fail<2;++fail){
  queued=posted=freed=0;result=fail?-1:0;
  int status=esp_hosted_tx(interface,7,payload,100,copy,owner,release,9);
  assert(queued==1 && posted==!fail && freed==fail);
  assert(timeout_seen==(interface<2?0:HOSTED_BLOCK_MAX));
  assert(priority_seen==(interface==2?1:interface==3?2:0));
  assert(status==(fail?(interface<2?ESP_ERR_NO_MEM:ESP_FAIL):ESP_OK));
  assert(received.payload==payload && received.priv_buffer_handle==owner);
  assert(received.payload_zcopy==copy && received.payload_len==100 && received.if_num==7 && received.flag==9);
  if(!fail){received.free_buf_handle(received.priv_buffer_handle);assert(freed==1);}
 }
 for(unsigned fault=0;fault<4;++fault){
  queued=posted=freed=0;ready=fault!=0;
  assert(esp_hosted_tx(1,0,fault==1?NULL:payload,fault==2?0:fault==3?1601:100,1,owner,release,0)==ESP_FAIL);
  assert(!queued && !posted && freed==1);
 }
 ready=true;result=-1;queued=posted=freed=0;
 assert(esp_hosted_tx(1,0,payload,100,0,NULL,NULL,0)==ESP_ERR_NO_MEM);
 assert(queued==1 && !posted && !freed);
 puts("Actual SDIO TX: bounded AP/STA queue, preserved control policy, correct priority, single buffer release and success-only wakeup passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory);(path/'test.c').write_text(harness+macro+'\n'+body+checks)
 subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
