#include <assert.h>
#include <stdio.h>
#include "ptp_signaling.h"

int main(void)
{
    const uint8_t local[10] = {1,2,3,4,5,6,7,8,0,18};
    const uint8_t remote[10] = {8,7,6,5,4,3,2,1,0,1};
    /* Independent wire fixture: message interval request, not capability interval. */
    uint8_t frame[128] = {0x1c,0x12,0,60,0};
    const uint8_t interval[16] = {0,3,0,12,0,0x80,0xc2,0,0,2,128,127,126,7,0,0};
    memcpy(frame+20,remote,10);
    memcpy(frame+34,local,10);
    memcpy(frame+44,interval,16);
    ptp_interval_message_t decoded = {0};
    assert(ptp_signaling_read_message_interval(frame,60,0,local,&decoded)==3);
    assert(decoded.log_link_delay==-128 && decoded.log_sync==127 && decoded.log_announce==126);
    assert(decoded.flags==7 && !memcmp(decoded.source_port,remote,10));
    ptp_interval_message_t saved = decoded;
    for (unsigned received=0; received<60; ++received) {
        assert(ptp_signaling_read_message_interval(frame,received,0,local,&decoded)==-1);
        assert(!memcmp(&decoded,&saved,sizeof(decoded)));
    }
    /* Field interpretation belongs to policy; preserve every signed byte. */
    for (unsigned value=0; value<256; ++value) {
        frame[55]=value;
        assert(ptp_signaling_read_message_interval(frame,60,0,local,&decoded)==3);
        assert((uint8_t)decoded.log_sync==value);
    }
    frame[43]=2;
    assert(ptp_signaling_read_message_interval(frame,60,0,local,&decoded)==0);
    memset(frame+34,255,10);
    assert(ptp_signaling_read_message_interval(frame,60,0,local,&decoded)==3);
    frame[4]=1;
    assert(ptp_signaling_read_message_interval(frame,60,0,local,&decoded)==0);
    frame[4]=0;
    memcpy(frame+20,local,10);
    assert(ptp_signaling_read_message_interval(frame,60,0,local,&decoded)==0);
    memcpy(frame+20,remote,10);
    /* Capability followed by malformed interval must not expose capability. */
    frame[44]=0x80; frame[45]=0; frame[53]=4;
    memcpy(frame+60,interval,16);
    frame[3]=76;
    frame[63]=10;
    ptp_capable_message_t capable = {{0},42};
    ptp_capable_message_t capable_saved = capable;
    assert(ptp_signaling_read_capable(frame,76,0,local,&capable)==-1);
    assert(!memcmp(&capable,&capable_saved,sizeof(capable)));
    frame[63]=12;
    assert(ptp_signaling_read_capable(frame,76,0,local,&capable)==1);
    assert(ptp_signaling_read_message_interval(frame,76,0,local,&decoded)==3);
    /* Duplicates of any known subtype invalidate the entire message. */
    memcpy(frame+76,interval,16);
    frame[3]=92;
    assert(ptp_signaling_read_capable(frame,92,0,local,&capable)==-1);
    assert(ptp_signaling_read_message_interval(frame,92,0,local,&decoded)==-1);
    frame[85]=99;
    assert(ptp_signaling_read_message_interval(frame,92,0,local,&decoded)==3);
    frame[79]=11;
    assert(ptp_signaling_read_message_interval(frame,92,0,local,&decoded)==-1);
    puts("Message interval fields, bounds, identity, mixed TLVs and atomic rejection passed");
}
