#include <assert.h>
#include <string.h>
#include "ptp_timing_snapshot.h"

int main(void)
{
    uint8_t frame[76] = {[0]=0x18, [1]=2, [3]=76, [45]=3, [47]=28,
        [49]=0x80, [50]=0xc2, [53]=1};
    assert(ptp_timing_payload_valid(frame, sizeof(frame)));
    assert(!ptp_timing_payload_valid(frame, 75));
    assert(!ptp_timing_payload_valid(NULL, 76));
    const unsigned critical[] = {0, 1, 3, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53};
    for (unsigned index = 0; index < sizeof(critical)/sizeof(critical[0]); ++index) {
        uint8_t candidate[76];
        memcpy(candidate, frame, sizeof(frame));
        candidate[critical[index]] ^= 1;
        assert(!ptp_timing_payload_valid(candidate, sizeof(candidate)));
    }
    frame[3] = 44;
    assert(!ptp_timing_payload_valid(frame, sizeof(frame)));
    return 0;
}
