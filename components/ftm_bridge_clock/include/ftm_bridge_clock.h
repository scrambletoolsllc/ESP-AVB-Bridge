#pragma once
#include <stdbool.h>
#include <stdint.h>

#define FTM_BRIDGE_HISTORY 4

typedef struct {
    uint32_t host_boot, radio_boot, source_generation, sequence;
    uint64_t host_edge, radio_edge;
    uint64_t host_before, host_after, radio_before, radio_after;
    int64_t ptp_ns, received_us;
    uint32_t mac_us;
    int32_t trim_ppb;
    /* Applied PTP rate relative to the nominal host oscillator, not the
     * controller's requested trim, which can accumulate rounding error. */
    int64_t host_rate_q32;
    bool source_valid;
} ftm_bridge_observation_t;

typedef struct {
    uint32_t host_boot, radio_boot, source_generation, sequence;
    /* Read brackets only, excludes fixed skew, holdover and upstream error. */
    uint32_t mac_us, read_uncertainty_ns;
    int64_t reference_ns, refreshed_us, rate_q32;
    bool valid;
} ftm_bridge_snapshot_t;

typedef struct {
    ftm_bridge_observation_t history[FTM_BRIDGE_HISTORY];
    unsigned count;
    ftm_bridge_snapshot_t snapshot;
} ftm_bridge_clock_t;

typedef enum {
    FTM_BRIDGE_OK, FTM_BRIDGE_ACQUIRING, FTM_BRIDGE_INVALID,
    FTM_BRIDGE_IDENTITY, FTM_BRIDGE_ORDER, FTM_BRIDGE_BRACKET,
    FTM_BRIDGE_RATE, FTM_BRIDGE_INNOVATION, FTM_BRIDGE_MAC
} ftm_bridge_result_t;

/* Task-owned state. Input counters are paired 40 MHz hardware captures.
 * P4 PTP and GPTimer must share their nominal oscillator reference. */
void ftm_bridge_clock_reset(ftm_bridge_clock_t *clock);
ftm_bridge_result_t ftm_bridge_clock_observe(ftm_bridge_clock_t *clock,
    const ftm_bridge_observation_t *observation);
bool ftm_bridge_clock_snapshot(const ftm_bridge_clock_t *clock, int64_t now_us,
    ftm_bridge_snapshot_t *snapshot);

/* Full local radio timestamp, not a received remote 48-bit timestamp.
 * This task-context conversion is a reference for the eventual IRAM path. */
bool ftm_bridge_clock_convert(const ftm_bridge_snapshot_t *snapshot,
    uint64_t local_ps, int64_t now_us, int64_t *reference_ns);
