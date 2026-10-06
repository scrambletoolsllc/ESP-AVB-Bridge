#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint32_t host_boot;
    uint32_t sequence;
    uint64_t baseline;
    bool armed;
    bool captured;
    bool fault;
} edge_capture_state_t;

static inline bool edge_capture_arm(edge_capture_state_t *state, uint32_t host_boot,
                                     uint32_t sequence, uint64_t baseline)
{
    if (!host_boot || !sequence) return false;
    if (host_boot == state->host_boot) {
        uint32_t difference = sequence - state->sequence;
        if (!difference) return !state->fault;
        if (difference >= UINT32_C(0x80000000)) return false;
    }
    *state = (edge_capture_state_t){.host_boot = host_boot, .sequence = sequence,
        .baseline = baseline, .armed = true};
    return true;
}

static inline bool edge_capture_record(edge_capture_state_t *state, uint64_t ticks)
{
    if (ticks <= state->baseline) return false;
    if (!state->armed) { state->fault = true; state->captured = false; return false; }
    state->armed = false;
    state->captured = true;
    return true;
}
