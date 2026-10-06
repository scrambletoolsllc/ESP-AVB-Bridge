#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "ptp_capable_interval.h"
int main(void) {
    ptp_capable_interval_t state={0};
    assert(ptp_capable_interval_period(&state)==1000000);
    assert(ptp_capable_interval_request(&state,2));
    assert(state.log_interval==2 && state.slowdown_remaining==9);
    for(unsigned index=0;index<9;++index){
        assert(ptp_capable_interval_period(&state)==1000000);
        ptp_capable_interval_sent(&state,2,false);assert(state.slowdown_remaining==9-index);
        ptp_capable_interval_sent(&state,0,true);assert(state.slowdown_remaining==9-index);
        ptp_capable_interval_sent(&state,2,true);
    }
    assert(ptp_capable_interval_period(&state)==4000000);
    assert(ptp_capable_interval_request(&state,-3));assert(ptp_capable_interval_period(&state)==125000);
    assert(ptp_capable_interval_request(&state,1));assert(state.slowdown_remaining==9);
    ptp_capable_interval_sent(&state,1,true);
    assert(ptp_capable_interval_request(&state,1));assert(state.slowdown_remaining==8);
    assert(ptp_capable_interval_request(&state,2));assert(state.slowdown_remaining==9 && state.old_interval_us==125000);
    assert(ptp_capable_interval_request(&state,127));assert(!ptp_capable_interval_period(&state));
    assert(ptp_capable_interval_request(&state,-128));assert(!ptp_capable_interval_period(&state));
    assert(ptp_capable_interval_request(&state,126));assert(ptp_capable_interval_period(&state)==1000000);
    for(int request=-128;request<=127;++request){
        ptp_capable_interval_t trial={0},previous=trial;
        bool expected=(request>=-24 && request<=24)||request==-128||request==126||request==127;
        assert(ptp_capable_interval_request(&trial,request)==expected);
        if(!expected)assert(!memcmp(&trial,&previous,sizeof(trial)));
        /* Faster than the supported maximum rate: closest longer supported interval. */
        if(request>=-24 && request<-3)assert(trial.log_interval==-3 && ptp_capable_interval_period(&trial)==125000);
    }
    assert(ptp_capable_interval_us(24)==INT64_C(16777216000000));
    puts("Capability interval policy: nine accepted notices, failed/stale sends, faster rates, repeated requests, stop/resume and all256 inputs passed");
}
