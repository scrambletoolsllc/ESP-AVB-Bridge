#include "ftm_discipline.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

bool ftm_discipline_observe(ftm_discipline_t *state, uint32_t generation,
    uint16_t time_base, int64_t local_ns, int64_t reference_ns, int64_t *innovation_ns)
{
    *innovation_ns = INT64_MIN;
    if (!generation || local_ns < 0 || reference_ns < 0 ||
        local_ns > INT64_MAX - INT64_C(100000000000) ||
        reference_ns > INT64_MAX - INT64_C(100000000000)) return false;
    bool reset = state->generation != generation || state->time_base != time_base;
    if (state->count && (local_ns <= state->local[state->count - 1] ||
        local_ns - state->local[state->count - 1] > INT64_C(10000000000))) reset = true;
    if (reset) memset(state, 0, sizeof(*state));
    state->generation = generation;
    state->time_base = time_base;
    if (state->valid) {
        int64_t elapsed = local_ns - state->local_anchor;
        int64_t predicted = state->reference_anchor + elapsed +
            elapsed * state->rate_ppb / INT64_C(1000000000);
        *innovation_ns = reference_ns - predicted;
        if (llabs(*innovation_ns) > 5000) {
            if (++state->rejected >= 3) memset(state, 0, sizeof(*state));
            return false;
        }
    }
    state->rejected = 0;
    if (state->count == FTM_DISCIPLINE_WINDOW) {
        memmove(state->local, state->local + 1, sizeof(state->local) - sizeof(state->local[0]));
        memmove(state->reference, state->reference + 1, sizeof(state->reference) - sizeof(state->reference[0]));
        --state->count;
    }
    state->local[state->count] = local_ns;
    state->reference[state->count++] = reference_ns;
    if (state->count < 8) return false;
    double mean_local = 0, mean_correction = 0;
    for (unsigned index = 0; index < state->count; ++index) {
        int64_t elapsed = state->local[index] - state->local[0];
        mean_local += elapsed;
        mean_correction += state->reference[index] - state->reference[0] - elapsed;
    }
    mean_local /= state->count;
    mean_correction /= state->count;
    double covariance = 0, variance = 0;
    for (unsigned index = 0; index < state->count; ++index) {
        int64_t elapsed = state->local[index] - state->local[0];
        double centered = elapsed - mean_local;
        covariance += centered * (state->reference[index] - state->reference[0] - elapsed - mean_correction);
        variance += centered * centered;
    }
    double slope = covariance / variance;
    if (!isfinite(slope) || fabs(slope) > .0002) {
        memset(state, 0, sizeof(*state));
        return false;
    }
    state->local_anchor = local_ns;
    state->reference_anchor = state->reference[0] + (local_ns - state->local[0]) +
        (int64_t)llround(mean_correction + slope * (local_ns - state->local[0] - mean_local));
    state->rate_ppb = (int32_t)llround(slope * 1e9);
    state->valid = true;
    return true;
}
