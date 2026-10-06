#include "ftm_follow_up_tx.h"
#include <limits.h>
#ifdef ESP_PLATFORM
#include "esp_attr.h"
#else
#define IRAM_ATTR
#endif

bool IRAM_ATTR ftm_follow_up_emit(const ftm_follow_up_tx_t *snapshot,
    uint64_t departure_ps, int64_t now_us, uint8_t followup_token,
    uint16_t sequence, uint8_t *output, size_t size)
{
    if (!output || size < FTM_FOLLOW_UP_IE_SIZE) return false;
    volatile uint8_t *bytes = output;
    /* A declined frame still carries the fixed registered IE length. */
    for (unsigned index = 2; index < FTM_FOLLOW_UP_IE_SIZE; ++index) bytes[index] = 0;
    if (!snapshot || !snapshot->valid || !followup_token ||
        departure_ps < snapshot->not_before_ps || now_us < 0 ||
        now_us > snapshot->expires_us || snapshot->rate_q32 < INT64_C(4286377361) ||
        snapshot->rate_q32 > INT64_C(4303557231)) return false;
    bool negative = departure_ps < snapshot->anchor_ps;
    uint64_t distance = negative ? snapshot->anchor_ps - departure_ps : departure_ps - snapshot->anchor_ps;
    if (distance > UINT64_C(1500000000000)) return false;
    /* Divide a bounded 64-bit ps interval using only native 32-bit divisions. */
    uint32_t high = distance >> 32, low = distance;
    uint32_t remainder = high * 296 + low % 1000;
    uint32_t nanoseconds = high * 4294967 + low / 1000 + remainder / 1000;
    remainder %= 1000;
    int64_t scaled = (int64_t)nanoseconds * 65536 + remainder * 65536 / 1000;
    scaled += (int64_t)nanoseconds * (snapshot->rate_q32 - INT64_C(4294967296)) / 65536;
    if (negative) scaled = -scaled;
    if ((scaled > 0 && snapshot->correction_scaled > INT64_MAX - scaled) ||
        (scaled < 0 && snapshot->correction_scaled < INT64_MIN - scaled)) return false;
    uint64_t correction = (uint64_t)(snapshot->correction_scaled + scaled);
    for (unsigned index = 2; index < FTM_FOLLOW_UP_IE_SIZE; ++index)
        bytes[index] = snapshot->ie[index];
    for (unsigned index = 0; index < 8; ++index)
        bytes[14 + index] = correction >> (56 - 8 * index);
    bytes[36] = sequence >> 8;
    bytes[37] = sequence;
    return true;
}
