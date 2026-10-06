#ifndef FTM_RESPONDER_FIELDS_H
#define FTM_RESPONDER_FIELDS_H
#include <stdint.h>

static inline uint64_t ftm_responder_tx_ticks(const uint32_t words[3])
{
    return ((uint64_t)words[0] * 80 + (words[1] & 127) - 640) * 8;
}

static inline uint64_t ftm_responder_rx_ticks(const uint32_t words[3])
{
    uint32_t coarse = (words[1] & UINT32_C(0xffffc000)) | (words[2] >> 18);
    uint32_t correction = (words[2] >> 7) & 2047;
    if (correction & 1024) correction = 2048 - correction;
    return (uint64_t)coarse * 640 - 13312 + (words[2] & 127) * 8 + correction;
}
#endif
