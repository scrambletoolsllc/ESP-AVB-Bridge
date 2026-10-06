#include <assert.h>
#include <stdio.h>
#include "ptp_peer_exchange.h"
int main(void)
{
    ptp_peer_exchange_t exchange={0};
    struct ptp_header_s request={0};request.sourceidentity[7]=1;
    struct ptp_delay_resp_s response={0};response.reqidentity[7]=1;
    response.header.sourceidentity[7]=2;response.header.flags[0]=0; /* Still requires matched Follow_Up. */
    struct ptp_delay_resp_follow_up_s follow={0}, retained;
    follow.reqidentity[7]=1;follow.header.sourceidentity[7]=2;
    struct timespec transmit={100,1000},receive={100,5000};
    ptp_peer_measurement_t measurement={0};uint32_t retained_generation;
    for(unsigned scenario=0;scenario<5;scenario++) {
        ptp_peer_invalidate(&exchange);
        uint32_t generation=ptp_peer_begin(&exchange,0,&request,1000);
        assert(ptp_peer_response(&exchange,&response,&receive,100)==PTP_PEER_ACCEPTED);
        assert(!exchange.published);
        assert(!ptp_peer_finish(&exchange,&follow,200,&measurement));
        assert(exchange.follow_up_pending);
        assert(!ptp_peer_take_follow_up(&exchange,201,&retained,&retained_generation));
        if(scenario==1) {
            ptp_peer_cancel(&exchange,generation);
            assert(!ptp_peer_publish(&exchange,generation,&transmit,300));
        } else if(scenario==2) {
            ptp_peer_invalidate(&exchange);
            assert(!ptp_peer_publish(&exchange,generation,&transmit,300));
        } else {
            assert(ptp_peer_publish(&exchange,generation,&transmit,300));
        }
        if(scenario==3) {
            assert(!ptp_peer_finish(&exchange,&follow,301,&measurement));
            assert(exchange.multiple); /* Duplicate retained Follow_Up. */
        }
        int64_t now=scenario==4 ? 1000 : 400;
        bool ready=ptp_peer_take_follow_up(&exchange,now,&retained,&retained_generation);
        assert(ready==(scenario==0));
        if(ready) {
            assert(retained_generation==generation);
            assert(ptp_peer_finish(&exchange,&retained,now,&measurement));
            assert(measurement.transmit.tv_nsec==1000 && measurement.receive.tv_nsec==5000);
            assert(!ptp_peer_take_follow_up(&exchange,now,&retained,&retained_generation));
        }
    }
    puts("Early response+Follow_Up retained until confirmed T1, canceled on failure/lifecycle, duplicates and expired replay rejected");
}
