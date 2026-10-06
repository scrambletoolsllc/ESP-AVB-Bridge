#!/usr/bin/env python3
"""Test the installed association-event MAC guard with binary addresses."""
from pathlib import Path
import subprocess,tempfile,re
root=Path(__file__).resolve().parents[2]
source=(root/'managed_components/espressif__esp_hosted/host/drivers/rpc/wrap/rpc_wrap.c').read_text()
checks=[]
for event in ['AP_StaConnected','AP_StaDisconnected']:
 start=source.index('case RPC_ID__Event_'+event+':')
 branch=source[start:source.index('break;',start)]
 guard=re.search(r'if \((.*?)\) \{',branch).group(1)
 checks.append('static bool test_'+event+'(const struct event *p_e) {return '+guard+';}')
harness='''#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
struct event {uint8_t mac[6];};
'''
main='''int main(void){
 struct event event={{0,1,2,3,4,5}};
 assert(test_AP_StaConnected(&event) && test_AP_StaDisconnected(&event));
 memset(event.mac,0,sizeof(event.mac));assert(!test_AP_StaConnected(&event) && !test_AP_StaDisconnected(&event));
 for(unsigned position=0;position<6;++position){event.mac[position]=2;assert(test_AP_StaConnected(&event) && test_AP_StaDisconnected(&event));event.mac[position]=0;}
 memset(event.mac,0xaa,6);assert(test_AP_StaConnected(&event) && test_AP_StaDisconnected(&event));
 puts("Actual AP event guards handle zero-leading and non-terminated binary MACs within six bytes");
}
'''
with tempfile.TemporaryDirectory() as directory:
 path=Path(directory);(path/'test.c').write_text(harness+'\n'.join(checks)+main)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
