#pragma once
#include "ftm_association.h"

/* Generation covers the entire AP registry; any event retires pending maps. */
typedef struct {
    uint32_t generation;
    unsigned count;
    bool forwarded;
    uint8_t macs[FTM_ASSOC_MAX][6];
} ftm_radio_association_t;

static inline uint32_t ftm_radio_association_change(ftm_radio_association_t *state,
                                                    const uint8_t mac[6], bool joined)
{
    if (!state) return 0;
    if (!++state->generation) ++state->generation;
    state->forwarded = false;
    if (!mac) {
        state->count = 0;
        memset(state->macs, 0, sizeof(state->macs));
        return state->generation;
    }
    const uint8_t zero[6] = {0};
    if ((mac[0] & 1) || !memcmp(mac, zero, 6)) return 0;
    for (unsigned index = 0; index < state->count; ++index) {
        if (memcmp(state->macs[index], mac, 6)) continue;
        if (!joined) {
            --state->count;
            memcpy(state->macs[index], state->macs[state->count], 6);
            memset(state->macs[state->count], 0, 6);
        }
        return state->generation;
    }
    if (joined) {
        if (state->count == FTM_ASSOC_MAX) return 0;
        memcpy(state->macs[state->count++], mac, 6);
    }
    return state->generation;
}

/* A token is publishable only after its lifecycle notification was queued. */
static inline bool ftm_radio_association_forwarded(ftm_radio_association_t *state,
                                                   uint32_t generation, bool success)
{
    if (!state || !generation || generation != state->generation) return false;
    state->forwarded = success;
    return success;
}

/* Task-only map admission. Caller separately verifies boot, publication and age. */
static inline bool ftm_radio_association_accepts(const ftm_radio_association_t *state,
    uint32_t generation, const ftm_association_packet_t *packet)
{
    if (!state || !state->forwarded || !generation || generation != state->generation ||
        !ftm_association_packet_valid(packet) || packet->count != state->count) return false;
    for (unsigned index = 0; index < state->count; ++index) {
        bool found = false;
        for (unsigned peer = 0; peer < packet->count; ++peer)
            if (!memcmp(state->macs[index], packet->entries[peer].mac, 6)) {
                found = true;
                break;
            }
        if (!found) return false;
    }
    return true;
}

/* Wrap the existing map with a radio-owned generation. Explicit little-endian. */
#define FTM_ASSOC_ADMISSION_TAG UINT32_C(0x31474146)
#define FTM_ASSOC_ADMISSION_SIZE (8 + FTM_ASSOC_WIRE_SIZE)
static inline bool ftm_radio_association_encode(uint32_t generation,
    const ftm_association_packet_t *packet, uint8_t *wire, size_t capacity)
{
    if (!generation || !wire || capacity < FTM_ASSOC_ADMISSION_SIZE ||
        !ftm_association_packet_valid(packet)) return false;
    ftm_association_encode(packet, wire + 8, capacity - 8);
    ftm_association_write32(wire, FTM_ASSOC_ADMISSION_TAG);
    ftm_association_write32(wire + 4, generation);
    return true;
}

static inline bool ftm_radio_association_decode(const uint8_t *wire, size_t length,
    uint32_t *generation, ftm_association_packet_t *packet)
{
    if (!wire || !generation || !packet || length != FTM_ASSOC_ADMISSION_SIZE ||
        ftm_association_read32(wire) != FTM_ASSOC_ADMISSION_TAG ||
        !ftm_association_read32(wire + 4)) return false;
    if (!ftm_association_decode(wire + 8, length - 8, packet)) return false;
    *generation = ftm_association_read32(wire + 4);
    return true;
}
