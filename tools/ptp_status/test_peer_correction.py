#!/usr/bin/env python3
"""Exercise actual peer-delay handler with signed corrections and Sync isolation."""
from pathlib import Path
import subprocess
import tempfile
component = Path('/home/dev/Development/esp_ptp')
source = (component/'ptp.c').read_text()
start = source.index('static int\nptp_process_delay_resp_follow_up(')
handler = source[start:source.index('/* Determine received packet type', start)]
start = source.index('static int64_t get_correction_ns(')
correction = source[start:source.index('// Convert period', start)]
harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <time.h>
#include "ptp.h"
#include "ptp_peer_exchange.h"
#include "ptp_peer_rate.h"
#include "ptp_peer_capability.h"
#define ptpinfo(...) ((void)0)
static int critical_entries;
static bool invalidate_commit, change_peer, stale_deferred;
#define portENTER_CRITICAL(lock) do { if (++critical_entries==2 && invalidate_commit) ptp_peer_invalidate(&state->port[0].peer_exchange); } while (0)
#define portEXIT_CRITICAL(lock) ((void)0)
static int64_t esp_timer_get_time(void) { return 300; }
#define FAR
#define OK 0
#define CONFIG_ESP_PTP_MAX_PEER_DELAY_NS 10000
#define CONFIG_ESP_PTP_DELAYREQ_AVGCOUNT 8
#define ptpwarn(...) ((void)0)
#define ptpdebug(...) ((void)0)
struct ptp_state_s {
 struct ptp_announce_s own_identity;
 double correction_ns;
 struct {
  ptp_peer_exchange_t peer_exchange;
  ptp_peer_rate_t peer_rate;
  ptp_peer_capability_t peer_capability;
  long peer_delay_ns;
  int peer_delay_avgcount;
 } port[1];
};
static bool ptp_is_gptp(struct ptp_state_s *state) { (void)state; return true; }
static int64_t timespec_delta_ns(struct timespec *first, struct timespec *second) {
 return (int64_t)(first->tv_sec-second->tv_sec)*1000000000LL+first->tv_nsec-second->tv_nsec;
}
static void ptp_format_to_timespec(uint8_t *wire, struct timespec *stamp) {
 stamp->tv_sec=0;stamp->tv_nsec=0;
 for (int index=0;index<6;index++) stamp->tv_sec=(stamp->tv_sec<<8)|wire[index];
 for (int index=6;index<10;index++) stamp->tv_nsec=(stamp->tv_nsec<<8)|wire[index];
}
static void encode(uint8_t *wire, unsigned bytes, uint64_t value) {
 for (unsigned index=0;index<bytes;index++) { wire[bytes-index-1]=(uint8_t)value;value>>=8; }
}
'''
checks = r'''
static void check(int64_t response_ns, int64_t follow_ns, long expected) {
 critical_entries=0;
 struct ptp_state_s state={0};
 struct ptp_delay_resp_follow_up_s follow={0};
 state.correction_ns=1234567.0;
 struct timespec transmit={10,1000}, receive={10,5000};
 struct ptp_delay_resp_s response={0};
 response.header.flags[0]=2;
 response.header.messagetype=0x13;follow.header.messagetype=0x1a;
 response.header.sourceidentity[7]=follow.header.sourceidentity[7]=2;
 encode(response.receivetimestamp+6,4,2000);
 encode(follow.origintimestamp+6,4,4000);
 encode(response.header.correction,8,(uint64_t)(response_ns*65536));
 encode(follow.header.correction,8,(uint64_t)(follow_ns*65536));
 uint32_t generation=ptp_peer_begin(&state.port[0].peer_exchange,0,&state.own_identity.header,1000);
 assert(ptp_peer_publish(&state.port[0].peer_exchange,generation,&transmit,100));
 assert(ptp_peer_response(&state.port[0].peer_exchange,&response,&receive,200)==PTP_PEER_ACCEPTED);
 state.port[0].peer_rate=(ptp_peer_rate_t){.anchored=true,
  .responder={0,0,0,0,0,0,0,2,0,0},.remote_previous={-1,4000},.local_previous={9,5000},.correction_previous=follow_ns};
 if(change_peer) {
  state.port[0].peer_rate.responder[7]=3;
  state.port[0].peer_delay_avgcount=8;
  state.port[0].peer_delay_ns=9000;
 }
 assert(ptp_process_delay_resp_follow_up(&state,&follow,stale_deferred ? generation+1 : 0)==OK);
 assert(state.correction_ns==1234567.0);
 assert(state.port[0].peer_capability.qualified==(expected>0 && expected<=800));
 assert(state.port[0].peer_delay_ns==expected);
 assert(state.port[0].peer_delay_avgcount==(expected?1:0));
}
int main(void) {
 check(0,0,1000);
 check(200,600,800);
 check(-200,600,600);
 check(200,-600,1400);
 check(0,4000,0); /* Invalid negative delay must not corrupt Sync correction. */
 change_peer=true;
 check(0,0,0);
 change_peer=false;
 stale_deferred=true;
 check(0,0,0);
 stale_deferred=false;
 invalidate_commit=true;
 check(0,0,0);
 puts("Actual peer-delay handler applies signed exchange corrections and preserves Sync correction");
}
'''
with tempfile.TemporaryDirectory() as temporary:
 path=Path(temporary)
 (path/'test.c').write_text(harness+handler+checks)
 subprocess.run(['cc','-std=c11','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(component),str(path/'test.c'),'-lm','-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
