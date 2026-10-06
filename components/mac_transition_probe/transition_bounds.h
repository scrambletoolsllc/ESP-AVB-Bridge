#pragma once
#include <stdint.h>

typedef struct {
    int64_t lower;
    int64_t upper;
} transition_bounds_t;

static inline transition_bounds_t transition_bounds(uint32_t mac_after,
                                                      uint64_t timer_before,
                                                      uint64_t timer_after)
{
    /* The final counter read can truncate almost one timer tick. */
    return (transition_bounds_t){
        .lower = (int64_t)mac_after * 40 - (int64_t)timer_after - 1,
        .upper = (int64_t)mac_after * 40 - (int64_t)timer_before,
    };
}
