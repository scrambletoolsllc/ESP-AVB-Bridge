#pragma once
#include "ftm_follow_up.h"

typedef struct {
    uint64_t anchor_ps, not_before_ps;
    int64_t expires_us, correction_scaled, rate_q32;
    uint32_t generation;
    uint8_t ie[FTM_FOLLOW_UP_IE_SIZE];
    bool valid;
} ftm_follow_up_tx_t;

/* Bounded integer-only callback path. The snapshot must reside in DRAM.
 * sequence is the transmitting port's Follow_Up sequenceId; the FTM dialog
 * tokens, not this field, pair the IE with its measurement. */
bool ftm_follow_up_emit(const ftm_follow_up_tx_t *snapshot, uint64_t departure_ps,
    int64_t now_us, uint8_t followup_token, uint16_t sequence, uint8_t *output, size_t size);
