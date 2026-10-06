#!/usr/bin/env python3
"""Exercise actual request sender around synchronous network completion."""
from pathlib import Path
import subprocess,tempfile
component=Path('/home/dev/Development/esp_ptp')
source=(component/'ptp.c').read_text()
start=source.index('static int ptp_send_delay_req(')
function=source[start:source.index('/* Timer callback:',start)]
harness=r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include "ptp_peer_exchange.h"
typedef union { struct ptp_header_s header; struct ptp_delay_req_s delay_req; } ptp_msgbuf;
#define FAR
#define OK 0
#define CONFIG_ESP_PTP_PEER_LOSS_TEST 1
#define ptpinfo(...) do { if (0) printf(__VA_ARGS__); } while (0)
static int64_t test_time=100;
static unsigned network_calls;
#define ptperr(...) ((void)0)
#define ptpdebug(...) ((void)0)
static int locked;
#define portENTER_CRITICAL(lock) assert(!locked++)
#define portEXIT_CRITICAL(lock) assert(locked--==1)
static int scenario;
static uint16_t s_peer_ingress_sequence, s_peer_ingress_count;
struct ptp_state_s {
 struct ptp_announce_s own_identity;
 uint16_t delay_req_seq;
 struct {
  long delayreq_interval_ms;
  struct timespec delayreq_time,last_transmitted_delayreq;
  ptp_peer_exchange_t peer_exchange;
 } port[1];
};
static bool ptp_is_gptp(struct ptp_state_s *state) { (void)state;return true; }
static int64_t esp_timer_get_time(void) { return test_time; }
static int msec_to_log_period(long interval) { (void)interval;return 0; }
static void ptp_gettime(struct ptp_state_s *state,struct timespec *stamp) {(void)state;(void)stamp;}
static void timespec_to_ptp_format(struct timespec *stamp,uint8_t *wire) {(void)stamp;(void)wire;}
static unsigned ptp_get_sequence(const struct ptp_header_s *header) {return ((unsigned)header->sequenceid[0]<<8)|header->sequenceid[1];}
static void ptp_increment_sequence(uint16_t *sequence,struct ptp_header_s *header) {
 ++*sequence;header->sequenceid[0]=*sequence>>8;header->sequenceid[1]=*sequence;
}
static int ptp_net_send(struct ptp_state_s *state,ptp_msgbuf *request,size_t length,struct timespec *stamp) {
 ++network_calls;
 assert(!locked);assert(length==sizeof(struct ptp_pdelay_req_s));
 assert(!state->port[0].peer_exchange.published);
 struct ptp_delay_resp_s early={.header=request->header};early.header.flags[0]=2;
 early.header.sourceidentity[7]=7;
 memcpy(early.reqidentity,request->header.sourceidentity,8);
 memcpy(early.reqportindex,request->header.sourceportindex,2);
 struct timespec receive={100,5000};
 assert(ptp_peer_response(&state->port[0].peer_exchange,&early,&receive,100)==PTP_PEER_ACCEPTED);
 if(scenario==4) {
  struct ptp_delay_resp_follow_up_s follow={.header=early.header};
  memcpy(follow.reqidentity,early.reqidentity,8);
  memcpy(follow.reqportindex,early.reqportindex,2);
  ptp_peer_measurement_t measurement={0};
  assert(!ptp_peer_finish(&state->port[0].peer_exchange,&follow,100,&measurement));
  assert(state->port[0].peer_exchange.follow_up_pending);
 }
 if(scenario==1) return -1;
 if(scenario==2) ptp_peer_invalidate(&state->port[0].peer_exchange);
 if(scenario!=3) *stamp=(struct timespec){100,1000};
 return length;
}
'''
checks=r'''
int main(void) {
 for(scenario=0;scenario<5;scenario++) {
  struct ptp_state_s state={0};state.port[0].delayreq_interval_ms=1000;
  state.own_identity.header.sourceidentity[7]=1;
  state.own_identity.header.sourceportindex[1]=2;
  int result=ptp_send_delay_req(&state);
  assert((result<0)==(scenario==1));
  assert(state.port[0].peer_exchange.published==(scenario==0 || scenario==4));
  assert(state.port[0].peer_exchange.lost_responses==0);
  assert(!locked);
  if(scenario==1 || scenario==3) {
   assert(!state.port[0].peer_exchange.response_seen);
   assert(!state.port[0].peer_exchange.follow_up_pending);
  }
  if(scenario==0 || scenario==4) {
   assert(state.port[0].peer_exchange.sequence==1);
   assert(state.port[0].peer_exchange.requester[9]==2);
   assert(state.port[0].peer_exchange.transmit.tv_nsec==1000);
  }
 }
 scenario=0;
 struct ptp_state_s losses={0};losses.port[0].delayreq_interval_ms=1000;
 losses.own_identity.header.sourceidentity[7]=1;
 test_time=100;
 for(unsigned attempt=0;attempt<10;attempt++) {
  assert(ptp_send_delay_req(&losses)>0);
  assert(losses.port[0].peer_exchange.lost_responses==attempt);
  assert(!ptp_peer_expire(&losses.port[0].peer_exchange,test_time+999999));
  test_time+=1000000;
 }
 assert(losses.port[0].peer_exchange.missing_response==0);
 assert(losses.port[0].peer_exchange.missing_follow_up==9);
 const int64_t times[]={59999999,60000000,65999999,66000000,70000000};
 for(unsigned index=0;index<5;index++) {
  struct ptp_state_s state={0};state.port[0].delayreq_interval_ms=1000;
  unsigned before=network_calls;test_time=times[index];
  ptp_send_delay_req(&state);
  assert(network_calls-before==((index==1 || index==2)?0:1));
 }
 puts("Actual sender retains early RX and publishes only completed timestamps, cancels send failure and missing timestamps, rejects invalidation races");
}
'''
with tempfile.TemporaryDirectory() as temporary:
 path=Path(temporary);(path/'test.c').write_text(harness+function+checks)
 subprocess.run(['cc','-std=c11','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(component),str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
