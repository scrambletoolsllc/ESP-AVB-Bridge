#include <assert.h>
#include "ptp_ftm_session.h"
#include "ptp_ftm_rtt.h"

int main(void)
{
    assert(!ptp_ftm_rtt_positive(0));
    assert(!ptp_ftm_rtt_positive(UINT32_MAX));
    assert(!ptp_ftm_rtt_positive(UINT32_C(4294965733))); /* -1563 ps */
    assert(!ptp_ftm_rtt_positive(UINT32_C(0x80000000)));
    assert(ptp_ftm_rtt_positive(1));
    assert(ptp_ftm_rtt_positive(4086));
    assert(ptp_ftm_rtt_positive(INT32_MAX));
    const uint8_t peer[6] = {0xd8,0x85,0xac,0xfa,0x2c,0x59};
    const uint8_t other[6] = {1,2,3,4,5,6};
    ptp_ftm_session_t session = {0};
    assert(ptp_ftm_beacon_fresh(true, true, 100, 200, 300));
    assert(ptp_ftm_beacon_fresh(true, true, 100, 200, 1000200));
    assert(!ptp_ftm_beacon_fresh(true, true, 100, 200, 1000201));
    assert(!ptp_ftm_beacon_fresh(true, true, 300, 200, 400));
    assert(!ptp_ftm_beacon_fresh(true, true, 100, 400, 300));
    assert(!ptp_ftm_beacon_fresh(true, true, 0, 200, 300));
    assert(!ptp_ftm_beacon_fresh(false, true, 100, 200, 300));
    assert(!ptp_ftm_beacon_fresh(true, false, 100, 200, 300));
    assert(!ptp_ftm_session_finish(&session, peer, true));
    assert(ptp_ftm_session_begin(&session, peer));
    assert(!ptp_ftm_session_begin(&session, peer));
    assert(ptp_ftm_session_finish(&session, peer, true));
    assert(!ptp_ftm_session_finish(&session, peer, true));

    /* Reassociation to the same peer cannot revive a canceled exchange. */
    assert(ptp_ftm_session_begin(&session, peer));
    ptp_ftm_session_invalidate(&session);
    assert(!ptp_ftm_session_begin(&session, peer));
    assert(!ptp_ftm_session_finish(&session, peer, true));
    assert(ptp_ftm_session_begin(&session, peer));
    assert(ptp_ftm_session_finish(&session, peer, true));

    assert(ptp_ftm_session_begin(&session, peer));
    assert(!ptp_ftm_session_finish(&session, peer, false));
    assert(ptp_ftm_session_begin(&session, peer));
    assert(!ptp_ftm_session_finish(&session, other, true));
    return 0;
}
