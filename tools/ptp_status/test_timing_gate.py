#!/usr/bin/env python3
"""Exercise actual RX admission and daemon revocation blocks."""
from pathlib import Path
import subprocess,tempfile
component=Path('/home/dev/Development/esp_ptp');source=(component/'ptp.c').read_text()
start=source.index('  /* Timing state currently belongs')
admission=source[start:source.index('  /* Rout the packet',start)]
start=source.index('      if (ptp_is_gptp(state) && !capable) {')
revocation=source[start:source.index('      if (!state->port[0].capability_reported',start)]
harness=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include "ptp.h"
#define OK 0
#define ptp_port_medium_eth_hwts 1
struct ptp_state_s {
 bool selected_source_valid, gptp, capable;
 struct { int medium;bool twostep_pending;struct {struct ptp_header_s header;} rxbuf; } port[1];
};
static unsigned invalidations;
static bool ptp_is_gptp(struct ptp_state_s *state) {return state->gptp;}
static bool ptp_wired_capability(struct ptp_state_s *state) {return state->capable;}
static void ptp_invalidate_timing(void) {++invalidations;}
'''
checks=r'''
int main(void) {
 struct ptp_state_s state={.gptp=true,.selected_source_valid=true};state.port[0].medium=1;
 unsigned kinds[]={PTP_MSGTYPE_SYNC,PTP_MSGTYPE_FOLLOW_UP,PTP_MSGTYPE_ANNOUNCE};
 for(unsigned index=0;index<3;index++) {
  state.port[0].rxbuf.header.messagetype=kinds[index]|0x10;
  state.port[0].twostep_pending=true;
  assert(!admit(&state,0));assert(!state.port[0].twostep_pending);
  state.capable=true;assert(admit(&state,0));assert(!admit(&state,1));state.capable=false;
 }
 state.port[0].rxbuf.header.messagetype=PTP_MSGTYPE_PDELAY_RESP|0x10;
 assert(admit(&state,0)); /* Recovery traffic is not gated. */
 state.port[0].twostep_pending=true;revoke(&state,false);
 assert(!state.selected_source_valid && !state.port[0].twostep_pending && invalidations==1);
 revoke(&state,false);assert(invalidations==1);
 state.selected_source_valid=true;revoke(&state,true);assert(state.selected_source_valid);
 state.gptp=false;revoke(&state,false);assert(state.selected_source_valid);
 state.port[0].rxbuf.header.messagetype=PTP_MSGTYPE_SYNC;
 assert(admit(&state,0));
 state.gptp=true;state.port[0].medium=2;assert(admit(&state,0));
 puts("Actual wired timing admission rejects unqualified Sync/FollowUp/Announce, preserves recovery traffic and invalidates once");
}
'''
with tempfile.TemporaryDirectory() as temporary:
 path=Path(temporary);(path/'test.c').write_text(harness+'static int admit(struct ptp_state_s *state,int ingress_port) {\n'+admission+'return 1;\n}\nstatic void revoke(struct ptp_state_s *state,bool capable) {\n'+revocation+'}\n'+checks)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(component),str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
