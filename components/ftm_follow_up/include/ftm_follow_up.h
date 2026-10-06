#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define FTM_FOLLOW_UP_SIZE 76
#define FTM_FOLLOW_UP_IE_SIZE 82

typedef struct {
    int64_t origin_ns, correction_scaled;
    int32_t cumulative_rate_offset;
    uint16_t sequence, time_base;
    uint8_t source_port[10], domain;
    int8_t log_interval;
} ftm_follow_up_fields_t;

/* Portable reference implementation, not yet audited for an IRAM callback.
 * Correction units are 2^-16 ns. The caller supplies the residence and path
 * contribution in BTC units and owns freshness and exchange association. */
bool ftm_follow_up_relay(const uint8_t *upstream, size_t size,
    const uint8_t source_port[10], uint16_t sequence, int8_t log_interval,
    int64_t additional_correction_scaled, int64_t cumulative_rate_offset,
    uint8_t output[FTM_FOLLOW_UP_IE_SIZE]);

/* One complete vendor IE, with no trailing bytes. Admission by selected
 * source, domain, generation and FTM token is the caller's responsibility. */
bool ftm_follow_up_parse(const uint8_t *ie, size_t size,
    ftm_follow_up_fields_t *fields);
