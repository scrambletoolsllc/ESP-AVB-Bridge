#!/usr/bin/env python3
"""Check independent bench request frames against production decoder and target gates."""
from pathlib import Path
import subprocess,tempfile
component=Path('/home/dev/Development/esp_ptp')
source=(component/'ptp_wifi.c').read_text()
start=source.index('typedef struct {\n  int port_index;\n  uint32_t generation;\n  bool ap;\n  uint8_t source_mac')
body=source[start:source.index('static void interval_probe_task',start)]
body=body.replace('static interval_probe_t s_interval_probe;','').replace('static bool s_interval_probe_started;','')
harness=r'''
#include <assert.h>
#include <stdio.h>
#include "ptp_signaling.h"
#define CONFIG_ESP_PTP_DOMAIN 0
'''
checks=r'''
int main(void){
 interval_probe_t probe={.source_mac={2,1},.destination={2,2},.source_port={1},.target_port={2}};
 probe.source_port[9]=1;probe.target_port[9]=2;
 uint8_t storage[74];memset(storage,0xa5,sizeof(storage));
 int requests[]={1,-3,127,-4,126};
 for(unsigned index=0;index<5;++index){
  interval_probe_frame(storage+1,&probe,0x1234,requests[index],false);
  assert(storage[0]==0xa5 && storage[73]==0xa5);
  assert(!memcmp(storage+1,probe.destination,6) && !memcmp(storage+7,probe.source_mac,6));
  assert(storage[13]==0x88 && storage[14]==0xf7);
  ptp_capable_message_t decoded;
  assert(ptp_signaling_read_capable_interval(storage+15,58,0,probe.target_port,&decoded)==2);
  assert(decoded.log_interval==requests[index] && !memcmp(decoded.source_port,probe.source_port,10));
  assert(storage[45]==0x12 && storage[46]==0x34);
 }
 interval_probe_frame(storage+1,&probe,1,127,true);
 ptp_capable_message_t decoded;
 assert(ptp_signaling_read_capable_interval(storage+15,58,0,probe.target_port,&decoded)==2);
 assert(decoded.source_port[9]==0x41);
 puts("Independent interval probe frames: length, boundaries, Ethernet addresses, target identity, signed requests and wrong identity passed");
}
'''
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory);(path/'test.c').write_text(harness+body+checks)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(component),str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
