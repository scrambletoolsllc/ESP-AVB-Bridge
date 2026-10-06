#include <assert.h>
#include <stdio.h>
#include "ptp_wifi_peers.h"
#include "ftm_association.h"

static ftm_association_packet_t export_packet(ptp_wifi_peers_t *peers, uint32_t serial)
{
    ptp_wifi_association_snapshot_t snapshot;
    assert(ptp_wifi_peers_snapshot(peers,2,2,&snapshot));
    ftm_association_packet_t packet = {.host_boot=1,.radio_boot=2,.publication=serial,
        .count=snapshot.count,.clock_identity={2}};
    for (unsigned index=0;index<snapshot.count;++index) {
        memcpy(packet.entries[index].mac,snapshot.entries[index].mac,6);
        packet.entries[index].port_number=snapshot.entries[index].port_number;
        packet.entries[index].association=snapshot.entries[index].association;
        packet.entries[index].sync_stopped=snapshot.entries[index].sync_stopped;
        packet.entries[index].sync_revision=snapshot.entries[index].sync_revision;
    }
    uint8_t wire[FTM_ASSOC_WIRE_SIZE];
    assert(ftm_association_encode(&packet,wire,sizeof(wire)));
    ftm_association_packet_t decoded;
    assert(ftm_association_decode(wire,sizeof(wire),&decoded));
    wire[FTM_ASSOC_POLICY_OFFSET+3]=128;
    assert(!ftm_association_decode(wire,sizeof(wire),&decoded));
    return packet;
}

int main(void)
{
    ptp_wifi_peers_t peers={0};
    const uint8_t first[6]={2,1},second[6]={2,2};
    ptp_wifi_peer_t *peer=ptp_wifi_peers_join(&peers,first);
    ptp_wifi_peer_t *other=ptp_wifi_peers_join(&peers,second);
    ptp_capable_message_t indication={.source_port={3,0,0,0,0,0,0,0,0,1}};
    assert(ptp_wifi_peers_capable(&peers,first,peer->association,&indication,100));
    ftm_association_packet_t packet=export_packet(&peers,1);
    ftm_association_state_t radio={0};uint8_t identity[10];
    assert(ftm_association_apply(&radio,&packet,1,2,100));
    assert(ftm_association_select(&radio,first,110,105,identity));
    ptp_interval_message_t request={.log_sync=127,.log_announce=127,.log_link_delay=127};
    memcpy(request.source_port,indication.source_port,10);
    assert(!ptp_wifi_peers_sync_interval(&peers,first,peer->association+1,&request));
    assert(!ptp_wifi_peers_sync_interval(&peers,second,other->association,&request));
    request.source_port[9]=2;
    assert(!ptp_wifi_peers_sync_interval(&peers,first,peer->association,&request));
    request.source_port[9]=1;
    assert(ptp_wifi_peers_sync_interval(&peers,first,peer->association,&request));
    assert(peer->sync_stopped && !other->sync_stopped);
    packet=export_packet(&peers,2);
    assert(ftm_association_apply(&radio,&packet,1,2,200));
    assert(!ftm_association_select(&radio,first,210,205,identity));
    assert(ftm_association_select(&radio,second,210,105,identity));
    for (int interval=-128;interval<=127;++interval) {
        if (interval==-3 || interval==126 || interval==127 || interval==-128) continue;
        request.log_sync=interval;
        assert(!ptp_wifi_peers_sync_interval(&peers,first,peer->association,&request));
        assert(peer->sync_stopped);
    }
    request.log_sync=-128;
    assert(ptp_wifi_peers_sync_interval(&peers,first,peer->association,&request) && peer->sync_stopped);
    request.log_sync=126;
    assert(ptp_wifi_peers_sync_interval(&peers,first,peer->association,&request) && !peer->sync_stopped);
    packet=export_packet(&peers,3);
    assert(ftm_association_apply(&radio,&packet,1,2,300));
    assert(!ftm_association_select(&radio,first,310,205,identity));
    assert(ftm_association_select(&radio,first,310,305,identity));
    assert(ftm_association_select(&radio,second,310,105,identity));
    /* A coalesced stop/reset still retires snapshots even if radio missed stop. */
    request.log_sync=127;
    assert(ptp_wifi_peers_sync_interval(&peers,first,peer->association,&request));
    request.log_sync=126;
    assert(ptp_wifi_peers_sync_interval(&peers,first,peer->association,&request));
    packet=export_packet(&peers,4);
    assert(ftm_association_apply(&radio,&packet,1,2,350));
    assert(!ftm_association_select(&radio,first,360,305,identity));
    assert(ftm_association_select(&radio,first,360,355,identity));
    assert(ftm_association_select(&radio,second,360,105,identity));
    request.log_sync=127;
    assert(ptp_wifi_peers_sync_interval(&peers,first,peer->association,&request));
    indication.source_port[9]=2;
    assert(ptp_wifi_peers_capable(&peers,first,peer->association,&indication,400));
    assert(!peer->sync_stopped);
    memcpy(request.source_port,indication.source_port,10);
    assert(ptp_wifi_peers_sync_interval(&peers,first,peer->association,&request));
    uint32_t retired=peer->association;
    ptp_wifi_peers_leave(&peers,first);
    peer=ptp_wifi_peers_join(&peers,first);
    assert(!peer->sync_stopped && peer->association!=retired);
    assert(!ptp_wifi_peers_sync_interval(&peers,first,retired,&request));
    puts("Per-peer sync stop/reset, identity/lifetime guards, codec and fresh-snapshot resumption passed");
}
