#include "ftm_bridge_clock.h"
#include <math.h>
#include <string.h>

#define Q32_SCALE 4294967296.0
#define MAX_AGE_US 1500000
#define MAX_COUNTER_SPAN UINT64_C(120000000)

void ftm_bridge_clock_reset(ftm_bridge_clock_t *clock)
{
    memset(clock, 0, sizeof(*clock));
}

static ftm_bridge_result_t reject(ftm_bridge_clock_t *clock, ftm_bridge_result_t reason)
{
    ftm_bridge_clock_reset(clock);
    return reason;
}

static double fit_raw_rate(const ftm_bridge_observation_t *history, unsigned count,
                           double *intercept)
{
    double local_mean = 0, host_mean = 0, covariance = 0, variance = 0;
    for (unsigned index = 0; index < count; ++index) {
        local_mean += (double)(history[index].radio_edge - history[0].radio_edge);
        host_mean += (double)(history[index].host_edge - history[0].host_edge);
    }
    local_mean /= count;
    host_mean /= count;
    for (unsigned index = 0; index < count; ++index) {
        double local_delta = (double)(history[index].radio_edge - history[0].radio_edge) - local_mean;
        double host_delta = (double)(history[index].host_edge - history[0].host_edge) - host_mean;
        covariance += local_delta * host_delta;
        variance += local_delta * local_delta;
    }
    double rate = covariance / variance;
    *intercept = host_mean - rate * local_mean;
    return rate;
}

ftm_bridge_result_t ftm_bridge_clock_observe(ftm_bridge_clock_t *clock,
    const ftm_bridge_observation_t *observation)
{
    if (!clock || !observation) return FTM_BRIDGE_INVALID;
    if (!observation->host_boot || !observation->radio_boot ||
        !observation->source_generation || !observation->sequence || observation->ptp_ns < 0 ||
        observation->ptp_ns > INT64_MAX - INT64_C(10000000000) ||
        observation->received_us < 0 || observation->trim_ppb < -512000 ||
        observation->trim_ppb > 512000 ||
        observation->host_rate_q32 < INT64_C(4290672328) ||
        observation->host_rate_q32 > INT64_C(4299262263))
        return reject(clock, FTM_BRIDGE_INVALID);
    if (!observation->host_edge || !observation->radio_edge ||
        observation->host_before < observation->host_edge ||
        observation->host_after < observation->host_before ||
        observation->radio_before < observation->radio_edge ||
        observation->radio_after < observation->radio_before ||
        observation->host_after - observation->host_edge > 400000 ||
        observation->radio_after - observation->radio_edge > 400000 ||
        observation->host_after - observation->host_before > 40 ||
        observation->radio_after - observation->radio_before > 40)
        return reject(clock, FTM_BRIDGE_BRACKET);
    ftm_bridge_result_t result = FTM_BRIDGE_ACQUIRING;
    if (clock->count) {
        const ftm_bridge_observation_t *previous = &clock->history[clock->count - 1];
        if (previous->host_boot != observation->host_boot ||
            previous->radio_boot != observation->radio_boot ||
            previous->source_generation != observation->source_generation) {
            ftm_bridge_clock_reset(clock);
            result = FTM_BRIDGE_IDENTITY;
        } else if (observation->sequence - previous->sequence != 1 ||
                   observation->host_edge <= previous->host_edge ||
                   observation->radio_edge <= previous->radio_edge ||
                   observation->radio_before <= previous->radio_after ||
                   observation->host_edge - previous->host_edge > MAX_COUNTER_SPAN ||
                   observation->radio_edge - previous->radio_edge > MAX_COUNTER_SPAN ||
                   observation->received_us <= previous->received_us ||
                   observation->received_us - previous->received_us > MAX_AGE_US) {
            return reject(clock, FTM_BRIDGE_ORDER);
        } else {
            double elapsed_ticks = (double)(observation->radio_before - previous->radio_before) +
                ((double)(observation->radio_after - observation->radio_before) -
                 (double)(previous->radio_after - previous->radio_before)) / 2;
            uint32_t elapsed_mac_us = observation->mac_us - previous->mac_us;
            if (fabs((double)elapsed_mac_us * 1000 - elapsed_ticks * 25) > 2500)
                return reject(clock, FTM_BRIDGE_MAC);
        }
    }
    if (clock->count == FTM_BRIDGE_HISTORY) {
        double intercept;
        double rate = fit_raw_rate(clock->history, clock->count, &intercept);
        double predicted = rate * (double)(observation->radio_edge - clock->history[0].radio_edge) + intercept;
        double actual = (double)(observation->host_edge - clock->history[0].host_edge);
        if (!isfinite(rate) || fabs(actual - predicted) * 25 > 1000)
            return reject(clock, FTM_BRIDGE_INNOVATION);
        memmove(clock->history, clock->history + 1,
                (FTM_BRIDGE_HISTORY - 1) * sizeof(clock->history[0]));
        --clock->count;
    }
    clock->history[clock->count++] = *observation;
    clock->snapshot.valid = false;
    /* Raw edge frequency remains measurable while a PTP anchor is rejected. */
    if (!observation->source_valid) return FTM_BRIDGE_INVALID;
    if (clock->count < FTM_BRIDGE_HISTORY) return result;

    double intercept;
    double raw_rate = fit_raw_rate(clock->history, clock->count, &intercept);
    if (!isfinite(raw_rate) || fabs(raw_rate - 1) > .001)
        return reject(clock, FTM_BRIDGE_RATE);
    double host_rate = observation->host_rate_q32 / Q32_SCALE;
    double reference_rate = raw_rate * host_rate;
    double host_midpoint = (double)(observation->host_before - observation->host_edge) +
        (observation->host_after - observation->host_before) / 2.0;
    double radio_midpoint = (double)(observation->radio_before - observation->radio_edge) +
        (observation->radio_after - observation->radio_before) / 2.0;
    /* A coarse MAC value spans one microsecond. Anchor its lower boundary. */
    double correction = -host_midpoint * 25 * host_rate +
        (radio_midpoint * 25 - 500) * reference_rate;
    int64_t reference_ns = observation->ptp_ns + (int64_t)llround(correction);
    int64_t rate_q32 = (int64_t)llround(reference_rate * Q32_SCALE);
    if (reference_ns < 0 || rate_q32 < INT64_C(4286377361) ||
        rate_q32 > INT64_C(4303557231)) return reject(clock, FTM_BRIDGE_RATE);
    uint32_t uncertainty = (uint32_t)ceil(
        (observation->host_after - observation->host_before) * 12.5 * host_rate +
        ((observation->radio_after - observation->radio_before) * 12.5 + 500) * reference_rate);
    clock->snapshot = (ftm_bridge_snapshot_t){
        .host_boot = observation->host_boot, .radio_boot = observation->radio_boot,
        .source_generation = observation->source_generation, .sequence = observation->sequence,
        .mac_us = observation->mac_us, .read_uncertainty_ns = uncertainty,
        .reference_ns = reference_ns,
        .refreshed_us = observation->received_us,
        .rate_q32 = rate_q32, .valid = true,
    };
    return FTM_BRIDGE_OK;
}

