#include <assert.h>
#include <stdint.h>
#include "scope_math.h"
int main(void)
{
    uint64_t target = 0;
    assert(scope_target_ticks(20000000, 20000000, 800000, 4000000000ULL, &target));
    assert(target == 4000800000ULL);
    assert(scope_target_ticks(20000000, 20010000, 800000, 4000000000ULL, &target));
    assert(target == 4000799600ULL);
    assert(!scope_target_ticks(4999999, 20000000, 800000, 0, &target));
    assert(!scope_target_ticks(40000001, 20000000, 800000, 0, &target));
    assert(!scope_rate_valid(-20000000, 800000));
    assert(!scope_rate_valid(1020000000, 800000));
    assert(!scope_rate_valid(20000000, 0));
    assert(!scope_rate_valid(20000000, 8000001));
    assert(!scope_rate_valid(20020001, 800000));
    assert(!scope_rate_valid(19979999, 800000));
    assert(scope_rate_valid(20020000, 800000));
    assert(scope_rate_valid(19980000, 800000));
    for (int32_t rate = -512000; rate <= 512000; rate += 1000) {
        assert(scope_target_affine(80000000, rate, 4000000000ULL, &target));
        int64_t elapsed = (int64_t)(target - 4000000000ULL) * 25;
        int64_t projected = elapsed + elapsed * rate / 1000000000;
        assert(projected >= 79999987 && projected <= 80000013);
    }
    assert(!scope_target_affine(80000001, 0, 0, &target));
    assert(!scope_target_affine(4999999, 0, 0, &target));
    assert(!scope_target_affine(10000000, 512001, 0, &target));
    assert(!scope_target_affine(10000000, 0, UINT64_MAX, &target));
    return 0;
}
