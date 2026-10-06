#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ftm_follow_up_tx.h"

static int64_t correction(const uint8_t *bytes)
{
    uint64_t value = 0;
    for (unsigned index = 14; index < 22; ++index) value = (value << 8) | bytes[index];
    return value <= INT64_MAX ? (int64_t)value : -1 - (int64_t)(UINT64_MAX - value);
}

int main(void)
{
    ftm_follow_up_tx_t snapshot = {
        .anchor_ps = UINT64_C(4294967296000000),
        .not_before_ps = UINT64_C(4292967296000000),
        .expires_us = 5000000, .correction_scaled = -16384,
        .rate_q32 = INT64_C(4295067296), .generation = 2, .valid = true,
    };
    snapshot.ie[2] = 0x00;
    snapshot.ie[3] = 0x80;
    snapshot.ie[4] = 0xc2;
    uint8_t output[82];
    for (int64_t rate = INT64_C(4286377361); rate < INT64_C(4303557231); rate += 128849) {
        snapshot.rate_q32 = rate;
        for (int64_t delta = -INT64_C(1500000000000); delta <= INT64_C(1500000000000); delta += 12345678901) {
            assert(ftm_follow_up_emit(&snapshot, snapshot.anchor_ps + delta, 1000000, 255, 0xabcd, output, 82));
            int64_t expected = snapshot.correction_scaled +
                (__int128)delta * rate / INT64_C(65536000);
            assert(llabs(correction(output) - expected) <= 134);
            assert(output[2] == 0x00 && output[3] == 0x80 && output[4] == 0xc2 && output[36] == 0xab && output[37] == 0xcd);
        }
    }
    assert(!ftm_follow_up_emit(&snapshot, snapshot.not_before_ps - 1, 1, 1, 1, output, 82));
    assert(!ftm_follow_up_emit(&snapshot, snapshot.anchor_ps, 5000001, 1, 1, output, 82));
    assert(!ftm_follow_up_emit(&snapshot, snapshot.anchor_ps, 1, 0, 1, output, 82));
    for (unsigned index = 2; index < 82; ++index) assert(output[index] == 0);
    snapshot.rate_q32 = INT64_C(4294967296);
    snapshot.correction_scaled = INT64_MAX;
    assert(!ftm_follow_up_emit(&snapshot, snapshot.anchor_ps + 1000, 1, 1, 1, output, 82));
    snapshot.correction_scaled = INT64_MIN;
    assert(!ftm_follow_up_emit(&snapshot, snapshot.anchor_ps - 1000, 1, 1, 1, output, 82));
    assert(!ftm_follow_up_emit(NULL, snapshot.anchor_ps, 1, 1, 1, output, 82));
    puts("FTM callback integer conversion, wrap, expiry and invalidation tests pass");
}
