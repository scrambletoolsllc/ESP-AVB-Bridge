#include <assert.h>
#include <stdio.h>
#include "ptp_peer_exchange.h"

int main(void)
{
    ptp_peer_exchange_t exchange = {0};
    struct ptp_header_s request = {0};
    struct ptp_delay_resp_s response = {0};
    struct ptp_delay_resp_follow_up_s follow = {0};
    struct timespec transmit = {100, 1000}, receive = {100, 5000};
    ptp_peer_measurement_t measurement;
    request.sourceidentity[7] = 1;
    response.reqidentity[7] = follow.reqidentity[7] = 1;
    response.header.sourceidentity[7] = follow.header.sourceidentity[7] = 2;
    response.header.flags[0] = 2;
    for (unsigned index = 0; index < 70000; index++) {
        int64_t now = (int64_t)index * 1000;
        uint32_t generation = ptp_peer_begin(&exchange, 0, &request, now + 1000);
        assert(!ptp_peer_expire(&exchange, now + 1000)); /* No published T1. */
        assert(ptp_peer_publish(&exchange, generation, &transmit, now));
        if (index % 2) {
            assert(ptp_peer_response(&exchange, &response, &receive, now + 100)
                   == PTP_PEER_ACCEPTED);
        }
        assert(!ptp_peer_expire(&exchange, now + 999));
        assert(ptp_peer_expire(&exchange, now + 1000));
        assert(!ptp_peer_expire(&exchange, now + 2000));
        assert(exchange.lost_responses == (index < UINT16_MAX ? index + 1 : UINT16_MAX));
        assert(!ptp_peer_finish(&exchange, &follow, now + 1000, &measurement));
    }
    assert(exchange.missing_response == 35000 && exchange.missing_follow_up == 35000);
    uint32_t generation = ptp_peer_begin(&exchange, 0, &request, 1000);
    assert(ptp_peer_publish(&exchange, generation, &transmit, 100));
    assert(ptp_peer_response(&exchange, &response, &receive, 200) == PTP_PEER_ACCEPTED);
    assert(exchange.lost_responses == UINT16_MAX); /* Response alone cannot clear. */
    follow.header.sourceportindex[1] = 9;
    assert(!ptp_peer_finish(&exchange, &follow, 300, &measurement));
    assert(exchange.lost_responses == UINT16_MAX);
    follow.header.sourceportindex[1] = 0;
    assert(ptp_peer_finish(&exchange, &follow, 300, &measurement));
    assert(exchange.lost_responses == 0);
    assert(!ptp_peer_expire(&exchange, 1000));
    ptp_peer_invalidate(&exchange);
    assert(!exchange.lost_responses && !exchange.missing_response && !exchange.missing_follow_up);
    puts("Peer losses: deadlines, missing response/Follow_Up, once-only count, saturation, matched completion and lifecycle reset passed");
}
