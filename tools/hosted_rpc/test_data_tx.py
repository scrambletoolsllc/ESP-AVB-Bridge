#!/usr/bin/env python3
"""Exercise the actual SDIO TX handoff and its channel error mapping with
queue saturation and ownership checks."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
component=root/'managed_components/espressif__esp_hosted'
transport=component/'host/mcu/eh_host_mcu_transport/src'
source=(transport/'eh_host_bus_sdio.c').read_text()
start=source.index('int eh_host_bus_tx(')
bus=source[start:source.index('\nint eh_host_bus_inform_slave_ps_enter',start)]
source=(transport/'eh_host_mcu_transport_channels.c').read_text()
start=source.index('esp_err_t eh_host_transport_tx(')
channel=source[start:source.index('\nesp_err_t eh_host_transport_tx_zerocopy',start)]
header=(component/'host/eh_host_config/include/eh_host_port_master_config.h').read_text()
start=header.index('#define EH_HOST_PORT_FREE_PTR_WITH_FUNC')
macro=header[start:header.index('} while (0)',start)+len('} while (0)')]
harness=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define ESP_PKT_STATS 0
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 0x101
#define ESP_ERR_ESP_NETIF_TX_FAILED 0x5009
#define EH_HOST_PORT_OK 0
#define EH_HOST_PORT_ERR_TIMEOUT -2
#define EH_HOST_PORT_WAIT_FOREVER 0xffffffffu
#define MAX_PAYLOAD_SIZE 1600
#define ESP_STA_IF 0
#define ESP_AP_IF 1
#define ESP_SERIAL_IF 2
#define ESP_HCI_IF 3
#define PRIO_Q_SERIAL 0
#define PRIO_Q_BT 1
#define PRIO_Q_OTHERS 2
#define MAX_PRIORITY_QUEUES 3
#define TAG "test"
#define ESP_LOGE(...) ((void)0)
typedef int esp_err_t;
typedef struct {
 uint8_t payload_zcopy,if_type,if_num,flags;
 uint16_t payload_len;uint8_t *payload;void *priv_buffer_handle;
 void (*free_buf_handle)(void*);
}interface_buffer_handle_t;
typedef struct {unsigned count;}eh_host_port_queue_t;
typedef int eh_host_port_sem_t;
static eh_host_port_queue_t queues[MAX_PRIORITY_QUEUES];
static eh_host_port_queue_t *to_slave_queue[MAX_PRIORITY_QUEUES]={&queues[0],&queues[1],&queues[2]};
static eh_host_port_sem_t semaphore,*sem_to_slave_queue=&semaphore;
static uint32_t s_data_tx_queue_size=20;
static bool ready=true;
static int result,priority_seen,bus_result;
static uint32_t timeout_seen;
static unsigned queued,posted,freed,bus_calls;
static void *free_expected;
static interface_buffer_handle_t received;
static uint8_t is_transport_tx_ready(void){return ready;}
static void release(void *buffer){assert(buffer==free_expected);++freed;}
static int eh_host_port_queue_send(eh_host_port_queue_t *queue,const void *item,uint32_t timeout){
 ++queued;timeout_seen=timeout;priority_seen=(int)(queue-queues);
 assert(priority_seen>=0 && priority_seen<MAX_PRIORITY_QUEUES);
 received=*(const interface_buffer_handle_t*)item;
 if(result==EH_HOST_PORT_OK)++queue->count;
 return result;
}
static uint32_t eh_host_port_queue_count(const eh_host_port_queue_t *queue){return queue->count;}
static void eh_host_port_sem_post(eh_host_port_sem_t *sem){assert(sem==sem_to_slave_queue);++posted;}
static bool eh_host_wifi_tx_is_throttled(void){return false;}
static size_t eh_frame_hdr_size(void){return 12;}
static void *eh_host_port_dma_alloc(size_t size){return malloc(size);}
static void eh_host_port_dma_free(void *buffer){free(buffer);}
static void eh_frame_encode(uint8_t *buffer,const interface_buffer_handle_t *handle,uint16_t length){(void)buffer;(void)handle;(void)length;}
static int eh_host_mcu_transport_tx(interface_buffer_handle_t *handle){
 ++bus_calls;handle->free_buf_handle(handle->priv_buffer_handle);return bus_result;
}
'''
checks=r'''
int main(void){
 uint8_t payload[100]={0},owner[200]={0};free_expected=owner;
 for(unsigned interface=0;interface<4;++interface)for(unsigned copy=0;copy<2;++copy)for(unsigned fail=0;fail<2;++fail){
  queued=posted=freed=0;result=fail?EH_HOST_PORT_ERR_TIMEOUT:EH_HOST_PORT_OK;
  interface_buffer_handle_t handle={.payload_zcopy=copy,.if_type=interface,.if_num=7,.flags=9,
   .payload_len=100,.payload=payload,.priv_buffer_handle=owner,.free_buf_handle=release};
  int status=eh_host_bus_tx(&handle);
  assert(queued==1 && posted==!fail && freed==fail);
  assert(timeout_seen==(interface<2?0:EH_HOST_PORT_WAIT_FOREVER));
  assert(priority_seen==(interface==2?PRIO_Q_SERIAL:interface==3?PRIO_Q_BT:PRIO_Q_OTHERS));
  assert(status==(fail?(interface<2?ESP_ERR_NO_MEM:ESP_FAIL):ESP_OK));
  assert(received.payload==payload && received.priv_buffer_handle==owner);
  assert(received.payload_zcopy==copy && received.payload_len==100 && received.if_num==7 && received.flags==9);
  if(!fail){received.free_buf_handle(received.priv_buffer_handle);assert(freed==1);}
 }
 for(unsigned fault=0;fault<4;++fault){
  queued=posted=freed=0;ready=fault!=0;
  interface_buffer_handle_t handle={.if_type=ESP_AP_IF,.payload_len=fault==2?0:fault==3?1601:100,
   .payload=fault==1?NULL:payload,.priv_buffer_handle=owner,.free_buf_handle=release};
  assert(eh_host_bus_tx(&handle)==ESP_FAIL);
  assert(!queued && !posted && freed==1);
 }
 ready=true;result=EH_HOST_PORT_ERR_TIMEOUT;queued=posted=freed=0;
 interface_buffer_handle_t borrowed={.if_type=ESP_AP_IF,.payload_len=100,.payload=payload};
 assert(eh_host_bus_tx(&borrowed)==ESP_ERR_NO_MEM);
 assert(queued==1 && !posted && !freed);
 queues[PRIO_Q_OTHERS].count=16;
 assert(esp_hosted_data_tx_queue_space()==4);
 to_slave_queue[PRIO_Q_OTHERS]=NULL;
 assert(esp_hosted_data_tx_queue_space()==0);
 int expected[][2]={{ESP_OK,ESP_OK},{ESP_ERR_NO_MEM,ESP_ERR_NO_MEM},{ESP_FAIL,ESP_FAIL},{-2,ESP_FAIL}};
 for(unsigned index=0;index<4;++index){
  bus_calls=0;bus_result=expected[index][0];
  assert(eh_host_transport_tx(ESP_AP_IF,0,payload,100,0)==expected[index][1] && bus_calls==1);
 }
 puts("Actual SDIO TX: bounded AP/STA queue, preserved control policy, correct priority, single buffer release, success-only wakeup, queue space and ESP_ERR_NO_MEM pass-through passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory);(path/'test.c').write_text(harness+macro+'\n'+bus+'\n'+channel+checks)
 subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined',str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
