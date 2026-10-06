#ifndef FTM_RAW_PROBE_H
#define FTM_RAW_PROBE_H
#include "sdkconfig.h"
#include "ftm_clock_model.h"
#if CONFIG_FTM_LIVE_MODEL
/* Task context only. Copies an observation-only relative clock snapshot. */
bool ftm_raw_model_snapshot(ftm_model_snapshot_t *snapshot);
#endif
#endif
