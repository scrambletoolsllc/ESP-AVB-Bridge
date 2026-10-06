#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "ptp_announce_schedule.h"

static uint32_t begin(ptp_announce_schedule_t *state,int64_t now,int8_t expected)
{
    int8_t advertised=99;uint16_t sequence=0;
    uint32_t token=ptp_announce_begin(state,0,state->revision,1,now,&advertised,&sequence);
    assert(token && advertised==expected && sequence==state->sequence);
    return token;
}
int main(void)
{
    ptp_announce_schedule_t state={0};
    uint32_t token=begin(&state,0,0);
    assert(ptp_announce_finish(&state,token,true,0));
    assert(ptp_announce_request(&state,0,2));
    assert(state.slowdown_remaining==3 && state.old_period_us==1000000);
    uint32_t revision=state.revision;
    token=begin(&state,100000,2);
    assert(ptp_announce_finish(&state,token,false,100000));
    assert(state.slowdown_remaining==3);
    int8_t advertised;uint16_t sequence;
    assert(!ptp_announce_begin(&state,0,revision,1,100001,&advertised,&sequence));
    token=begin(&state,1100000,2);assert(ptp_announce_finish(&state,token,true,1100000));
    assert(state.slowdown_remaining==2);
    assert(ptp_announce_request(&state,0,2) && state.slowdown_remaining==2 && state.revision==revision);
    token=begin(&state,2100000,2);assert(ptp_announce_finish(&state,token,true,2100000));
    assert(state.slowdown_remaining==1);
    token=begin(&state,3100000,2);assert(ptp_announce_finish(&state,token,true,3100000));
    assert(!state.slowdown_remaining && state.next_us==7100000);
    assert(!ptp_announce_begin(&state,0,revision,1,7100000-1,&advertised,&sequence));
    token=begin(&state,7100000,2);assert(ptp_announce_finish(&state,token,true,7100000));
    /* Source/path changes bypass the period, with independent sequence continuity. */
    uint16_t previous_sequence=state.sequence;
    token=ptp_announce_begin(&state,0,revision,2,7200000,&advertised,&sequence);
    assert(token && sequence==(uint16_t)(previous_sequence+1));
    assert(ptp_announce_finish(&state,token,true,7200000));
    /* Stop and reset retire queued policy and stale completion tokens. */
    assert(ptp_announce_request(&state,0,127));
    assert(!ptp_announce_begin(&state,0,state.revision,3,7300000,&advertised,&sequence));
    assert(ptp_announce_request(&state,0,-128) && state.log_interval==127);
    assert(ptp_announce_request(&state,0,126) && state.log_interval==0);
    assert(!ptp_announce_begin(&state,0,revision,3,7400000,&advertised,&sequence));
    token=begin(&state,7500000,0);
    assert(ptp_announce_request(&state,0,1));
    assert(!ptp_announce_finish(&state,token,true,7500001));
    assert(state.slowdown_remaining==3);
    /* Every reserved value leaves state unchanged; faster requests map to base. */
    for (int request=-128;request<=127;++request) {
        ptp_announce_schedule_t candidate={0};
        bool expected=request==-128 || request==126 || request==127 || (request>=-24 && request<=24);
        assert(ptp_announce_request(&candidate,0,request)==expected);
        if (!expected) {ptp_announce_schedule_t empty={0};assert(!memcmp(&candidate,&empty,sizeof(empty)));}
        else if (request>=-24 && request<=24) assert(candidate.log_interval==(request<0?0:request));
    }
    ptp_announce_schedule_t changed={0};uint32_t stale=begin(&changed,0,0);
    token=ptp_announce_begin(&changed,0,0,2,1,&advertised,&sequence);
    assert(token && token!=stale);
    assert(!ptp_announce_finish(&changed,stale,true,2));
    assert(ptp_announce_finish(&changed,token,true,2));
    ptp_announce_schedule_t configured={0};
    assert(ptp_announce_request(&configured,2,-1) && configured.log_interval==2);
    assert(ptp_announce_request(&configured,2,3) && configured.log_interval==3);
    assert(ptp_announce_request(&configured,2,126) && configured.log_interval==2);
    assert(ptp_announce_period_us(-3)==125000 && ptp_announce_period_us(-24)==1);
    ptp_announce_schedule_t maximum={0};assert(ptp_announce_request(&maximum,0,24));
    maximum.slowdown_remaining=0;
    assert(!ptp_announce_begin(&maximum,0,maximum.revision,1,INT64_MAX,&advertised,&sequence));
    assert(!ptp_announce_begin(&maximum,0,maximum.revision,1,-1,&advertised,&sequence));
    state=(ptp_announce_schedule_t){0};token=begin(&state,0,0);
    assert(!ptp_announce_finish(&state,token,true,1000000));
    state.serial=UINT32_MAX;state.sequence=UINT16_MAX;
    token=begin(&state,1000000,0);assert(token==1 && state.sequence==0);
    assert(ptp_announce_finish(&state,token,true,1000000));
    token=begin(&state,2000000,0);
    state.revision=UINT32_MAX;
    previous_sequence=state.sequence;
    ptp_announce_reset(&state);
    assert(state.revision==1 && !state.pending && !state.initialized);
    assert(state.sequence==previous_sequence && state.serial==token);
    assert(!ptp_announce_finish(&state,token,true,2000001));
    assert(!ptp_announce_begin(&state,0,UINT32_MAX,1,2000001,&advertised,&sequence));
    uint32_t replacement=begin(&state,2000001,0);
    assert(replacement!=token && state.sequence==(uint16_t)(previous_sequence+1));
    assert(!ptp_announce_finish(&state,token,true,2000002));
    assert(ptp_announce_finish(&state,replacement,true,2000002));
    puts("Announce scheduling: 3 accepted old-rate messages, deadlines, stop/reset, source changes, stale work, all256 requests and wrap passed");
}
