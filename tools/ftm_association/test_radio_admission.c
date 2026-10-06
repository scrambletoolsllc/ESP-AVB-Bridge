#include <assert.h>
#include <stdio.h>
#include "ftm_radio_association.h"

int main(void)
{
    ftm_radio_association_t radio = {0};
    ftm_association_packet_t packet = {.host_boot=1, .radio_boot=2,
        .publication=3, .count=1, .clock_identity={2},
        .entries={{.mac={2,1,2,3,4,5}, .port_number=2, .association=10}}};
    const uint8_t *mac = packet.entries[0].mac;
    uint32_t first = ftm_radio_association_change(&radio, mac, true);
    assert(first && !ftm_radio_association_accepts(&radio, first, &packet));
    assert(!ftm_radio_association_forwarded(&radio, first, false));
    assert(!ftm_radio_association_accepts(&radio, first, &packet));
    assert(ftm_radio_association_forwarded(&radio, first, true));
    assert(ftm_radio_association_accepts(&radio, first, &packet));
    /* No map need have been installed before this reconnect. */
    uint32_t disconnected = ftm_radio_association_change(&radio, mac, false);
    assert(!ftm_radio_association_accepts(&radio, first, &packet));
    uint32_t rejoined = ftm_radio_association_change(&radio, mac, true);
    assert(!ftm_radio_association_forwarded(&radio, disconnected, true));
    assert(!ftm_radio_association_accepts(&radio, rejoined, &packet));
    assert(ftm_radio_association_forwarded(&radio, rejoined, true));
    assert(!ftm_radio_association_accepts(&radio, first, &packet));
    assert(ftm_radio_association_accepts(&radio, rejoined, &packet));
    uint8_t other[6] = {2,1,2,3,4,6};
    uint32_t changed = ftm_radio_association_change(&radio, other, true);
    assert(ftm_radio_association_forwarded(&radio, changed, true));
    assert(!ftm_radio_association_accepts(&radio, changed, &packet));
    packet.count=2;packet.entries[1]=packet.entries[0];
    memcpy(packet.entries[1].mac, other, 6);packet.entries[1].port_number=18;
    assert(ftm_radio_association_accepts(&radio, changed, &packet));
    uint8_t wire[FTM_ASSOC_ADMISSION_SIZE + 1];memset(wire,0xa5,sizeof(wire));
    assert(ftm_radio_association_encode(changed,&packet,wire,sizeof(wire)));
    assert(!memcmp(wire,"FAG1",4) && wire[4]==changed && wire[8]=='F');
    assert(wire[FTM_ASSOC_ADMISSION_SIZE]==0xa5);
    ftm_association_packet_t decoded = {0};uint32_t generation=0;
    assert(ftm_radio_association_decode(wire,FTM_ASSOC_ADMISSION_SIZE,&generation,&decoded));
    assert(generation==changed && decoded.count==2);
    ftm_association_packet_t before=decoded;
    for(unsigned size=0;size<FTM_ASSOC_ADMISSION_SIZE;++size){
        assert(!ftm_radio_association_decode(wire,size,&generation,&decoded));
        assert(generation==changed && !memcmp(&before,&decoded,sizeof(before)));
    }
    wire[8]^=1;assert(!ftm_radio_association_decode(wire,FTM_ASSOC_ADMISSION_SIZE,&generation,&decoded));
    assert(generation==changed && !memcmp(&before,&decoded,sizeof(before)));
    ftm_radio_association_change(&radio,NULL,false);
    assert(!radio.count && !ftm_radio_association_accepts(&radio,changed,&packet));
    radio.generation=UINT32_MAX;
    assert(ftm_radio_association_change(&radio,mac,true)==1);
    puts("Radio admission: delayed first map, reconnect, notification failure/order, membership, stop, wrap and wire bounds passed");
}
