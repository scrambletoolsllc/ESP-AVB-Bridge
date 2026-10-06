#pragma once
#include <stdbool.h>
#include <stdint.h>

#define FTM_DISCIPLINE_WINDOW 32
typedef struct {
    int64_t local[FTM_DISCIPLINE_WINDOW], reference[FTM_DISCIPLINE_WINDOW];
    unsigned count, rejected;
    uint32_t generation;
    uint16_t time_base;
    int64_t local_anchor, reference_anchor;
    int32_t rate_ppb;
    bool valid;
} ftm_discipline_t;

/* One task owns the state. Predictions are evaluated before adding input. */
bool ftm_discipline_observe(ftm_discipline_t *state, uint32_t generation,
    uint16_t time_base, int64_t local_ns, int64_t reference_ns, int64_t *innovation_ns);
