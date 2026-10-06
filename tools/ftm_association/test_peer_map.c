#include <assert.h>
#include <stdio.h>
#include "ptp_wifi_peers.h"
#include "ftm_association.h"

int main(void)
{
    /* Every configured transport keeps its physical number; all extras are unique. */
    bool used[65] = {0};
    for (unsigned port = 1; port <= 4; ++port)
        for (unsigned slot = 0; slot < 16; ++slot) {
            unsigned number = ptp_wifi_association_port(port, 4, slot);
            assert(number && number <= 64 && !used[number]);
            used[number] = true;
            assert(slot ? number > 4 : number == port);
        }
    assert(!ptp_wifi_association_port(0, 2, 0));
    assert(!ptp_wifi_association_port(3, 2, 0));
    assert(!ptp_wifi_association_port(1, 4096, 0));
    assert(!ptp_wifi_association_port(1, 2, 16));
    assert(ptp_wifi_association_port(4095, 4095, 15) == 65520);

    ptp_wifi_peers_t peers = {0};
    uint8_t first_mac[6] = {2, 1, 2, 3, 4, 5};
    uint8_t second_mac[6] = {2, 1, 2, 3, 4, 6};
    ptp_wifi_peer_t *first = ptp_wifi_peers_join(&peers, first_mac);
    uint32_t first_lifetime = first->association;
    ptp_wifi_peer_t *second = ptp_wifi_peers_join(&peers, second_mac);
    uint32_t second_lifetime = second->association;
    ptp_wifi_association_snapshot_t snapshot;
    assert(ptp_wifi_peers_snapshot(&peers, 2, 2, &snapshot));
    assert(snapshot.count == 2 && snapshot.entries[0].port_number == 2);
    assert(snapshot.entries[1].port_number == 18);
    ptp_wifi_association_snapshot_t original = snapshot;
    assert(!ptp_wifi_peers_snapshot(&peers, 3, 2, &snapshot));
    assert(!memcmp(&snapshot, &original, sizeof(snapshot)));

    ptp_wifi_peers_leave(&peers, first_mac);
    assert(ptp_wifi_peers_snapshot(&peers, 2, 2, &snapshot));
    assert(snapshot.count == 1 && snapshot.entries[0].port_number == 18);
    assert(snapshot.entries[0].association == second_lifetime);
    first = ptp_wifi_peers_join(&peers, first_mac);
    assert(first->association != first_lifetime);
    assert(ptp_wifi_peers_snapshot(&peers, 2, 2, &snapshot));
    assert(snapshot.entries[0].port_number == 2);
    assert(snapshot.entries[1].port_number == 18);
    assert(snapshot.entries[1].association == second_lifetime);

    ftm_association_packet_t packet = {.host_boot = 1, .radio_boot = 2,
        .publication = 3, .count = snapshot.count, .clock_identity = {2}};
    for (unsigned index = 0; index < snapshot.count; ++index) {
        memcpy(packet.entries[index].mac, snapshot.entries[index].mac, 6);
        packet.entries[index].port_number = snapshot.entries[index].port_number;
        packet.entries[index].association = snapshot.entries[index].association;
    }
    uint8_t wire[FTM_ASSOC_WIRE_SIZE];
    assert(ftm_association_encode(&packet, wire, sizeof(wire)));
    ftm_association_packet_t decoded;
    assert(ftm_association_decode(wire, sizeof(wire), &decoded));
    ftm_association_state_t radio = {0};
    assert(ftm_association_apply(&radio, &decoded, 1, 2, 100));
    uint8_t identity[10];
    assert(ftm_association_select(&radio, first_mac, 200, 150, identity));
    assert(identity[8] == 0 && identity[9] == 2);
    assert(ftm_association_select(&radio, second_mac, 200, 150, identity));
    assert(identity[8] == 0 && identity[9] == 18);
    ptp_wifi_peers_clear(&peers);
    assert(ptp_wifi_peers_snapshot(&peers, 2, 2, &snapshot) && snapshot.count == 0);
    assert(original.count == 2 && original.entries[0].association == first_lifetime);
    puts("Logical port uniqueness, stable survivors, reconnect and host-to-radio mapping passed");
}
