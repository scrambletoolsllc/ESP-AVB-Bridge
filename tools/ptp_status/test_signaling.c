#include <assert.h>
#include <stdio.h>
#include "ptp_signaling.h"
int main(void) {
    uint8_t message[128] = {0x1c,2,0,60,0};
    uint8_t local[10] = {1,2,3,4,5,6,7,8,0,1};
    uint8_t source[10] = {9,8,7,6,5,4,3,2,0,2};
    const uint8_t capable[] = {0x80,0,0,12,0,0x80,0xc2,0,0,4,0xff,0,0,0,0,0};
    memcpy(message+20,source,10); memset(message+34,255,10);
    memcpy(message+44,capable,16);
    ptp_capable_message_t output = {0};
    for (unsigned length=0; length<60; ++length)
        assert(ptp_signaling_read_capable(message,length,0,local,&output)==PTP_SIGNALING_MALFORMED);
    assert(ptp_signaling_read_capable(message,sizeof(message),0,local,&output)==PTP_SIGNALING_CAPABLE);
    assert(output.log_interval==-1 && !memcmp(output.source_port,source,10));
    /* Reserved flags and bytes are ignored on receipt. */
    memset(message+55,0xaa,5);
    assert(ptp_signaling_read_capable(message,60,0,local,&output)==PTP_SIGNALING_CAPABLE);
    message[5]=1;
    assert(ptp_signaling_read_capable(message,60,0,local,&output)==PTP_SIGNALING_IGNORED);
    message[5]=0;
    uint8_t other_port[10];memcpy(other_port,local,10);other_port[9]=8;
    memcpy(message+20,other_port,10);
    assert(ptp_signaling_read_capable(message,60,0,local,&output)==PTP_SIGNALING_IGNORED);
    memcpy(message+20,source,10);
    message[4]=1;
    assert(ptp_signaling_read_capable(message,60,0,local,&output)==PTP_SIGNALING_IGNORED);
    message[4]=0; memcpy(message+34,local,10);
    assert(ptp_signaling_read_capable(message,60,0,local,&output)==PTP_SIGNALING_CAPABLE);
    message[43]=2;
    assert(ptp_signaling_read_capable(message,60,0,local,&output)==PTP_SIGNALING_IGNORED);
    memcpy(message+34,local,10); memcpy(message+20,local,10);
    assert(ptp_signaling_read_capable(message,60,0,local,&output)==PTP_SIGNALING_IGNORED);
    memcpy(message+20,source,10);
    memcpy(message+60,capable,16); message[3]=76;
    assert(ptp_signaling_read_capable(message,76,0,local,&output)==PTP_SIGNALING_MALFORMED);
    message[69]=6; /* Unknown well-formed organization subtype. */
    assert(ptp_signaling_read_capable(message,76,0,local,&output)==PTP_SIGNALING_CAPABLE);
    message[63]=13;
    assert(ptp_signaling_read_capable(message,77,0,local,&output)==PTP_SIGNALING_MALFORMED);
    message[3]=60; message[47]=10;
    assert(ptp_signaling_read_capable(message,60,0,local,&output)==PTP_SIGNALING_MALFORMED);
    puts("Capability TLV bounds, domain, target, source, duplicate, reserved and unknown-TLV tests passed");
}
