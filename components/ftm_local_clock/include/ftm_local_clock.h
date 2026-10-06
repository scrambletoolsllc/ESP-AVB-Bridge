#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint32_t generation;
    uint32_t mac_us;
    int64_t local_ns;
    int64_t refreshed_ns;
    uint32_t uncertainty_ns;
    bool valid;
} ftm_local_clock_snapshot_t;

bool ftm_local_clock_snapshot(ftm_local_clock_snapshot_t *snapshot);

/* Convert a full local FTM timestamp (ps), never a remote 48-bit value.
 * Require the caller's acquisition generation; reject stale/remote epochs. */
static inline bool ftm_local_clock_convert(const ftm_local_clock_snapshot_t *map,
                                          uint32_t generation, uint64_t ftm_ps,
                                          int64_t now_ns, int64_t *local_ns)
{
    if (!map->valid || map->generation != generation || now_ns < map->refreshed_ns ||
        now_ns - map->refreshed_ns > INT64_C(1000000000)) return false;
    uint32_t mac_us = (uint32_t)(ftm_ps / 1000000);
    uint32_t unsigned_delta = mac_us - map->mac_us;
    if (unsigned_delta == UINT32_C(0x80000000)) return false;
    int64_t delta_us = unsigned_delta <= INT32_MAX ? unsigned_delta :
        (int64_t)unsigned_delta - INT64_C(4294967296);
    if (delta_us < -1000000 || delta_us > 1000000) return false;
    *local_ns = map->local_ns + delta_us * 1000 + (ftm_ps % 1000000) / 1000;
    return true;
}
