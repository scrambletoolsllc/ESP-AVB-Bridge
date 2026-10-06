#include <assert.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include "ftm_bridge_clock.h"

static const int64_t reference_origin = INT64_C(1000000000000000);
static const uint64_t mac_origin = UINT64_C(4294967000);

static ftm_bridge_observation_t observation(unsigned sequence)
{
    uint64_t radio = UINT64_C(10000000) + (uint64_t)sequence * 40000000;
    uint64_t host = UINT64_C(20000000) + (uint64_t)sequence * 40000800;
    ftm_bridge_observation_t result = {
        .host_boot = 1, .radio_boot = 2, .source_generation = 3, .sequence = sequence,
        .host_edge = host, .radio_edge = radio,
        .host_before = host + 1000, .host_after = host + 1022,
        .radio_before = radio + 205, .radio_after = radio + 235,
        .received_us = (int64_t)sequence * 1000000,
        .mac_us = (uint32_t)(mac_origin + (uint64_t)sequence * 1000000 + 5),
        .trim_ppb = 30000, .source_valid = true,
        .host_rate_q32 = INT64_C(4295096145),
    };
    result.ptp_ns = reference_origin + (int64_t)llroundl(
        ((long double)sequence * 40000800 + 1011) * 25 * 1.00003L);
    return result;
}

static void acquire(ftm_bridge_clock_t *clock)
{
    ftm_bridge_clock_reset(clock);
    for (unsigned sequence = 1; sequence <= 8; ++sequence) {
        ftm_bridge_observation_t input = observation(sequence);
        assert(ftm_bridge_clock_observe(clock, &input) ==
               (sequence < 4 ? FTM_BRIDGE_ACQUIRING : FTM_BRIDGE_OK));
    }
}

int main(void)
{
    ftm_bridge_clock_t clock;
    ftm_bridge_observation_t input;
    acquire(&clock);
    input = observation(9);
    input.trim_ppb = 30500;
    assert(ftm_bridge_clock_observe(&clock, &input) == FTM_BRIDGE_OK);
    int64_t actual_rate = clock.snapshot.rate_q32;
    acquire(&clock);
    input = observation(9);
    assert(ftm_bridge_clock_observe(&clock, &input) == FTM_BRIDGE_OK);
    assert(clock.snapshot.rate_q32 == actual_rate);
    acquire(&clock);
    ftm_bridge_snapshot_t snapshot;
    assert(ftm_bridge_clock_snapshot(&clock, 8000000, &snapshot));
    assert(snapshot.read_uncertainty_ns >= 1150 && snapshot.read_uncertainty_ns <= 1152);
    for (int displacement = -1400000; displacement <= 1400000; displacement += 125000) {
        uint64_t timestamp = (mac_origin + 8000000 + displacement) * 1000000 + 125000;
        int64_t converted;
        assert(ftm_bridge_clock_convert(&snapshot, timestamp, 8100000, &converted));
        int64_t expected = reference_origin + (int64_t)llroundl(
            (8000000000.L + displacement * 1000.L + 125) * 1.00002L * 1.00003L);
        assert(llabs(converted - expected) <= 2);
    }
    assert(!ftm_bridge_clock_snapshot(&clock, 9500001, &snapshot));
    assert(!ftm_bridge_clock_snapshot(&clock, 7999999, &snapshot));
    input = observation(9);
    input.source_generation++;
    assert(ftm_bridge_clock_observe(&clock, &input) == FTM_BRIDGE_IDENTITY);
    assert(clock.count == 1 && !clock.snapshot.valid);
    acquire(&clock);
    input = observation(10);
    assert(ftm_bridge_clock_observe(&clock, &input) == FTM_BRIDGE_ORDER);
    assert(!clock.count && !clock.snapshot.valid);
    acquire(&clock);
    input = observation(9);
    input.host_edge += 100;
    input.host_before += 100;
    input.host_after += 100;
    assert(ftm_bridge_clock_observe(&clock, &input) == FTM_BRIDGE_INNOVATION);
    acquire(&clock);
    input = observation(9);
    input.mac_us += 100;
    assert(ftm_bridge_clock_observe(&clock, &input) == FTM_BRIDGE_MAC);
    acquire(&clock);
    input = observation(9);
    input.host_after = input.host_before + 41;
    assert(ftm_bridge_clock_observe(&clock, &input) == FTM_BRIDGE_BRACKET);
    input = observation(9);
    input.ptp_ns = INT64_MAX;
    assert(ftm_bridge_clock_observe(&clock, &input) == FTM_BRIDGE_INVALID);
    acquire(&clock);
    input = observation(9);
    input.source_valid = false;
    input.ptp_ns += 1000000000;
    assert(ftm_bridge_clock_observe(&clock, &input) == FTM_BRIDGE_INVALID);
    assert(clock.count == FTM_BRIDGE_HISTORY);
    assert(!ftm_bridge_clock_snapshot(&clock, 9000000, &snapshot));
    input = observation(10);
    assert(ftm_bridge_clock_observe(&clock, &input) == FTM_BRIDGE_OK);
    assert(ftm_bridge_clock_snapshot(&clock, 10000000, &snapshot));
    int64_t recovered;
    uint64_t recovery_timestamp = (mac_origin + 10000000) * 1000000;
    assert(ftm_bridge_clock_convert(&snapshot, recovery_timestamp, 10000000, &recovered));
    int64_t recovery_expected = reference_origin + (int64_t)llroundl(10000000000.L * 1.00002L * 1.00003L);
    assert(llabs(recovered - recovery_expected) <= 2);
    acquire(&clock);
    input = observation(9);
    input.host_rate_q32 = 0;
    assert(ftm_bridge_clock_observe(&clock, &input) == FTM_BRIDGE_INVALID);
    acquire(&clock);
    input = observation(9);
    input.ptp_ns = 0;
    assert(ftm_bridge_clock_observe(&clock, &input) == FTM_BRIDGE_RATE);
    assert(!clock.snapshot.valid);
    acquire(&clock);
    snapshot = clock.snapshot;
    snapshot.rate_q32 = INT64_MAX;
    int64_t converted;
    assert(!ftm_bridge_clock_convert(&snapshot, UINT64_MAX, 8000000, &converted));
    puts("bridge clock wrap, rate, continuity, identity and rejection tests pass");
}
