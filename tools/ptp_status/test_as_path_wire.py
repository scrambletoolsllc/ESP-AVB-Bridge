#!/usr/bin/env python3
"""Compile the actual path response sender with actual wire layouts."""
from pathlib import Path
import subprocess,tempfile
component=Path('/home/dev/Development/esp_avb')
header=(component/'atdecc.h').read_text()
source=(component/'atdecc.c').read_text()
def wire_type(name):
 end=header.index('} '+name+';')+len('} '+name+';')
 start=header.rfind('typedef struct {',0,end)
 return header[start:end]+'\n'
wire=''.join(wire_type(name) for name in ['atdecc_header_s','aecp_common_s','aecp_common_aem_s','aecp_get_as_path_s','aecp_get_as_path_rsp_s'])
start=source.index('int avb_send_aecp_rsp_get_as_path(')
function=source[start:source.index('\nint avb_process_aecp_cmd_get_as_path',start)]
harness=r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <time.h>
#include <stdio.h>
#include "ptp_status_path.h"
#define AECP_MAX_AS_PATH_COUNT 17
#define UNIQUE_ID_LEN 8
#define AVTP_CDL_PREAMBLE_LEN 12
#define aecp_msg_type_aem_response 1
#define ethertype_avtp 0x22f0
#define avberr(...) ((void)0)
typedef uint8_t unique_id_t[8];
typedef uint8_t eth_addr_t[6];
typedef struct { struct ptpd_status_s ptp_status; } avb_state_s;
static void int_to_octets(const void *value, uint8_t *output, size_t length) {
 assert(length==2); uint16_t number; memcpy(&number,value,2);
 output[0]=number>>8; output[1]=number;
}
'''
stub=r'''
static unsigned expected_count;
static int avb_net_send_to(avb_state_s *state, int type, const void *data,
 size_t length, struct timespec *stamp, eth_addr_t *destination) {
 (void)state; (void)stamp; (void)destination; assert(type==0x22f0);
 const aecp_get_as_path_rsp_s *response=data;
 unsigned count=((unsigned)response->count[0]<<8)|response->count[1];
 assert(count==expected_count);
 assert(length==28+count*8 && length<=sizeof(*response));
 assert(response->common.header.control_data_len==length-12);
 uint8_t bytes[sizeof(*response)]; memcpy(bytes,data,length);
 if(count)assert(bytes[length-1]==0x99);
 else assert(bytes[length-1]==0);
 return 0;
}
'''
checks=r'''
int main(void) {
 avb_state_s state={0}; aecp_get_as_path_s request={0}; eth_addr_t destination={0};
 memset(state.ptp_status.own_identity_info.id,0x99,8);
 state.ptp_status.clock_source_selected=true;
 state.ptp_status.clock_source_valid=false;
 for(unsigned count=0;count<=16;++count) {
  state.ptp_status.selected_path.count=count;
  for(unsigned index=0;index<count;++index)
   memset(state.ptp_status.selected_path.identities[index],index+1,8);
  expected_count=count?count+1:0;
  assert(avb_send_aecp_rsp_get_as_path(&state,&request,&destination)==0);
 }
 puts("Actual AS path sender serializes unknown path and exact lengths through 17 clocks, including holdover");
}
'''
with tempfile.TemporaryDirectory() as temporary:
 path=Path(temporary);(path/'test.c').write_text(harness+wire+stub+function+checks)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
 '-I','/home/dev/Development/esp_ptp','-I','/home/dev/Development/esp_ptp/include',str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
