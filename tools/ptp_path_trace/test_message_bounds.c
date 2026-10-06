#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "ptp_message_bounds.h"
int main(void) {
    uint8_t packet[256] = {0};
    const struct { unsigned type, minimum; } cases[] = {
        {0,44},{1,44},{2,54},{3,54},{8,76},{9,54},{10,54},{11,64},{12,44}
    };
    assert(!ptp_message_bounded_length(NULL, sizeof(packet)));
    for (unsigned index = 0; index < sizeof(cases)/sizeof(cases[0]); ++index) {
        memset(packet, 0, sizeof(packet));
        packet[0] = 0x10 | cases[index].type;
        packet[1] = 2;
        packet[3] = cases[index].minimum;
        for (size_t received = 0; received < cases[index].minimum; ++received)
            assert(!ptp_message_bounded_length(packet, received));
        assert(ptp_message_bounded_length(packet, sizeof(packet)) == cases[index].minimum);
        --packet[3];
        assert(!ptp_message_bounded_length(packet, sizeof(packet)));
        packet[2] = 1; packet[3] = 1;
        assert(!ptp_message_bounded_length(packet, sizeof(packet)));
    }
    packet[0] = 8; packet[1] = 2; packet[2] = 0; packet[3] = 44;
    assert(ptp_message_bounded_length(packet, sizeof(packet)) == 44);
    packet[1] = 1;
    assert(!ptp_message_bounded_length(packet, sizeof(packet)));
    puts("PTP version, per-type truncation, advertised length and padding tests passed");
}
