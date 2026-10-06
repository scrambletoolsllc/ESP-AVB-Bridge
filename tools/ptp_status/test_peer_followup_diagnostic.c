#include <assert.h>
#include <stdio.h>
#include "ptp_peer_exchange.h"
int main(void) {
    struct ptp_header_s request = {0}; request.sourceidentity[7] = 1;
    struct ptp_delay_resp_s response = {0}; response.reqidentity[7] = 1;
    response.header.sourceidentity[7] = 2;
    struct ptp_delay_resp_follow_up_s follow = {0};
    follow.reqidentity[7] = 1; follow.header.sourceidentity[7] = 2;
    struct timespec timestamp = {100, 5};
    for (unsigned reason = 0; reason < 8; ++reason) {
        ptp_peer_exchange_t exchange = {0};
        uint32_t generation = ptp_peer_begin(&exchange, 0, &request, 1000);
        assert(ptp_peer_publish(&exchange, generation, &timestamp, 10));
        assert(ptp_peer_response(&exchange, &response, &timestamp, 20) == PTP_PEER_ACCEPTED);
        struct ptp_delay_resp_follow_up_s altered = follow;
        int64_t now = 30;
        switch (reason) {
        case 0: exchange.published = false; break;
        case 1: exchange.multiple = true; break;
        case 2: now = 1000; break;
        case 3: altered.reqportindex[1] = 2; break;
        case 4: exchange.response_seen = false; break;
        case 5: altered.origintimestamp[6] = 0xff; break;
        case 6: altered.header.sourceportindex[1] = 3; break;
        case 7: exchange.consumed = true; break;
        }
        ptp_peer_measurement_t result;
        assert(!ptp_peer_finish(&exchange, &altered, now, &result));
        assert(exchange.follow_up_count == 1);
        assert(exchange.follow_up_rejections == (1U << reason));
        altered.header.sequenceid[1] = 1;
        assert(!ptp_peer_finish(&exchange, &altered, now, &result));
        assert(exchange.follow_up_count == 1);
        exchange.follow_up_count = UINT16_MAX;
        assert(!ptp_peer_finish(&exchange, &follow, 1000, &result));
        assert(exchange.follow_up_count == UINT16_MAX);
    }
    puts("Follow_Up diagnostic distinguishes all rejection reasons, ignores foreign sequence, saturates counters");
}
