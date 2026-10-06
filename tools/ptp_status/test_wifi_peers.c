#include <assert.h>
#include <stdio.h>
#include "ptp_wifi_peers.h"
int main(void) {
    ptp_wifi_peers_t peers={0};
    uint8_t address[6]={0,1,2,3,4,5};
    ptp_wifi_peer_t *first=ptp_wifi_peers_join(&peers,address);
    assert(first && first->associated && first->association && !first->bound);
    ptp_capable_message_t message={.log_interval=0};message.source_port[7]=2;message.source_port[9]=1;
    uint32_t association=first->association;
    assert(ptp_wifi_peers_capable(&peers,address,association,&message,100));
    assert(first->bound && ptp_neighbor_capable(&first->capable,message.source_port,association,101));
    assert(!ptp_neighbor_capable(&first->capable,message.source_port,association,9000100));
    for(unsigned index=1;index<PTP_WIFI_PEERS_MAX;++index){
        uint8_t other[6]={2,1,2,3,4,index};
        ptp_wifi_peer_t *peer=ptp_wifi_peers_join(&peers,other);assert(peer && peer!=first);
        assert(!peer->capable.valid);
    }
    uint8_t overflow[6]={4,1,2,3,4,5};
    assert(!ptp_wifi_peers_join(&peers,overflow));
    assert(first->capable.valid && first->association==association);
    first=ptp_wifi_peers_join(&peers,address);
    assert(first && first->association!=association && !first->bound && !first->capable.valid);
    assert(!ptp_wifi_peers_capable(&peers,address,association,&message,200));
    assert(ptp_wifi_peers_capable(&peers,address,first->association,&message,200));
    message.source_port[9]=3;
    assert(ptp_wifi_peers_capable(&peers,address,first->association,&message,201));
    assert(first->port_identity[9]==3 && first->capable.message.source_port[9]==3);
    ptp_wifi_peers_leave(&peers,address);assert(!ptp_wifi_peers_find(&peers,address));
    assert(ptp_wifi_peers_join(&peers,overflow));
    uint32_t previous=peers.generation;ptp_wifi_peers_clear(&peers);assert(peers.generation!=previous);
    for(unsigned index=0;index<PTP_WIFI_PEERS_MAX;++index)assert(!peers.entries[index].associated);
    uint8_t zero[6]={0},group[6]={1};assert(!ptp_wifi_peers_join(&peers,zero));assert(!ptp_wifi_peers_join(&peers,group));
    peers.generation=UINT32_MAX;assert(ptp_wifi_peers_join(&peers,address)->association==1);
    puts("Per-station capability isolation, full table, reconnect, stale lifetime, identity change, expiry and generation wrap passed");
}
