#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <math.h>

/* Timestamp differences share the first matched quartet's origin. */
typedef struct {
    int forward, reverse;
    double forward_ps, reverse_ps;
} ftm_pair_selection_t;

static inline void ftm_pair_selection_init(ftm_pair_selection_t *selection)
{
    *selection = (ftm_pair_selection_t){.forward = -1, .reverse = -1};
}

static inline bool ftm_pair_selection_add(ftm_pair_selection_t *selection,
    unsigned index, uint64_t t1, uint64_t t2, uint64_t t3, uint64_t t4,
    uint64_t remote_origin, uint64_t local_origin, double remote_per_local)
{
    const uint64_t mask = (UINT64_C(1) << 48) - 1;
    uint64_t remote_tx = (t1 - remote_origin) & mask;
    uint64_t remote_rx = (t4 - remote_origin) & mask;
    if (t2 < local_origin || t3 < t2 || remote_rx < remote_tx ||
        remote_rx > UINT64_C(2000000000000) ||
        t3 - local_origin > UINT64_C(2000000000000) ||
        !isfinite(remote_per_local) || remote_per_local < .999 ||
        remote_per_local > 1.001) return false;
    double forward = (t2 - local_origin) * remote_per_local - remote_tx;
    double reverse = remote_rx - (t3 - local_origin) * remote_per_local;
    if (selection->forward < 0 || forward <= selection->forward_ps) {
        selection->forward = index;
        selection->forward_ps = forward;
    }
    if (selection->reverse < 0 || reverse <= selection->reverse_ps) {
        selection->reverse = index;
        selection->reverse_ps = reverse;
    }
    return true;
}
