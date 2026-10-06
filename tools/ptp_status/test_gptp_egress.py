#!/usr/bin/env python3
"""Check actual Ethernet serialization normalizes gPTP without mutating templates."""
from pathlib import Path
import subprocess,tempfile
component=Path('/home/dev/Development/esp_ptp')
source=(component/'ptp.c').read_text();start=source.index('static void ptp_create_eth_frame_to(')
body=source[start:source.index('\nstatic void ptp_create_eth_frame(',start)]
harness=r'''
#include <assert.h>
#include <arpa/inet.h>
#include <stdio.h>
#include "ptp_gptp_wire.h"
#define ETH_ADDR_LEN 6
#define ETH_TYPE_PTP 0x88f7
struct eth_hdr {struct {uint8_t addr[6];}dest,src;uint16_t type;};
struct ptp_state_s {bool gptp;struct {uint8_t intf_hw_addr[6];}port[1];};
static bool ptp_is_gptp(struct ptp_state_s *state){return state->gptp;}
'''
checks=r'''
int main(void){
 struct ptp_state_s state={.gptp=true};state.port[0].intf_hw_addr[0]=0x80;
 uint8_t destination[6]={1,0x80,0xc2,0,0,0x0e};
 uint8_t announce[76],original[76],frame[90];memset(announce,0xa5,sizeof(announce));
 announce[0]=0x1b;memcpy(original,announce,sizeof(original));
 ptp_create_eth_frame_to(&state,frame,announce,sizeof(announce),destination);
 assert(!memcmp(announce,original,sizeof(announce)));
 assert(!memcmp(frame,destination,6) && frame[6]==0x80 && frame[12]==0x88 && frame[13]==0xf7);
 assert(frame[15]==0x12 && frame[46]==0);
 for(unsigned index=48;index<58;++index)assert(frame[index]==0);
 assert(frame[60]==0);
 assert(!memcmp(frame+22,original+8,8));
 state.gptp=false;ptp_create_eth_frame_to(&state,frame,announce,sizeof(announce),destination);
 assert(!memcmp(frame+14,original,sizeof(original)));
 puts("Actual Ethernet serializer normalizes outgoing gPTP only and preserves caller-owned templates");
}
'''
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory);(path/'test.c').write_text(harness+body+checks)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(component),str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