bool ftm_bridge_clock_snapshot(const ftm_bridge_clock_t *clock, int64_t now_us,
    ftm_bridge_snapshot_t *snapshot)
{
    if (!clock || !snapshot) return false;
    *snapshot = clock->snapshot;
    if (now_us < snapshot->refreshed_us || now_us - snapshot->refreshed_us > MAX_AGE_US)
        snapshot->valid = false;
    return snapshot->valid;
}

bool ftm_bridge_clock_convert(const ftm_bridge_snapshot_t *snapshot,
    uint64_t local_ps, int64_t now_us, int64_t *reference_ns)
{
    if (!snapshot || !reference_ns || !snapshot->valid || now_us < snapshot->refreshed_us ||
        now_us - snapshot->refreshed_us > MAX_AGE_US) return false;
    if (snapshot->rate_q32 < INT64_C(4286377361) ||
        snapshot->rate_q32 > INT64_C(4303557231) || snapshot->reference_ns < 0 ||
        snapshot->reference_ns > INT64_MAX - INT64_C(2000000000)) return false;
    uint32_t delta = (uint32_t)(local_ps / 1000000) - snapshot->mac_us;
    int64_t delta_us = delta <= INT32_MAX ? delta : (int64_t)delta - INT64_C(4294967296);
    if (delta_us < -1500000 || delta_us > 1500000) return false;
    int64_t delta_ns = delta_us * 1000 + (int64_t)(local_ps % 1000000) / 1000;
    int64_t converted = snapshot->reference_ns + delta_ns * snapshot->rate_q32 / INT64_C(4294967296);
    if (converted < 0) return false;
    *reference_ns = converted;
    return true;
}
