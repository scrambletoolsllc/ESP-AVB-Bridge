#include "ftm_clock_model.h"
#include <math.h>
#include <string.h>

#define REMOTE_PERIOD (INT64_C(1) << 48)
#define MAC_PERIOD ((INT64_C(1) << 32) * 1000000)
#define MAX_EPOCH (INT64_MAX / 4)
#define MAX_AGE_US INT64_C(2000000)

static int64_t median_integer(int64_t *values, unsigned count)
{
    for (unsigned index = 1; index < count; ++index) {
        int64_t value = values[index];
        unsigned position = index;
        while (position && values[position - 1] > value) {
            values[position] = values[position - 1];
            --position;
        }
        values[position] = value;
    }
    int64_t lower = values[(count - 1) / 2], upper = values[count / 2];
    return lower + (upper - lower) / 2;
}

static double median_double(double *values, unsigned count)
{
    for (unsigned index = 1; index < count; ++index) {
        double value = values[index];
        unsigned position = index;
        while (position && values[position - 1] > value) {
            values[position] = values[position - 1];
            --position;
        }
        values[position] = value;
    }
    return (values[(count - 1) / 2] + values[count / 2]) / 2;
}

static bool extend_near(int64_t value, int64_t anchor, int64_t period,
                        int64_t budget, int64_t *extended)
{
    if (anchor < 0 || anchor > MAX_EPOCH || value < 0 || value >= period) return false;
    int64_t delta = value - anchor % period;
    if (delta > period / 2) delta -= period;
    if (delta < -period / 2) delta += period;
    if (delta < -budget || delta > budget || anchor + delta < 0 ||
        anchor + delta > MAX_EPOCH) return false;
    *extended = anchor + delta;
    return true;
}

void ftm_model_reset(ftm_model_t *model) { memset(model, 0, sizeof(*model)); }

static bool fit(const ftm_model_t *model, ftm_model_snapshot_t *snapshot)
{
    *snapshot = (ftm_model_snapshot_t){0};
    if (model->count < 8) return true;
    double average_elapsed = 0, average_correction = 0;
    int64_t local_anchor = model->local[0], remote_anchor = model->remote[0];
    for (unsigned index = 0; index < model->count; ++index) {
        int64_t elapsed = model->local[index] - local_anchor;
        int64_t correction = (model->remote[index] - remote_anchor) - elapsed;
        average_elapsed += (double)elapsed;
        average_correction += (double)correction;
    }
    average_elapsed /= model->count;
    average_correction /= model->count;
    double variance = 0, covariance = 0;
    for (unsigned index = 0; index < model->count; ++index) {
        int64_t elapsed = model->local[index] - local_anchor;
        int64_t correction = (model->remote[index] - remote_anchor) - elapsed;
        double centered = (double)elapsed - average_elapsed;
        variance += centered * centered;
        covariance += centered * ((double)correction - average_correction);
    }
    if (variance <= 0) return false;
    double rate = covariance / variance;
    if (!isfinite(rate) || fabs(rate) > 200e-6) return false;
    snapshot->valid = true;
    snapshot->local_anchor_ps = local_anchor;
    snapshot->remote_anchor_ps = remote_anchor;
    snapshot->rate_delta = rate;
    snapshot->correction_ps = average_correction - rate * average_elapsed;
    return true;
}

static ftm_model_status_t reject(ftm_model_t *model, ftm_model_status_t status)
{
    ftm_model_reset(model);
    return status;
}

