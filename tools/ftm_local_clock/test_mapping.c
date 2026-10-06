#include <assert.h>
#include <stdio.h>
#include "ftm_local_clock.h"

int main(void)
{
    ftm_local_clock_snapshot_t mapping = {.generation = 3, .mac_us = UINT32_MAX - 2,
        .local_ns = 5000000000, .refreshed_ns = 5000000100, .valid = true};
    int64_t converted;
    assert(ftm_local_clock_convert(&mapping, 3, 2000123, 5000000200, &converted));
    assert(converted == 5000005000);
    assert(ftm_local_clock_convert(&mapping, 3,
        (UINT64_C(4294967296) + 2) * 1000000 + 125000,
        5000000200, &converted));
    assert(converted == 5000005125);
    assert(!ftm_local_clock_convert(&mapping, 2, 2000123, 5000000200, &converted));
    assert(!ftm_local_clock_convert(&mapping, 3, 2000123, 6000000101, &converted));
    assert(!ftm_local_clock_convert(&mapping, 3, 2000123, 5000000000, &converted));
    assert(!ftm_local_clock_convert(&mapping, 3, 2000000000000, 5000000200, &converted));
    mapping.mac_us = 10;
    assert(ftm_local_clock_convert(&mapping, 3, 8125000, 5000000200, &converted));
    assert(converted == 4999998125);
    mapping.valid = false;
    assert(!ftm_local_clock_convert(&mapping, 3, 8125000, 5000000200, &converted));
    puts("mapping wrap, freshness, generation and fractional conversion pass");
}
