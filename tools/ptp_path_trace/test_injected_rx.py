#!/usr/bin/env python3
"""Verify real RX publication/draining with bounded daemon ownership."""
from pathlib import Path
import subprocess, tempfile
source=Path('/home/dev/Development/esp_ptp/ptp.c').read_text()
state=source[source.index('#define PTP_INJECT_DEPTH'):source.index('/****************************************************************************', source.index('#define PTP_INJECT_DEPTH'))]
publish=source[source.index('int ptp_inject_received_frame_from('):source.index('\nint ptpd_inject_sync(')]
link=source[source.index('static void ptp_set_port_link('):source.index('static void ptp_eth_event_handler(')]
drain=source[source.index('    for (unsigned drained'):source.index('    struct ptp_delay_resp_follow_up_s deferred_follow_up;')]
start_index=source.index('  s_injected_head = s_injected_count = 0;')
start_queue=source[start_index:source.index('  portEXIT_CRITICAL(&s_injected_lock);',start_index)]
stop_index=source.index('  s_injected_enabled = false;')
stop_queue=source[stop_index:source.index('  portEXIT_CRITICAL(&s_injected_lock);',stop_index)]
harness=r"""
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <time.h>
#include <errno.h>
#include <stdio.h>
#define OK 0
#define CONFIG_ESP_PTP_NUM_PORTS 2
#define portMUX_TYPE int
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(lock) ((void)(lock))
#define portEXIT_CRITICAL(lock) ((void)(lock))
struct ptp_header_s { uint8_t bytes[34]; };
typedef union { uint8_t raw[256]; } ptp_msgbuf;
#define FAR
#define ptpinfo(...) ((void)0)
static int s_peer_lock;
struct peer_exchange {unsigned generation;};
static void ptp_peer_invalidate(struct peer_exchange *peer) {++peer->generation;}
struct ptp_port_s {ptp_msgbuf rxbuf;struct timespec rxtime;uint8_t rx_source_mac[6];
 bool rx_source_mac_valid,link_up;struct peer_exchange peer_exchange;
 struct {bool valid;} capable_receive;};
struct ptp_state_s {struct ptp_port_s port[2];};
static long timestamp;
static bool change_during_timestamp, restart_during_timestamp;
static void start_queue(void);
static void restart_queue(void);
static void change_link(void);
static int ptp_gettime(void *unused, struct timespec *out) {
 if(change_during_timestamp) change_link();
 if(restart_during_timestamp) restart_queue();
 (void)unused; *out=(struct timespec){.tv_sec=++timestamp}; return 0;
}
static unsigned processed;
static void ptp_process_rx_packet(struct ptp_state_s *state, int length, int ingress_port) {
 assert(ingress_port == (int)(processed % 2));
 assert(length==34); assert(state->port[0].rxbuf.raw[0]==processed);
 assert(state->port[0].rxbuf.raw[255]==0);
 assert(state->port[0].rxtime.tv_sec==(long)processed+2);
 if(state->port[0].rx_source_mac_valid) assert(state->port[0].rx_source_mac[0]==2);
 ++processed;
}
"""
checks=r"""
int main(void) {
 uint8_t frame[34]={0};
 assert(ptp_inject_received_frame(0, NULL, 34)==-EINVAL);
 assert(ptp_inject_received_frame(-1, frame, 34)==-EINVAL);
 assert(ptp_inject_received_frame(0, frame, 33)==-EINVAL);
 assert(ptp_inject_received_frame(0, frame, 257)==-EINVAL);
 assert(ptp_inject_received_frame(0, frame, 34)==-ESRCH);
 start_queue();
 for (unsigned index=0; index<8; ++index) {
  frame[0]=index; assert(ptp_inject_received_frame(index % 2, frame, 34)==0);
 }
 assert(processed==0);
 assert(ptp_inject_received_frame(0, frame, 34)==-ENOBUFS);
 memset(frame, 255, sizeof(frame));
 struct ptp_state_s state={0}; drain(&state);
 assert(processed==8 && s_injected_count==0);
 drain(&state); assert(processed==8);
 processed=0;timestamp=1;
 uint8_t sender[6]={2,3,4,5,6,7};frame[0]=0;
 assert(ptp_inject_received_frame_from(0,frame,34,sender)==0);
 sender[0]=99;drain(&state);assert(processed==1);
 assert(state.port[0].rx_source_mac_valid && state.port[0].rx_source_mac[0]==2);
 assert(ptp_inject_received_frame_from(0,frame,34,sender)==0);
 uint32_t before=s_injected_generation[0];
 ptp_set_port_link(&state,0,true);
 assert(s_injected_generation[0]==before+1);
 assert(state.port[0].peer_exchange.generation==1);
 ptp_set_port_link(&state,0,true);assert(s_injected_generation[0]==before+1);
 drain(&state);assert(processed==1 && s_injected_count==0);
 ptp_set_port_link(&state,0,false);assert(s_injected_generation[0]==before+2);
 change_during_timestamp=true;
 assert(ptp_inject_received_frame_from(0,frame,34,sender)==-ESTALE);
 assert(s_injected_count==0);
 change_during_timestamp=false;restart_during_timestamp=true;
 assert(ptp_inject_received_frame_from(0,frame,34,sender)==-ESTALE);
 assert(s_injected_count==0 && s_injected_enabled);
 puts("RX restart generation, source MAC ownership, stale generation rejection, RX bounds, full queue, copy ownership, FIFO, original timestamps and daemon-only processing passed");
}
"""
with tempfile.TemporaryDirectory() as temporary:
 path=Path(temporary); (path/'test.c').write_text(harness+state+link+'static void start_queue(void) {\n'+start_queue+'}\nstatic void restart_queue(void) {\n'+stop_queue+start_queue+'}\nstatic void change_link(void) {++s_injected_generation[0];}\n'+publish+'\nstatic void drain(struct ptp_state_s *state) {\n'+drain+'\n}\n'+checks)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',str(path/'test.c'),'-o',str(path/'test')],check=True)
 subprocess.run([str(path/'test')],check=True)