ftm_model_status_t ftm_model_observe(ftm_model_t *model,
    const ftm_model_report_t *report, int64_t now_us, ftm_model_result_t *result)
{
    *result = (ftm_model_result_t){0};
    if (report->count == 0 || report->count > FTM_MODEL_ENTRIES ||
        report->before_us < 0 || report->after_us < report->before_us ||
        report->after_us - report->before_us > 50 || now_us < report->after_us ||
        now_us - report->after_us > 500000)
        return reject(model, FTM_MODEL_INPUT);
    if (model->identity_set && (model->generation != report->generation ||
                               memcmp(model->peer, report->peer, 6))) ftm_model_reset(model);
    if (model->identity_set && model->dropped != report->dropped)
        return reject(model, FTM_MODEL_DROPPED);
    if (model->identity_set && (report->attempt <= model->attempt ||
        report->after_us <= model->updated_us || report->after_us - model->updated_us > MAX_AGE_US))
        return reject(model, FTM_MODEL_STALE);
    int64_t local[FTM_MODEL_ENTRIES], remote[FTM_MODEL_ENTRIES];
    int64_t previous_local = model->previous_local, previous_remote = model->previous_remote;
    int64_t previous_t1 = model->previous_t1, last_t3 = 0;
    bool previous_set = model->previous_set;
    unsigned count = 0, wraps = 0;
    for (unsigned index = 0; index < report->count; ++index) {
        const ftm_model_entry_t *entry = &report->entries[index];
        if (!entry->rtt || entry->rtt > INT32_MAX) continue;
        if (entry->t1 >= REMOTE_PERIOD || entry->t4 >= REMOTE_PERIOD ||
            entry->t2 > MAX_EPOCH || entry->t3 > MAX_EPOCH || entry->t3 <= entry->t2 ||
            entry->t3 - entry->t2 >= UINT64_C(10000000000))
            return reject(model, FTM_MODEL_INPUT);
        int64_t turnaround = (entry->t4 - entry->t1) & (REMOTE_PERIOD - 1);
        if (turnaround <= 0 || turnaround >= INT64_C(10000000000))
            return reject(model, FTM_MODEL_INPUT);
        int64_t local_midpoint = (entry->t2 + entry->t3) / 2;
        int64_t remote_t1 = entry->t1;
        if (previous_set) {
            int64_t gap = local_midpoint - previous_local;
            if (gap <= 0 || gap > MAX_AGE_US * 1000000)
                return reject(model, FTM_MODEL_LOCAL_STEP);
            if (!extend_near(entry->t1, previous_remote + gap - turnaround / 2,
                             REMOTE_PERIOD, INT64_C(2000000000), &remote_t1) || remote_t1 <= previous_t1)
                return reject(model, FTM_MODEL_REMOTE_STEP);
            wraps += remote_t1 / REMOTE_PERIOD - previous_t1 / REMOTE_PERIOD;
        }
        local[count] = local_midpoint;
        remote[count] = remote_t1 + turnaround / 2;
        previous_local = local[count]; previous_remote = remote[count]; previous_t1 = remote_t1;
        previous_set = true;
        last_t3 = entry->t3;
        ++count;
    }
    if (!count) return reject(model, FTM_MODEL_INPUT);
    int64_t callback_mac;
    if (!extend_near((int64_t)report->mac_us * 1000000, last_t3, MAC_PERIOD,
                     INT64_C(500000000000), &callback_mac) || callback_mac - last_t3 < -1000000)
        return reject(model, FTM_MODEL_STALE);
    ftm_model_snapshot_t prior;
    if (!fit(model, &prior)) return reject(model, FTM_MODEL_RATE);
    result->predicted = prior.valid;
    if (prior.valid) {
        double errors[FTM_MODEL_ENTRIES];
        for (unsigned index = 0; index < count; ++index) {
            int64_t elapsed = local[index] - prior.local_anchor_ps;
            errors[index] = (double)((remote[index] - prior.remote_anchor_ps) - elapsed)
                            - (prior.correction_ps + prior.rate_delta * (double)elapsed);
            if (fabs(errors[index]) > result->max_abs_error_ps) result->max_abs_error_ps = fabs(errors[index]);
        }
        result->median_error_ps = median_double(errors, count);
        result->rate_ppm = prior.rate_delta * 1e6;
        if (fabs(result->median_error_ps) > 20000000) return reject(model, FTM_MODEL_INNOVATION);
    }
    int64_t corrections[FTM_MODEL_ENTRIES];
    for (unsigned index = 0; index < count; ++index) corrections[index] = remote[index] - local[index];
    int64_t local_center = median_integer(local, count);
    int64_t correction = median_integer(corrections, count);
    if (model->count == FTM_MODEL_WINDOW) {
        memmove(model->local, model->local + 1, (FTM_MODEL_WINDOW - 1) * sizeof(int64_t));
        memmove(model->remote, model->remote + 1, (FTM_MODEL_WINDOW - 1) * sizeof(int64_t));
        --model->count;
    }
    model->local[model->count] = local_center;
    model->remote[model->count++] = local_center + correction;
    model->previous_local = previous_local; model->previous_remote = previous_remote;
    model->previous_t1 = previous_t1; model->previous_set = true;
    model->identity_set = true; model->generation = report->generation;
    model->attempt = report->attempt; model->dropped = report->dropped;
    model->updated_us = report->after_us;
    memcpy(model->peer, report->peer, 6);
    if (!fit(model, &model->snapshot)) return reject(model, FTM_MODEL_RATE);
    model->snapshot.generation = report->generation;
    model->snapshot.attempt = report->attempt;
    model->snapshot.updated_us = report->after_us;
    memcpy(model->snapshot.peer, report->peer, 6);
    result->entries = count; result->wraps = wraps;
    return FTM_MODEL_OK;
}

bool ftm_model_snapshot(const ftm_model_t *model, int64_t now_us,
    uint32_t generation, ftm_model_snapshot_t *snapshot)
{
    *snapshot = model->snapshot;
    snapshot->valid = snapshot->valid && generation == snapshot->generation &&
        now_us >= snapshot->updated_us && now_us - snapshot->updated_us <= MAX_AGE_US;
    return snapshot->valid;
}
