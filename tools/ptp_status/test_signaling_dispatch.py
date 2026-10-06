#!/usr/bin/env python3
"""Exercise the actual Signaling branch with two ingress ports."""
from pathlib import Path
import subprocess,tempfile
component=Path('/home/dev/Development/esp_ptp')
source=(component/'ptp.c').read_text()
start=source.index('  case PTP_MSGTYPE_SIGNALING: {')
branch=source[start:source.index('\n#if defined(CONFIG_ESP_PTP_CLIENT)',start)]
branch=branch.replace('  case PTP_MSGTYPE_SIGNALING: {','{\nstruct ptp_port_s *ingress = &state->port[ingress_port];',1)
gate_start=source.index('  /* STA timing belongs to the currently associated AP. */')
gate=source[gate_start:source.index('  clock_gettime(CLOCK_MONOTONIC, &state->port[ingress_port].last_received_multicast);',gate_start)]
harness=r'''
#include <assert.h>
#include <time.h>
#include <stdio.h>
#include "ptp.h"
#include "ptp_signaling.h"
#include "ptp_capable_receive.h"
#include "ptp_wifi_neighbor.h"
#include "ptp_wifi_peers.h"
#include "ptp_wired_capable.h"
#define ptp_port_medium_wifi_ftm 2
#define ptp_port_wifi_mode_sta 1
#define ptp_port_wifi_mode_ap 2
#include "ptp_peer_rate.h"
#include "ptp_peer_exchange.h"
#define portENTER_CRITICAL(lock) ((void)0)
#define portEXIT_CRITICAL(lock) ((void)0)
#define ptp_port_medium_eth_hwts 1
static int64_t esp_timer_get_time(void) {return 100;}
#define CONFIG_ESP_PTP_DOMAIN 0
#define CONFIG_ESP_PTP_ANNOUNCE_INTERVAL_MS 1000
static int8_t msec_to_log_period(uint16_t value){assert(value==1000);return 0;}
#define CONFIG_ESP_PTP_NUM_PORTS 2
#define OK 0
#define ptpinfo(...) ((void)printf(__VA_ARGS__))
struct ptp_port_s {
 union { uint8_t raw[256]; } rxbuf;
 struct timespec last_received_capable_indication;
 ptp_capable_message_t last_capable_indication;
 unsigned capable_indication_count;
 bool enabled,link_up; int medium,wifi_mode;
 ptp_wifi_peers_t wifi_peers;
 ptp_wifi_neighbor_t wifi_neighbor;uint32_t rx_association;uint8_t rx_source_mac[6];bool rx_source_mac_valid;
 ptp_peer_rate_t peer_rate;
 ptp_peer_exchange_t peer_exchange;
 ptp_capable_receive_t capable_receive;
 ptp_wired_capable_t wired_capable;
};
struct ptp_state_s { struct ptp_announce_s own_identity; struct ptp_port_s port[2]; };
'''
harness += 'static bool ptp_is_gptp(struct ptp_state_s *state) {(void)state;return true;}\n'
checks=r'''
int main(void) {
 struct ptp_state_s state={0};
#if CONFIG_ESP_PTP_HAS_AP_VIA_COPROCESSOR
 struct ptp_port_s *hosted_port=&state.port[0];
 hosted_port->medium=2;hosted_port->wifi_mode=2;hosted_port->rx_source_mac_valid=true;
 const uint8_t hosted_macs[1][6]={{2,1}};
 memcpy(hosted_port->rx_source_mac,hosted_macs[0],6);
 ptp_wifi_peers_join(&hosted_port->wifi_peers,hosted_macs[0]);
 assert(!admit(&state,0));
 assert(ptp_wifi_peers_reconcile(&hosted_port->wifi_peers,7,1,hosted_macs,1));
 assert(admit(&state,0));
 ptp_wifi_peers_advance(&hosted_port->wifi_peers);assert(!admit(&state,0));
 assert(ptp_wifi_peers_reconcile(&hosted_port->wifi_peers,7,2,hosted_macs,1));
 assert(admit(&state,0));
 puts("Hosted AP ingress rejects provisional and unreconciled identities");
 return 0;
#endif
 memset(state.own_identity.header.sourceidentity,1,8);
 uint8_t *message=state.port[0].rxbuf.raw;
 message[0]=0x1c;message[1]=2;message[3]=60;
 memset(message+20,2,8);message[29]=1;
 memcpy(message+34,state.own_identity.header.sourceidentity,8);message[43]=2;
 const uint8_t tlv[16]={0x80,0,0,12,0,0x80,0xc2,0,0,4,0xff,0,0,0,0,0};
 memcpy(message+44,tlv,16);
 assert(dispatch(&state,60,1)==0);
 assert(state.port[1].capable_indication_count==1);
 assert(state.port[1].last_capable_indication.log_interval==-1);
 assert(state.port[1].last_received_capable_indication.tv_sec>0);
 assert(state.port[0].capable_indication_count==0);
 assert(dispatch(&state,60,0)==0); /* Target is port2, not port1. */
 assert(state.port[0].capable_indication_count==0);
 memset(message+34,255,10);
 assert(dispatch(&state,60,0)==0);
 assert(state.port[0].capable_indication_count==1);
 assert(!state.port[0].capable_receive.valid);
 state.port[0].enabled=state.port[0].link_up=true;
 state.port[0].medium=1;state.port[0].peer_rate.valid=true;
 memcpy(state.port[0].peer_rate.responder,message+20,10);
 assert(dispatch(&state,60,0)==0);
 assert(ptp_neighbor_capable(&state.port[0].capable_receive,message+20,0,100));
 assert(!ptp_neighbor_capable(&state.port[0].capable_receive,message+20,0,4500100));
 message[29]=3;
 assert(dispatch(&state,60,0)==0);
 assert(state.port[0].capable_receive.message.source_port[9]==1);
 message[29]=1;
 message[4]=1;
 assert(dispatch(&state,60,1)==0);
 assert(state.port[1].capable_indication_count==1);
 message[4]=0; message[47]=14;
 assert(dispatch(&state,60,1)==0);
 assert(state.port[1].capable_indication_count==1);
 message[47]=12;message[4]=0;
 struct ptp_port_s *wireless=&state.port[0];
 wireless->medium=2;wireless->wifi_mode=1;
 wireless->capable_receive.valid=false;
 uint8_t ap[6]={2,1,2,3,4,5};
 assert(!admit(&state,0));
 ptp_wifi_neighbor_associate(&wireless->wifi_neighbor,ap);
 assert(!admit(&state,0)); /* Unknown sender metadata. */
 wireless->rx_source_mac_valid=true;memcpy(wireless->rx_source_mac,ap,6);
 assert(admit(&state,0));
 dispatch(&state,60,0);assert(!wireless->capable_receive.valid); /* No Announce binding. */
 assert(ptp_wifi_neighbor_bind(&wireless->wifi_neighbor,wireless->rx_association,ap,message+20));
 dispatch(&state,60,0);assert(wireless->capable_receive.valid);
 wireless->capable_receive.valid=false;message[29]=9;
 dispatch(&state,60,0);assert(!wireless->capable_receive.valid);message[29]=1;
 wireless->rx_source_mac[5]++;
 assert(!admit(&state,0));
 dispatch(&state,60,0);assert(!wireless->capable_receive.valid);
 wireless->rx_source_mac[5]--;
 ptp_wifi_neighbor_associate(&wireless->wifi_neighbor,ap);
 dispatch(&state,60,0);assert(!wireless->capable_receive.valid);
 assert(admit(&state,0));
 assert(ptp_wifi_neighbor_bind(&wireless->wifi_neighbor,wireless->rx_association,ap,message+20));
 uint8_t sta_remote[10];memcpy(sta_remote,message+20,10);
 assert(ptp_signaling_write_capable_interval(message,256,sta_remote,0,20,1)==58);
 dispatch(&state,58,0);assert(wireless->wifi_neighbor.transmit.interval.log_interval==1);
 assert(wireless->wifi_neighbor.transmit.interval.slowdown_remaining==9);
 message[29]=4;message[54]=127;
 dispatch(&state,58,0);assert(wireless->wifi_neighbor.transmit.interval.log_interval==1);
 message[29]=sta_remote[9];wireless->rx_association++;
 dispatch(&state,58,0);assert(wireless->wifi_neighbor.transmit.interval.log_interval==1);
 wireless->rx_association--;wireless->rx_source_mac[5]++;
 dispatch(&state,58,0);assert(wireless->wifi_neighbor.transmit.interval.log_interval==1);
 wireless->rx_source_mac[5]--;dispatch(&state,58,0);
 assert(wireless->wifi_neighbor.transmit.interval.log_interval==127);
 message[54]=126;dispatch(&state,58,0);
 assert(wireless->wifi_neighbor.transmit.interval.log_interval==0);
 assert(ptp_signaling_write_capable(message,256,sta_remote,0,21,0)==60);
 message[44]=0;message[45]=3;message[53]=2;message[54]=128;message[55]=127;message[56]=128;
 message[29]^=0x40;dispatch(&state,60,0);assert(!wireless->wifi_neighbor.sync_stopped);
 message[29]^=0x40;wireless->rx_association++;
 dispatch(&state,60,0);assert(!wireless->wifi_neighbor.sync_stopped);wireless->rx_association--;
 dispatch(&state,60,0);assert(wireless->wifi_neighbor.sync_stopped);
 uint32_t stop_revision=wireless->wifi_neighbor.sync_revision;
 message[55]=0;dispatch(&state,60,0);assert(wireless->wifi_neighbor.sync_stopped);
 message[55]=128;dispatch(&state,60,0);assert(wireless->wifi_neighbor.sync_revision==stop_revision);
 message[55]=126;dispatch(&state,60,0);assert(!wireless->wifi_neighbor.sync_stopped);
 assert(wireless->wifi_neighbor.sync_revision!=stop_revision);
 assert(wireless->wifi_neighbor.transmit.interval.log_interval==0);
 puts("Actual STA synchronization interval dispatch: stop/reset, unsupported value and lifetime guards passed");
 uint32_t sta_token=ptp_capable_schedule_begin(&wireless->wifi_neighbor.transmit,true,100);
 assert(sta_token);
 uint8_t replacement_identity[10];memcpy(replacement_identity,sta_remote,10);replacement_identity[9]=4;
 assert(ptp_wifi_neighbor_bind(&wireless->wifi_neighbor,wireless->rx_association,ap,replacement_identity));
 assert(!ptp_wifi_neighbor_sent(&wireless->wifi_neighbor,ap,wireless->rx_association,sta_token,true,101));
 ptp_wifi_neighbor_associate(&wireless->wifi_neighbor,ap);
 assert(!wireless->wifi_neighbor.bound && wireless->wifi_neighbor.transmit.interval.log_interval==0);
 assert(ptp_signaling_write_capable(message,256,sta_remote,0,21,-1)==60);
 puts("Actual STA interval dispatch: full identity, association, MAC, stop/reset and identity replacement passed");
 puts("Actual STA sender gate, neighbor-bound Signaling, reconnect, port targeting and malformed-message rejection passed");
 wireless->wifi_mode=2;
 assert(!admit(&state,0));
 ptp_wifi_peer_t *peer=ptp_wifi_peers_join(&wireless->wifi_peers,ap);
 assert(peer && admit(&state,0));
 dispatch(&state,60,0);assert(peer->bound && peer->capable.valid);
 uint32_t old_association=wireless->rx_association;
 peer=ptp_wifi_peers_join(&wireless->wifi_peers,ap);
 assert(peer && peer->association!=old_association);
 dispatch(&state,60,0);assert(!peer->bound && !peer->capable.valid);
 assert(admit(&state,0));dispatch(&state,60,0);assert(peer->capable.valid);
 uint8_t remote_port[10];memcpy(remote_port,message+20,10);
 assert(ptp_signaling_write_capable_interval(message,256,remote_port,0,5,2)==58);
 dispatch(&state,58,0);assert(peer->transmit.interval.log_interval==2);
 assert(peer->transmit.interval.slowdown_remaining==9);
 uint32_t token=ptp_capable_schedule_begin(&peer->transmit,true,100);
 assert(token);
 message[54]=127;message[29]=7;
 dispatch(&state,58,0);assert(peer->transmit.interval.log_interval==2);
 message[29]=remote_port[9];wireless->rx_association++;
 dispatch(&state,58,0);assert(peer->transmit.interval.log_interval==2);
 wireless->rx_association--;wireless->enabled=false;
 dispatch(&state,58,0);assert(peer->transmit.interval.log_interval==2);
 wireless->enabled=true;message[4]=1;
 dispatch(&state,58,0);assert(peer->transmit.interval.log_interval==2);
 message[4]=0;message[54]=(uint8_t)-4;
 dispatch(&state,58,0);assert(peer->transmit.interval.log_interval==-3 && !peer->transmit.interval.slowdown_remaining);
 message[54]=(uint8_t)-30;dispatch(&state,58,0);assert(peer->transmit.interval.log_interval==-3);
 message[54]=127;dispatch(&state,58,0);
 assert(peer->transmit.interval.log_interval==127 && !peer->transmit.pending);
 message[54]=126;dispatch(&state,58,0);assert(peer->transmit.interval.log_interval==0);
 /* A malformed second known TLV must not partially apply the first. */
 assert(ptp_signaling_write_capable(message,256,remote_port,0,6,0)==60);
 uint8_t request[58];assert(ptp_signaling_write_capable_interval(request,58,remote_port,0,7,2)==58);
 memcpy(message+60,request+44,14);message[3]=74;message[63]=8;
 unsigned previous_count=wireless->capable_indication_count;
 dispatch(&state,74,0);assert(wireless->capable_indication_count==previous_count);
 /* Malformed synchronization interval must also prevent capability mutation. */
 message[60]=0;message[61]=3;message[69]=2;message[63]=10;
 dispatch(&state,74,0);assert(wireless->capable_indication_count==previous_count);
 message[63]=12;message[3]=76;message[74]=0;message[75]=0;
 dispatch(&state,76,0);assert(wireless->capable_indication_count==previous_count+1);
 /* A valid subtype 2 is structurally accepted; timing policy is separate. */
 previous_count++;message[60]=0x80;message[61]=0;message[69]=5;message[3]=74;

 assert(peer->transmit.interval.log_interval==0);
 message[63]=10;dispatch(&state,74,0);
 assert(peer->transmit.interval.log_interval==2 && wireless->capable_indication_count==previous_count+1);
 /* A second association accepts only its own logical target (port 3 on transport 1). */
 uint8_t second_mac[6]={2,9,8,7,6,5};
 ptp_wifi_peer_t *second_peer=ptp_wifi_peers_join(&wireless->wifi_peers,second_mac);
 memcpy(wireless->rx_source_mac,second_mac,6);assert(admit(&state,0));
 assert(ptp_signaling_write_capable(message,256,remote_port,0,22,0)==60);
 memcpy(message+34,state.own_identity.header.sourceidentity,8);message[42]=0;message[43]=1;
 dispatch(&state,60,0);assert(!second_peer->bound);
 message[43]=3;dispatch(&state,60,0);assert(second_peer->bound);
 assert(ptp_signaling_write_capable_interval(message,256,remote_port,0,23,-3)==58);
 memcpy(message+34,state.own_identity.header.sourceidentity,8);message[42]=0;message[43]=1;
 dispatch(&state,58,0);assert(second_peer->transmit.interval.log_interval==0);
 message[43]=3;dispatch(&state,58,0);assert(second_peer->transmit.interval.log_interval==-3);
 memcpy(wireless->rx_source_mac,ap,6);assert(admit(&state,0));
 puts("Actual AP interval request dispatch: identity, association, enable/domain/rate guards, stop/reset, mixed TLV atomic validation passed");
 /* Message interval sync control is separate from capability cadence. */
 assert(ptp_signaling_write_capable(message,256,remote_port,0,24,0)==60);
 message[44]=0;message[45]=3;message[53]=2;message[54]=128;message[55]=127;message[56]=128;
 memcpy(message+34,state.own_identity.header.sourceidentity,8);message[42]=0;message[43]=3;
 dispatch(&state,60,0);assert(!peer->sync_stopped);
 message[43]=1;dispatch(&state,60,0);
 assert(peer->sync_stopped && !second_peer->sync_stopped);
 message[55]=0;dispatch(&state,60,0);assert(peer->sync_stopped);
 message[55]=128;dispatch(&state,60,0);assert(peer->sync_stopped);
 message[55]=126;dispatch(&state,60,0);assert(!peer->sync_stopped);
 puts("Actual AP synchronization stop/reset isolates logical targets and ignores unsupported rates");
 /* Both fields are independent: unsupported sync must not mask valid Announce. */
 message[55]=0;message[56]=2;dispatch(&state,60,0);
 assert(peer->announce.log_interval==2 && peer->announce.slowdown_remaining==3);
 assert(second_peer->announce.log_interval==0 && !peer->sync_stopped);
 message[43]=3;message[56]=127;dispatch(&state,60,0);
 assert(peer->announce.log_interval==2 && second_peer->announce.log_interval==0);
 message[43]=1;dispatch(&state,60,0);assert(peer->announce.log_interval==127);
 uint32_t announce_revision=peer->announce.revision;
 message[56]=128;dispatch(&state,60,0);assert(peer->announce.revision==announce_revision);
 message[56]=126;dispatch(&state,60,0);assert(peer->announce.log_interval==0);
 message[56]=(uint8_t)-3;dispatch(&state,60,0);assert(peer->announce.log_interval==0);
 puts("Actual AP Announce interval dispatch: independent fields, directed target, slower/stop/reset and closest-supported rate passed");
 ptp_wifi_peers_leave(&wireless->wifi_peers,ap);
 assert(!admit(&state,0));
 puts("Actual AP gate and per-association capability dispatch reject unknown and stale senders");
 wireless->medium=1;wireless->peer_rate.valid=true;wireless->peer_rate.lifecycle=7;
 wireless->peer_exchange.lifecycle=7;memcpy(wireless->peer_rate.responder,remote_port,10);
 assert(ptp_signaling_write_capable_interval(message,256,remote_port,0,30,1)==58);
 dispatch(&state,58,0);assert(wireless->wired_capable.transmit.interval.log_interval==1);
 message[54]=127;message[29]=9;dispatch(&state,58,0);
 assert(wireless->wired_capable.transmit.interval.log_interval==1);
 message[29]=remote_port[9];wireless->peer_rate.valid=false;dispatch(&state,58,0);
 assert(wireless->wired_capable.transmit.interval.log_interval==1);
 wireless->peer_rate.valid=true;wireless->peer_exchange.lifecycle=8;dispatch(&state,58,0);
 assert(wireless->wired_capable.transmit.interval.log_interval==1);
 wireless->peer_rate.lifecycle=8;dispatch(&state,58,0);
 assert(wireless->wired_capable.transmit.interval.log_interval==127);
 puts("Actual wired interval dispatch: measured identity, rate validity and peer lifecycle guards passed");
 /* Previous cases also cover wired dispatch. */
 puts("Actual Signaling dispatch preserves port targeting and ignores wrong-domain/truncated indications");
}
'''
with tempfile.TemporaryDirectory() as temporary:
 path=Path(temporary);(path/'test.c').write_text(harness+'\nstatic int admit(struct ptp_state_s *state,int ingress_port) {\n'+gate+'return 1;\n}\nstatic int dispatch(struct ptp_state_s *state, size_t length, int ingress_port)\n'+branch+checks)
 for hosted in (0,1):
  subprocess.run(['cc','-std=c11','-D_POSIX_C_SOURCE=200809L',f'-DCONFIG_ESP_PTP_HAS_AP_VIA_COPROCESSOR={hosted}','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(component),str(path/'test.c'),'-o',str(path/'test')],check=True)
  subprocess.run([str(path/'test')],check=True)
