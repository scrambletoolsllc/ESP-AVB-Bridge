#ifndef FTM_CLOCK_MODEL_H
#define FTM_CLOCK_MODEL_H
#include <stdbool.h>
#include <stdint.h>
#define FTM_MODEL_WINDOW 32
#define FTM_MODEL_ENTRIES 16

typedef struct { uint64_t t1, t2, t3, t4; uint32_t rtt; } ftm_model_entry_t;
typedef struct {
    uint32_t generation, attempt, dropped, mac_us;
    uint8_t peer[6], count;
    int64_t before_us, after_us;
    ftm_model_entry_t entries[FTM_MODEL_ENTRIES];
} ftm_model_report_t;
typedef struct {
    bool valid;
    uint32_t generation, attempt;
    uint8_t peer[6];
    int64_t local_anchor_ps, remote_anchor_ps, updated_us;
    double correction_ps, rate_delta;
} ftm_model_snapshot_t;
/* Convert near the anchor using integer differences:
 * remote = remote_anchor + elapsed + correction + rate_delta * elapsed.
 * This relative epoch is not an upstream clock or a responder boot epoch.
 */
typedef struct {
    unsigned count;
    bool identity_set, previous_set;
    uint32_t generation, dropped, attempt;
    uint8_t peer[6];
    int64_t local[FTM_MODEL_WINDOW], remote[FTM_MODEL_WINDOW];
    int64_t previous_local, previous_remote, previous_t1, updated_us;
    ftm_model_snapshot_t snapshot;
} ftm_model_t;
typedef enum {
    FTM_MODEL_OK, FTM_MODEL_INPUT, FTM_MODEL_LOCAL_STEP, FTM_MODEL_REMOTE_STEP,
    FTM_MODEL_STALE, FTM_MODEL_RATE, FTM_MODEL_INNOVATION, FTM_MODEL_DROPPED
} ftm_model_status_t;
typedef struct {
    bool predicted;
    unsigned entries, wraps;
    double rate_ppm, median_error_ps, max_abs_error_ps;
} ftm_model_result_t;
void ftm_model_reset(ftm_model_t *model);
/* One task owns model. A rejection clears history; eight fresh reports
 * are required before publication. Input epochs must be <= INT64_MAX/4 ps.
 */
ftm_model_status_t ftm_model_observe(ftm_model_t *model,
    const ftm_model_report_t *report, int64_t now_us, ftm_model_result_t *result);
bool ftm_model_snapshot(const ftm_model_t *model, int64_t now_us,
    uint32_t generation, ftm_model_snapshot_t *snapshot);
#endif
