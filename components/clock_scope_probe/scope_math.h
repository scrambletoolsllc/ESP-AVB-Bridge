#pragma once
#include <stdbool.h>
#include <stdint.h>

/* 40 MHz raw timer, 25 ns per tick. Reject steps and extreme rates. */
static inline bool scope_rate_valid(int64_t elapsed_ns, int64_t elapsed_ticks)
{
    if (elapsed_ticks < 400000 || elapsed_ticks > 8000000)
        return false;
    int64_t nominal_ns = elapsed_ticks * 25;
    int64_t difference = elapsed_ns - nominal_ns;
    return difference >= -nominal_ns / 1000 && difference <= nominal_ns / 1000;
}

static inline bool scope_target_ticks(int64_t remaining_ns, int64_t elapsed_ns,
                                      int64_t elapsed_ticks, uint64_t anchor,
                                      uint64_t *target)
{
    if (remaining_ns < 5000000 || remaining_ns > 40000000 ||
        !scope_rate_valid(elapsed_ns, elapsed_ticks))
        return false;
    *target = anchor + (remaining_ns * elapsed_ticks + elapsed_ns / 2) / elapsed_ns;
    return true;
}

/* C6 GPTimer and SYSTIMER share the oscillator; use the applied affine rate. */
static inline bool scope_target_affine(int64_t remaining_ns, int32_t rate_ppb,
                                      uint64_t anchor, uint64_t *target)
{
    if (remaining_ns < 5000000 || remaining_ns > 80000000 ||
        rate_ppb < -512000 || rate_ppb > 512000) return false;
    int64_t denominator = INT64_C(1000000000) + rate_ppb;
    uint64_t ticks = (uint64_t)((remaining_ns * INT64_C(40000000) + denominator / 2) / denominator);
    if (UINT64_MAX - anchor < ticks) return false;
    *target = anchor + ticks;
    return true;
}
