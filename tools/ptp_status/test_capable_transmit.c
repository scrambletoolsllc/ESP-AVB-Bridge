#include <assert.h>
#include <stdio.h>
#include "ptp_signaling.h"
#include "ptp_capable_schedule.h"
static bool due(ptp_capable_schedule_t *state, bool enabled, int64_t now_us) {
    uint32_t token = ptp_capable_schedule_begin(state, enabled, now_us);
    if (token) assert(ptp_capable_schedule_finish(state, token, true, now_us));
    return token != 0;
}
int main(void)
{
    uint8_t source[10]={1,2,3,4,5,6,7,8,0,2}, wire[64];
    const uint8_t expected[60]={
        0x1c,0x12,0,60,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        1,2,3,4,5,6,7,8,0,2,0xab,0xcd,0,0x7f,
        255,255,255,255,255,255,255,255,255,255,
        0x80,0,0,12,0,0x80,0xc2,0,0,4,0xff,0,0,0,0,0};
    memset(wire,0xaa,sizeof(wire));
    assert(ptp_signaling_write_capable(wire,sizeof(wire),source,3,0xabcd,-1)==60);
    assert(!memcmp(wire,expected,60));assert(wire[60]==0xaa);
    for(unsigned length=0;length<60;length++)
        assert(!ptp_signaling_write_capable(wire,length,source,3,1,0));
    assert(!ptp_signaling_write_capable(wire,64,source,3,1,127));
    uint8_t local[10]={8};ptp_capable_message_t decoded;
    assert(ptp_signaling_read_capable(wire,60,3,local,&decoded)==PTP_SIGNALING_CAPABLE);
    assert(decoded.log_interval==-1 && !memcmp(decoded.source_port,source,10));
    ptp_capable_schedule_t clock={0};
    assert(!due(&clock,false,0));
    assert(due(&clock,true,0));assert(clock.sequence==1);
    assert(!due(&clock,true,999999));
    assert(due(&clock,true,1000000));
    assert(due(&clock,true,2025000));
    assert(clock.next_us==3000000); /* Preserve cadence through modest lateness. */
    assert(due(&clock,true,10000000));
    assert(clock.next_us==11000000); /* No catch-up burst after a stall. */
    assert(!due(&clock,true,10000000));
    assert(!due(&clock,false,10000001));
    assert(due(&clock,true,10000002));
    clock.sequence=UINT16_MAX;clock.active=false;
    assert(due(&clock,true,10000003));assert(clock.sequence==0);
    assert(!due(&clock,true,INT64_MAX));
    puts("Capability TX golden bytes, bounds, cadence, re-enable, stall, sequence wrap and overflow passed");
}
