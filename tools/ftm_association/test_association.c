#include <assert.h>
#include <stdio.h>
#include "ftm_association.h"

static ftm_association_packet_t packet(void)
{
    ftm_association_packet_t value = {.host_boot = 0x11223344, .radio_boot = 0x55667788,
        .publication = 1, .count = 2, .clock_identity = {0x80,0xf1,0xb2,0xff,0xfe,0xd2,0xca,0xa9}};
    value.entries[0] = (ftm_association_entry_t){.mac = {2,1,2,3,4,5}, .port_number = 2, .association = 7};
    value.entries[1] = (ftm_association_entry_t){.mac = {2,1,2,3,4,6}, .port_number = 18, .association = 8};
    return value;
}

int main(void)
{
    ftm_association_packet_t original = packet(), decoded;
    uint8_t wire[FTM_ASSOC_WIRE_SIZE + 1];
    memset(wire, 0xa5, sizeof(wire));
    assert(ftm_association_encode(&original, wire, sizeof(wire)));
    const uint8_t golden[] = {
        0x46,0x41,0x4d,0x31,2,0,0,0,0x44,0x33,0x22,0x11,0x88,0x77,0x66,0x55,
        1,0,0,0,2,0,0,0,0x80,0xf1,0xb2,0xff,0xfe,0xd2,0xca,0xa9,
        2,1,2,3,4,5,2,0,7,0,0,0,0,0,0,0,2,1,2,3,4,6,18,0,8,0,0,0,0,0,0,0
    };
    assert(!memcmp(wire, golden, sizeof(golden)));
    for (unsigned index = sizeof(golden); index < FTM_ASSOC_WIRE_SIZE; ++index) assert(!wire[index]);
    assert(wire[FTM_ASSOC_WIRE_SIZE] == 0xa5);
    assert(ftm_association_decode(wire, FTM_ASSOC_WIRE_SIZE, &decoded));
    assert(decoded.host_boot == original.host_boot && decoded.radio_boot == original.radio_boot);
    assert(decoded.count == 2 && decoded.entries[1].port_number == 18 && decoded.entries[1].association == 8);
    ftm_association_packet_t before = decoded;
    for (unsigned size = 0; size < FTM_ASSOC_WIRE_SIZE; ++size) {
        assert(!ftm_association_decode(wire, size, &decoded));
        assert(!memcmp(&before, &decoded, sizeof(decoded)));
    }
    assert(!ftm_association_decode(wire, sizeof(wire), &decoded));
    wire[0] ^= 1;assert(!ftm_association_decode(wire, FTM_ASSOC_WIRE_SIZE, &decoded));wire[0] ^= 1;
    wire[4] = 1;assert(!ftm_association_decode(wire, FTM_ASSOC_WIRE_SIZE, &decoded));wire[4] = 2;
    wire[100] = 1;assert(!ftm_association_decode(wire, FTM_ASSOC_WIRE_SIZE, &decoded));wire[100] = 0;
    wire[54] = 2;assert(!ftm_association_decode(wire, FTM_ASSOC_WIRE_SIZE, &decoded));wire[54] = 18;
    wire[53] = 5;assert(!ftm_association_decode(wire, FTM_ASSOC_WIRE_SIZE, &decoded));wire[53] = 6;
    wire[32] = 3;assert(!ftm_association_decode(wire, FTM_ASSOC_WIRE_SIZE, &decoded));wire[32] = 2;
    wire[20] = 17;assert(!ftm_association_decode(wire, FTM_ASSOC_WIRE_SIZE, &decoded));wire[20] = 2;
    assert(!memcmp(&before, &decoded, sizeof(decoded)));
    original.count = 17;
    uint8_t saved[sizeof(wire)];memcpy(saved, wire, sizeof(wire));
    assert(!ftm_association_encode(&original, wire, sizeof(wire)) && !memcmp(saved, wire, sizeof(wire)));
    original = packet();
    ftm_association_state_t state = {0};
    uint8_t source[10], untouched[10];memset(source, 0xa5, sizeof(source));memcpy(untouched, source, 10);
    assert(!ftm_association_select(&state, original.entries[0].mac, 100, 101, source));
    assert(!ftm_association_apply(&state, &original, 123, original.radio_boot, 100));
    assert(!state.valid);
    assert(ftm_association_apply(&state, &original, original.host_boot, original.radio_boot, 100));
    assert(!ftm_association_select(&state, original.entries[0].mac, 101, 100, source));
    assert(!memcmp(source, untouched, 10));
    assert(ftm_association_select(&state, original.entries[0].mac, 102, 101, source));
    assert(source[8] == 0 && source[9] == 2 && !memcmp(source, original.clock_identity, 8));
    assert(ftm_association_select(&state, original.entries[1].mac, 102, 101, source));assert(source[9] == 18);
    uint8_t unknown[6] = {2,8};
    assert(!ftm_association_select(&state, unknown, 102, 101, source));
    assert(!ftm_association_select(&state, original.entries[0].mac, 102, 103, source));
    assert(!ftm_association_select(&state, original.entries[0].mac, 99, 98, source));
    assert(!ftm_association_select(&state, original.entries[0].mac, 1000100, 101, source));
    ftm_association_state_t previous = state;
    assert(!ftm_association_apply(&state, &original, original.host_boot, original.radio_boot, 200));
    assert(!memcmp(&previous, &state, sizeof(state)));
    original.publication = 2;
    assert(!ftm_association_apply(&state, &original, original.host_boot, original.radio_boot, 99));
    assert(ftm_association_apply(&state, &original, original.host_boot, original.radio_boot, 200));
    assert(state.entries[0].activated_us == 100);
    ftm_association_retire(&state, original.entries[0].mac);
    assert(!ftm_association_select(&state, original.entries[0].mac, 202, 201, source));
    assert(ftm_association_select(&state, original.entries[1].mac, 202, 201, source));
    original.publication++;
    assert(ftm_association_apply(&state, &original, original.host_boot, original.radio_boot, 300));
    assert(state.entries[0].retired); /* A refresh cannot resurrect a retired lifetime. */
    ftm_association_state_t expired = state;
    ftm_association_packet_t refresh = original;refresh.publication++;
    assert(ftm_association_apply(&expired, &refresh, refresh.host_boot, refresh.radio_boot, 1000300));
    assert(expired.entries[0].retired);
    ftm_association_retire_all(&expired);refresh.publication++;
    assert(ftm_association_apply(&expired, &refresh, refresh.host_boot, refresh.radio_boot, 1000400));
    assert(expired.entries[0].retired && expired.entries[1].retired);
    assert(!ftm_association_apply(&state, &original, original.host_boot, original.radio_boot + 1, 400));
    original.entries[0].association++;
    original.publication++;
    assert(ftm_association_apply(&state, &original, original.host_boot, original.radio_boot, 400));
    assert(!state.entries[0].retired && state.entries[0].activated_us == 400);
    assert(!ftm_association_select(&state, original.entries[0].mac, 402, 399, source));
    assert(ftm_association_select(&state, original.entries[0].mac, 402, 401, source));
    original.publication++;
    assert(ftm_association_apply(&state, &original, original.host_boot, original.radio_boot, 1000400));
    assert(state.entries[0].activated_us == 1000400); /* Expiry recovery needs a new clock snapshot. */
    original.entries[0].port_number = 20;original.publication++;
    assert(ftm_association_apply(&state, &original, original.host_boot, original.radio_boot, 1000500));
    assert(state.entries[0].activated_us == 1000500);
    original.clock_identity[0] = 0x82;original.publication++;
    assert(ftm_association_apply(&state, &original, original.host_boot, original.radio_boot, 1000600));
    assert(state.entries[0].activated_us == 1000600 && state.entries[1].activated_us == 1000600);
    original.count = 0;original.publication++;
    assert(ftm_association_apply(&state, &original, original.host_boot, original.radio_boot, 1000700));
    assert(!ftm_association_select(&state, original.entries[0].mac, 1000702, 1000701, source));
    original = packet();original.publication = UINT32_MAX;original.host_boot++;
    assert(ftm_association_apply(&state, &original, original.host_boot, original.radio_boot, 1000800));
    original.publication = 1;
    assert(ftm_association_apply(&state, &original, original.host_boot, original.radio_boot, 1000900));
    original.publication = UINT32_MAX;
    assert(!ftm_association_apply(&state, &original, original.host_boot, original.radio_boot, 1001000));
    original = packet();original.count = FTM_ASSOC_MAX;
    for (unsigned index = 0; index < FTM_ASSOC_MAX; ++index)
        original.entries[index] = (ftm_association_entry_t){.mac={2,0,0,0,0,index}, .port_number=index+1, .association=index+1};
    assert(ftm_association_encode(&original, wire, sizeof(wire)));
    assert(ftm_association_decode(wire, FTM_ASSOC_WIRE_SIZE, &decoded) && decoded.count == FTM_ASSOC_MAX);
    puts("Association metadata: golden encoding, truncation, duplicate identities, atomic rejection, boot ownership, replay/wrap, expiry, retirement, reconnect and snapshot barriers passed");
}
