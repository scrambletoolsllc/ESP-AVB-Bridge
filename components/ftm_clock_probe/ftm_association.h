#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#define FTM_ASSOC_IRAM IRAM_ATTR
#else
#define FTM_ASSOC_IRAM
#endif

#define FTM_ASSOC_MAX 16
#define FTM_ASSOC_POLICY_OFFSET (32 + 16 * FTM_ASSOC_MAX)
#define FTM_ASSOC_WIRE_SIZE (FTM_ASSOC_POLICY_OFFSET + 4)
#define FTM_ASSOC_TAG UINT32_C(0x314d4146)
#define FTM_ASSOC_VERSION 2U
#define FTM_ASSOC_MAX_AGE_US INT64_C(1000000)

typedef struct {
    uint8_t mac[6];
    uint16_t port_number;
    uint32_t association;
    bool sync_stopped;
    uint32_t sync_revision;
} ftm_association_entry_t;

typedef struct {
    uint32_t host_boot, radio_boot, publication, count;
    uint8_t clock_identity[8];
    ftm_association_entry_t entries[FTM_ASSOC_MAX];
} ftm_association_packet_t;

typedef struct {
    ftm_association_entry_t peer;
    int64_t activated_us;
    bool retired;
} ftm_association_state_entry_t;

typedef struct {
    uint32_t host_boot, radio_boot, publication, count;
    uint8_t clock_identity[8];
    int64_t updated_us;
    bool valid;
    ftm_association_state_entry_t entries[FTM_ASSOC_MAX];
} ftm_association_state_t;

static inline uint32_t ftm_association_read32(const uint8_t *bytes)
{
    return (uint32_t)bytes[0] | (uint32_t)bytes[1] << 8 |
           (uint32_t)bytes[2] << 16 | (uint32_t)bytes[3] << 24;
}

static inline void ftm_association_write32(uint8_t *bytes, uint32_t value)
{
    for (unsigned offset = 0; offset < 4; ++offset) bytes[offset] = value >> (8 * offset);
}

static inline bool ftm_association_packet_valid(const ftm_association_packet_t *packet)
{
    if (!packet || !packet->host_boot || !packet->radio_boot || !packet->publication ||
        packet->count > FTM_ASSOC_MAX) return false;
    const uint8_t zero_mac[6] = {0}, zero_identity[8] = {0};
    if (!memcmp(packet->clock_identity, zero_identity, 8)) return false;
    for (unsigned index = 0; index < packet->count; ++index) {
        const ftm_association_entry_t *entry = &packet->entries[index];
        if (!entry->association || !entry->port_number || (entry->mac[0] & 1) ||
            !memcmp(entry->mac, zero_mac, 6)) return false;
        for (unsigned previous = 0; previous < index; ++previous)
            if (packet->entries[previous].port_number == entry->port_number ||
                !memcmp(packet->entries[previous].mac, entry->mac, 6)) return false;
    }
    return true;
}

/* Task-only, explicit little-endian encoding, independent of struct padding. */
static inline bool ftm_association_encode(const ftm_association_packet_t *packet,
                                          uint8_t *wire, size_t capacity)
{
    if (!wire || capacity < FTM_ASSOC_WIRE_SIZE || !ftm_association_packet_valid(packet))
        return false;
    memset(wire, 0, FTM_ASSOC_WIRE_SIZE);
    ftm_association_write32(wire, FTM_ASSOC_TAG);
    ftm_association_write32(wire + 4, FTM_ASSOC_VERSION);
    ftm_association_write32(wire + 8, packet->host_boot);
    ftm_association_write32(wire + 12, packet->radio_boot);
    ftm_association_write32(wire + 16, packet->publication);
    ftm_association_write32(wire + 20, packet->count);
    memcpy(wire + 24, packet->clock_identity, 8);
    for (unsigned index = 0; index < packet->count; ++index) {
        uint8_t *entry = wire + 32 + 16 * index;
        memcpy(entry, packet->entries[index].mac, 6);
        entry[6] = packet->entries[index].port_number;
        entry[7] = packet->entries[index].port_number >> 8;
        ftm_association_write32(entry + 8, packet->entries[index].association);
        ftm_association_write32(entry + 12, packet->entries[index].sync_revision);
        if (packet->entries[index].sync_stopped)
            wire[FTM_ASSOC_POLICY_OFFSET + index / 8] |= 1U << (index % 8);
    }
    return true;
}

