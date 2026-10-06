#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "ftm_discipline.h"
#include "ptp_clock_affine.h"

int main(void)
{
    ftm_discipline_t state = {0};
    const int64_t epoch = INT64_C(90000000000000);
    int64_t innovation;
    unsigned seed = 19;
    ptp_clock_affine_t clock = {.ptp_ns = INT64_C(1700000000000000000)};
    bool initialized = false;
    for (unsigned index = 1; index <= 500; ++index) {
        int64_t local = (int64_t)index * 400000000;
        seed = seed * 1664525U + 1013904223U;
        int64_t noise = (int64_t)(seed % 1601) - 800;
        int64_t reference = epoch + local + local * 23000 / 1000000000 + noise;
        bool valid = ftm_discipline_observe(&state, 1, 2, local, reference, &innovation);
        assert(valid == (index >= 8));
        if (index >= 32) {
            assert(llabs(state.rate_ppb - 23000) < 100);
            assert(llabs(state.reference_anchor - (reference - noise)) < 600);
        }
        if (valid) {
            int64_t now = local + 100000000, error;
            int64_t before = ptp_clock_affine_now(&clock, now);
            ptp_clock_affine_discipline(&clock, now, state.local_anchor,
                state.reference_anchor, state.rate_ppb, !initialized, &error);
            if (initialized) assert(ptp_clock_affine_now(&clock, now) == before);
            initialized = true;
            if (index > 40) {
                int64_t truth = epoch + now + now * 23000 / 1000000000;
                assert(llabs(ptp_clock_affine_now(&clock, now) - truth) < 1000);
            }
        }
    }
    int64_t local = state.local_anchor + 400000000;
    int64_t prediction = state.reference_anchor + 400000000 + 400000000LL * state.rate_ppb / 1000000000;
    assert(!ftm_discipline_observe(&state, 1, 2, local, prediction + 100000, &innovation));
    assert(state.valid && state.rejected == 1);
    assert(ftm_discipline_observe(&state, 1, 2, local, prediction, &innovation));
    assert(!state.rejected);
    assert(!ftm_discipline_observe(&state, 2, 2, local + 400000000, prediction + 400000000, &innovation));
    assert(state.count == 1 && !state.valid);
    assert(!ftm_discipline_observe(&state, 2, 2, local + INT64_C(11000000000), prediction + INT64_C(11000000000), &innovation));
    assert(state.count == 1);
    puts("FTM discipline acquisition, noisy drift fit, outlier and reset tests pass");
}
