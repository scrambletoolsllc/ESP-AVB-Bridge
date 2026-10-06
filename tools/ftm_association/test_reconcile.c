#include <assert.h>
#include <stdio.h>
#include "ptp_wifi_peers.h"
int main(void)
{
    ptp_wifi_peers_t peers={0};
    uint8_t macs[2][6]={{2,1,2,3,4,5},{2,1,2,3,4,6}};
    ptp_wifi_peer_t *first=ptp_wifi_peers_join(&peers,macs[0]);
    ptp_wifi_peer_t *second=ptp_wifi_peers_join(&peers,macs[1]);
    uint32_t old_first=first->association,old_second=second->association;
    first->bound=true;second->capable.valid=true;
    assert(ptp_wifi_peers_reconcile(&peers,10,1,macs,2));
    assert(first->association!=old_first && second->association!=old_second);
    assert(!first->bound && !second->capable.valid);
    ptp_wifi_peers_t saved=peers;
    assert(ptp_wifi_peers_reconcile(&peers,10,1,macs,2));
    assert(!memcmp(&saved,&peers,sizeof(saved)));
    assert(!ptp_wifi_peers_reconcile(&peers,10,1,macs,1));
    assert(!memcmp(&saved,&peers,sizeof(saved)));
    uint8_t invalid[2][6]={{2,1,2,3,4,5},{2,1,2,3,4,5}};
    assert(!ptp_wifi_peers_reconcile(&peers,10,2,invalid,2));
    assert(!memcmp(&saved,&peers,sizeof(saved)));
    ptp_wifi_peers_join(&peers,macs[0]);
    saved=peers;
    assert(!ptp_wifi_peers_reconcile(&peers,10,1,macs,2));
    assert(!memcmp(&saved,&peers,sizeof(saved)));
    ptp_wifi_association_snapshot_t snapshot;
    assert(ptp_wifi_peers_snapshot(&peers,2,2,&snapshot));
    assert(!snapshot.radio_generation && !snapshot.radio_boot);
    assert(ptp_wifi_peers_reconcile(&peers,10,2,&macs[1],1));
    assert(!first->associated && second->associated);
    assert(ptp_wifi_peers_snapshot(&peers,2,2,&snapshot));
    assert(snapshot.count==1 && snapshot.entries[0].port_number==18);
    assert(snapshot.radio_generation==2 && snapshot.radio_boot==10);
    assert(!ptp_wifi_peers_reconcile(&peers,10,1,macs,2));
    assert(ptp_wifi_peers_reconcile(&peers,11,UINT32_MAX,macs,2));
    assert(ptp_wifi_peers_reconcile(&peers,11,1,macs,2));
    assert(ptp_wifi_peers_reconcile(&peers,11,2,NULL,0));
    assert(ptp_wifi_peers_snapshot(&peers,2,2,&snapshot) && snapshot.count==0);
    puts("Host reconciliation: idempotence, stale epochs, native event barrier, reset state, survivor ports, boot/wrap and validation passed");
}
