#include <assert.h>
#include <stdio.h>
#include "ptp_capable_receive.h"
int main(void)
{
    uint8_t neighbor[10] = {1,2,3,4,5,6,7,8,0,1};
    ptp_capable_message_t message = {.log_interval=0};
    memcpy(message.source_port,neighbor,10);
    ptp_capable_receive_t receiver = {0};
    for (int interval=-128; interval<=127; interval++) {
        message.log_interval=interval;
        bool accepted=ptp_capable_receive(&receiver,&message,neighbor,7,100);
        assert(accepted==(interval>=-24 && interval<=24));
        if (accepted) {
            assert(ptp_neighbor_capable(&receiver,neighbor,7,100));
            assert(!ptp_neighbor_capable(&receiver,neighbor,7,99));
            assert(!ptp_neighbor_capable(&receiver,neighbor,8,100));
            assert(ptp_neighbor_capable(&receiver,neighbor,7,receiver.expires_us-1));
            assert(!ptp_neighbor_capable(&receiver,neighbor,7,receiver.expires_us));
        }
    }
    message.log_interval=0;
    assert(ptp_capable_receive(&receiver,&message,neighbor,7,100));
    assert(receiver.expires_us==9000100);
    neighbor[9]=2;
    assert(!ptp_capable_receive(&receiver,&message,neighbor,7,1000));
    assert(receiver.expires_us==9000100);
    assert(!ptp_neighbor_capable(&receiver,neighbor,7,101));
    neighbor[9]=1;
    assert(!ptp_capable_receive(&receiver,&message,neighbor,7,INT64_MAX));
    assert(!ptp_capable_receive(&receiver,&message,neighbor,7,-1));
    assert(ptp_capable_receive(&receiver,&message,neighbor,7,1000));
    assert(receiver.expires_us==9001000);
    puts("Capability receipt: all 256 intervals, neighbor binding, exact expiry, refresh, lifecycle and overflow passed");
}
