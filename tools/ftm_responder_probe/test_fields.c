#include <assert.h>
#include "ftm_responder_fields.h"
int main(void)
{
    uint32_t words[3] = {12345, (23456 & 0xffffc000) | 61,
                        (23456U & 16383) << 18 | (172 << 7) | 35};
    assert(ftm_responder_tx_ticks(words) == UINT64_C(7896168));
    assert(ftm_responder_rx_ticks(words) == UINT64_C(14998980));
    words[2] = (words[2] & ~(2047U << 7)) | (1876 << 7);
    assert(ftm_responder_rx_ticks(words) == UINT64_C(14998980));
    words[2] = (words[2] & ~(2047U << 7)) | (1024 << 7);
    assert(ftm_responder_rx_ticks(words) == UINT64_C(14999832));
    words[0] = UINT32_MAX;
    words[1] = UINT32_C(0xffffc000) | 79;
    words[2] = (UINT32_C(16383) << 18) | 79;
    assert(ftm_responder_tx_ticks(words) ==
           ((uint64_t)UINT32_MAX * 80 + 79 - 640) * 8);
    assert(ftm_responder_rx_ticks(words) ==
           (uint64_t)UINT32_MAX * 640 - 13312 + 79 * 8);
    return 0;
}
