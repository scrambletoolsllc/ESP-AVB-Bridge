#!/usr/bin/env python3
"""Test the actual AP registry export with lifecycle and ownership guards."""
from pathlib import Path
import subprocess
import tempfile

component = Path('/home/dev/Development/esp_ptp')
source = (component / 'ptp.c').read_text()
start = source.index('bool ptpd_wifi_association_snapshot(')
function = source[start:source.index('\nstatic void ptp_arm_profile_fallback', start)]
harness = r'''
#include <assert.h>
#include <stdio.h>
#include "ptp_wifi_peers.h"
#define CONFIG_ESP_PTP_NUM_PORTS 3
#define ptp_port_medium_wifi_ftm 2
#define ptp_port_wifi_mode_ap 2
static unsigned lock_depth;
static uint32_t s_injected_generation[3];
#define portENTER_CRITICAL(lock) assert(lock_depth++ == 0)
#define portEXIT_CRITICAL(lock) assert(--lock_depth == 0)
struct ptp_port_s { bool enabled, link_up; int medium, wifi_mode; ptp_wifi_peers_t wifi_peers; };
struct ptp_state_s { bool gptp; struct ptp_port_s port[3]; };
static struct ptp_state_s *s_state;
static bool ptp_is_gptp(const struct ptp_state_s *state) { return state->gptp; }
'''
checks = r'''
int main(void) {
    ptp_wifi_association_snapshot_t snapshot, original;
    memset(&snapshot, 0xa5, sizeof(snapshot)); original = snapshot;
    assert(!ptpd_wifi_association_snapshot(1, &snapshot));
    assert(!memcmp(&snapshot, &original, sizeof(snapshot)));
    struct ptp_state_s state = {.gptp = true}; s_state = &state;
    struct ptp_port_s *port = &state.port[1];
    port->enabled = port->link_up = true;
    port->medium = 2; port->wifi_mode = 2;
    uint8_t address[6] = {2,1,2,3,4,5};
    ptp_wifi_peers_join(&port->wifi_peers, address);
    assert(!ptpd_wifi_association_snapshot(-1, &snapshot));
    assert(!ptpd_wifi_association_snapshot(3, &snapshot));
    assert(!ptpd_wifi_association_snapshot(1, NULL));
    assert(!memcmp(&snapshot, &original, sizeof(snapshot)));
#if CONFIG_ESP_PTP_HAS_AP_VIA_COPROCESSOR
    assert(!ptpd_wifi_association_snapshot(1, &snapshot));
    assert(!memcmp(&snapshot, &original, sizeof(snapshot)));
    int8_t early_interval=99;uint16_t early_sequence=99;
    assert(!ptpd_wifi_announce_begin(1,address,port->wifi_peers.entries[0].association,0,1,0,0,&early_interval,&early_sequence));
    assert(early_interval==99 && early_sequence==99);
#else
    assert(ptpd_wifi_association_snapshot(1, &snapshot));
    assert(snapshot.count == 1 && snapshot.entries[0].port_number == 2);
#endif
    const uint8_t macs[1][6]={{2,1,2,3,4,5}};
    assert(ptpd_wifi_association_reconcile(1, 7, 1, macs, 1));
    assert(s_injected_generation[1]==1 && !lock_depth);
    assert(ptpd_wifi_association_reconcile(1, 7, 1, macs, 1));
    assert(s_injected_generation[1]==1);
    assert(!ptpd_wifi_association_reconcile(-1, 7, 1, macs, 1));
    assert(!ptpd_wifi_association_reconcile(3, 7, 1, macs, 1));
    assert(ptpd_wifi_association_snapshot(1, &snapshot) && snapshot.radio_generation==1);
    original = snapshot;
    ptp_wifi_peer_t *peer = ptp_wifi_peers_find(&port->wifi_peers,address);
    int8_t advertised;uint16_t sequence;
    uint32_t token=ptpd_wifi_announce_begin(1,address,peer->association,peer->announce.revision,1,0,100,&advertised,&sequence);
    assert(token && advertised==0 && sequence==1 && !lock_depth);
    assert(ptpd_wifi_announce_finish(1,address,peer->association,token,true,101));
    assert(ptp_announce_request(&peer->announce,0,2));
    assert(!ptpd_wifi_announce_begin(1,address,peer->association,original.entries[0].announce_revision,1,0,200,&advertised,&sequence));
    assert(!ptpd_wifi_announce_finish(1,address,peer->association,token,true,201));
    assert(ptpd_wifi_association_snapshot(1,&snapshot));
    assert(snapshot.entries[0].announce_revision==peer->announce.revision);
    token=ptpd_wifi_announce_begin(1,address,peer->association,peer->announce.revision,1,0,300,&advertised,&sequence);
    assert(token && advertised==2 && sequence==2);
    assert(!ptpd_wifi_announce_finish(1,address,peer->association+1,token,true,301));
    assert(ptpd_wifi_announce_finish(1,address,peer->association,token,true,301));
    assert(peer->announce.slowdown_remaining==2);
    assert(ptp_announce_request(&peer->announce,0,127));
    assert(!ptpd_wifi_announce_begin(1,address,peer->association,peer->announce.revision,2,0,400,&advertised,&sequence));
    assert(!ptpd_wifi_announce_begin(-1,address,peer->association,0,1,0,400,&advertised,&sequence));
    assert(!ptpd_wifi_announce_begin(3,address,peer->association,0,1,0,400,&advertised,&sequence));
    assert(!ptpd_wifi_announce_begin(1,NULL,peer->association,0,1,0,400,&advertised,&sequence));
    assert(ptpd_wifi_association_snapshot(1,&snapshot));original=snapshot;
    port->enabled = false; assert(!ptpd_wifi_association_snapshot(1, &snapshot)); port->enabled = true;
    port->link_up = false; assert(!ptpd_wifi_association_snapshot(1, &snapshot)); port->link_up = true;
    port->medium = 1; assert(!ptpd_wifi_association_snapshot(1, &snapshot)); port->medium = 2;
    port->wifi_mode = 1; assert(!ptpd_wifi_association_snapshot(1, &snapshot)); port->wifi_mode = 2;
    state.gptp = false; assert(!ptpd_wifi_association_snapshot(1, &snapshot)); state.gptp = true;
    assert(!memcmp(&snapshot, &original, sizeof(snapshot)));
    port->link_up=false;assert(!ptpd_wifi_association_reconcile(1,7,2,macs,1));port->link_up=true;
    assert(s_injected_generation[1]==1);
#if CONFIG_ESP_PTP_HAS_AP_VIA_COPROCESSOR
    assert(ptp_announce_request(&peer->announce,0,126));
    token=ptpd_wifi_announce_begin(1,address,peer->association,peer->announce.revision,3,0,500,&advertised,&sequence);
    assert(token);
    ptp_wifi_peers_advance(&port->wifi_peers);
    assert(!ptpd_wifi_association_snapshot(1,&snapshot));
    assert(!ptpd_wifi_announce_finish(1,address,peer->association,token,true,501));
    assert(!ptpd_wifi_announce_begin(1,address,peer->association,peer->announce.revision,4,0,502,&advertised,&sequence));
    assert(ptpd_wifi_association_reconcile(1,7,2,macs,1));
    assert(ptpd_wifi_association_snapshot(1,&snapshot));
#endif
    ptp_wifi_peers_clear(&port->wifi_peers);
#if CONFIG_ESP_PTP_HAS_AP_VIA_COPROCESSOR
    assert(!ptpd_wifi_association_snapshot(1, &snapshot));
#else
    assert(ptpd_wifi_association_snapshot(1, &snapshot) && snapshot.count == 0);
#endif
    assert(original.count == 1 && !lock_depth);
    puts("Actual snapshot export lifecycle, guards, copied ownership and lock balance passed");
}
'''
with tempfile.TemporaryDirectory() as temporary:
    path = Path(temporary)
    (path / 'test.c').write_text(harness + function + checks)
    for hosted in (0, 1):
      subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    f'-DCONFIG_ESP_PTP_HAS_AP_VIA_COPROCESSOR={hosted}',
                    '-fsanitize=address,undefined', '-I', str(component),
                    str(path / 'test.c'), '-o', str(path / 'test')], check=True)
      subprocess.run([str(path / 'test')], check=True)