static inline bool ftm_association_decode(const uint8_t *wire, size_t size,
                                          ftm_association_packet_t *packet)
{
    if (!wire || !packet || size != FTM_ASSOC_WIRE_SIZE ||
        ftm_association_read32(wire) != FTM_ASSOC_TAG ||
        ftm_association_read32(wire + 4) != FTM_ASSOC_VERSION) return false;
    ftm_association_packet_t decoded = {0};
    decoded.host_boot = ftm_association_read32(wire + 8);
    decoded.radio_boot = ftm_association_read32(wire + 12);
    decoded.publication = ftm_association_read32(wire + 16);
    decoded.count = ftm_association_read32(wire + 20);
    if (decoded.count > FTM_ASSOC_MAX) return false;
    uint32_t stopped = ftm_association_read32(wire + FTM_ASSOC_POLICY_OFFSET);
    if (stopped >> decoded.count) return false;
    memcpy(decoded.clock_identity, wire + 24, 8);
    for (unsigned index = 0; index < decoded.count; ++index) {
        const uint8_t *entry = wire + 32 + 16 * index;
        memcpy(decoded.entries[index].mac, entry, 6);
        decoded.entries[index].port_number = (uint16_t)entry[6] | (uint16_t)entry[7] << 8;
        decoded.entries[index].association = ftm_association_read32(entry + 8);
        decoded.entries[index].sync_revision = ftm_association_read32(entry + 12);
        decoded.entries[index].sync_stopped = (stopped & (1U << index)) != 0;
    }
    for (unsigned offset = 32 + 16 * decoded.count; offset < FTM_ASSOC_POLICY_OFFSET; ++offset)
        if (wire[offset]) return false;
    if (!ftm_association_packet_valid(&decoded)) return false;
    *packet = decoded;
    return true;
}

/* Caller serializes updates with callback reads. Boot ownership comes from the arm handshake. */
static inline bool ftm_association_apply(ftm_association_state_t *state,
    const ftm_association_packet_t *packet, uint32_t host_boot, uint32_t radio_boot,
    int64_t now_us)
{
    if (!state || now_us < 0 || !ftm_association_packet_valid(packet) ||
        packet->host_boot != host_boot || packet->radio_boot != radio_boot) return false;
    bool same_owner = state->valid && state->host_boot == host_boot && state->radio_boot == radio_boot;
    if (same_owner && ((int32_t)(packet->publication - state->publication) <= 0 ||
                       now_us < state->updated_us)) return false;
    ftm_association_state_t next = {.host_boot = host_boot, .radio_boot = radio_boot,
        .publication = packet->publication, .count = packet->count,
        .updated_us = now_us, .valid = true};
    memcpy(next.clock_identity, packet->clock_identity, 8);
    bool continuity = same_owner && now_us - state->updated_us < FTM_ASSOC_MAX_AGE_US &&
        !memcmp(state->clock_identity, packet->clock_identity, 8);
    for (unsigned index = 0; index < packet->count; ++index) {
        next.entries[index].peer = packet->entries[index];
        next.entries[index].activated_us = now_us;
        for (unsigned previous = 0; same_owner && previous < state->count; ++previous) {
            const ftm_association_state_entry_t *old = &state->entries[previous];
            if (!memcmp(old->peer.mac, packet->entries[index].mac, 6) &&
                old->peer.association == packet->entries[index].association) {
                next.entries[index].retired = old->retired;
                if (continuity && old->peer.port_number == packet->entries[index].port_number &&
                    old->peer.sync_stopped == packet->entries[index].sync_stopped &&
                    old->peer.sync_revision == packet->entries[index].sync_revision)
                    next.entries[index].activated_us = old->activated_us;
                break;
            }
        }
    }
    *state = next;
    return true;
}

/* A local disconnect/rejoin event retires the old lifetime before a host refresh. */
static inline void ftm_association_retire(ftm_association_state_t *state, const uint8_t mac[6])
{
    if (!state || !mac) return;
    for (unsigned index = 0; index < state->count && index < FTM_ASSOC_MAX; ++index)
        if (!memcmp(state->entries[index].peer.mac, mac, 6)) state->entries[index].retired = true;
}

static inline void ftm_association_retire_all(ftm_association_state_t *state)
{
    if (!state) return;
    for (unsigned index = 0; index < state->count && index < FTM_ASSOC_MAX; ++index)
        state->entries[index].retired = true;
}

/* All state and output memory must be DRAM resident when called from the radio callback. */
static inline FTM_ASSOC_IRAM bool ftm_association_select(const ftm_association_state_t *state,
    const uint8_t mac[6], int64_t now_us, int64_t snapshot_prepared_us, uint8_t source_port[10])
{
    if (!state || !mac || !source_port || !state->valid || state->count > FTM_ASSOC_MAX ||
        now_us < state->updated_us || now_us - state->updated_us >= FTM_ASSOC_MAX_AGE_US ||
        snapshot_prepared_us > now_us) return false;
    for (unsigned index = 0; index < state->count; ++index) {
        const ftm_association_state_entry_t *entry = &state->entries[index];
        bool matches = true;
        for (unsigned octet = 0; octet < 6; ++octet)
            if (entry->peer.mac[octet] != mac[octet]) matches = false;
        if (!matches) continue;
        if (entry->retired || entry->peer.sync_stopped ||
            snapshot_prepared_us <= entry->activated_us) return false;
        for (unsigned octet = 0; octet < 8; ++octet) source_port[octet] = state->clock_identity[octet];
        source_port[8] = entry->peer.port_number >> 8;
        source_port[9] = entry->peer.port_number;
        return true;
    }
    return false;
}
