#include <assert.h>
#include <stdio.h>
#include "ptp_signaling.h"
int main(void) {
    uint8_t source[10]={2,3,4,5,6,7,8,9,0,2};
    uint8_t local[10]={8,7,6,5,4,3,2,1,0,1};
    uint8_t wire[128],original[128];
    const uint8_t expected[58]={
        0x1c,0x12,0,58,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        2,3,4,5,6,7,8,9,0,2,0xab,0xcd,0,0x7f,
        255,255,255,255,255,255,255,255,255,255,
        0x80,0,0,10,0,0x80,0xc2,0,0,5,127,0,0,0};
    memset(wire,0xa5,sizeof(wire));
    assert(ptp_signaling_write_capable_interval(wire,sizeof(wire),source,3,0xabcd,127)==58);
    assert(!memcmp(wire,expected,58));
    for(unsigned index=58;index<sizeof(wire);++index)assert(wire[index]==0xa5);
    ptp_capable_message_t result={0};
    assert(ptp_signaling_read_capable_interval(wire,58,3,local,&result)==PTP_SIGNALING_CAPABLE_INTERVAL);
    assert(result.log_interval==127 && !memcmp(result.source_port,source,10));
    assert(ptp_signaling_read_capable(wire,58,3,local,&result)==PTP_SIGNALING_IGNORED);
    for(unsigned length=0;length<58;++length)
        assert(ptp_signaling_read_capable_interval(wire,length,3,local,&result)==PTP_SIGNALING_MALFORMED);
    memcpy(original,wire,sizeof(wire));
    for(int value=-128;value<=127;++value){
        bool allowed=(value>=-24 && value<=24)||value==-128||value==126||value==127;
        assert((ptp_signaling_write_capable_interval(wire,sizeof(wire),source,3,1,value)==58)==allowed);
        if(allowed){assert(ptp_signaling_read_capable_interval(wire,58,3,local,&result)==2);assert(result.log_interval==value);}
    }
    memcpy(wire,original,sizeof(wire));memset(wire+55,0x55,3);
    assert(ptp_signaling_read_capable_interval(wire,58,3,local,&result)==2);
    wire[3]=72;memcpy(wire+58,wire+44,14);
    assert(ptp_signaling_read_capable_interval(wire,72,3,local,&result)==-1);
    memcpy(wire,original,sizeof(wire));wire[47]=11;
    assert(ptp_signaling_read_capable_interval(wire,58,3,local,&result)==-1);
    memcpy(wire,original,sizeof(wire));memcpy(wire+34,local,10);
    assert(ptp_signaling_read_capable_interval(wire,58,3,local,&result)==2);
    wire[43]++;
    assert(ptp_signaling_read_capable_interval(wire,58,3,local,&result)==0);
    memcpy(wire,original,sizeof(wire));memcpy(wire+20,local,8);
    assert(ptp_signaling_read_capable_interval(wire,58,3,local,&result)==0);
    memcpy(wire,original,sizeof(wire));
    assert(!ptp_signaling_write_capable_interval(wire,57,source,3,0,0));
    assert(!memcmp(wire,original,sizeof(wire)));
    puts("Capability interval request golden wire, all256 encodings, truncation, duplicates, reserved bytes, source and target passed");
}
