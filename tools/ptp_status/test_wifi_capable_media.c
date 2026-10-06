#include <assert.h>
#include <stdio.h>
#include "ptp_wifi_capable.h"
int main(void) {
    ptp_wifi_media_t none = {0};
    assert(ptp_wifi_tm_ftm_support(&none) == 0);
    assert(!ptp_wifi_as_capable(&none, true, 0));
    ptp_wifi_media_t ftm = {.ftm_local = true, .ftm_peer = true};
    assert(ptp_wifi_tm_ftm_support(&ftm) == 2);
    /* FTM without a three- or two-frame grant never qualifies. */
    for (unsigned frames = 0; frames < 256; ++frames) {
        ftm.granted_frames = (uint8_t)frames;
        bool expected = frames == 3 || frames == 2;
        assert(ptp_wifi_as_capable(&ftm, true, 0) == expected);
        assert(ptp_wifi_as_capable(&ftm, true, 1) == expected);
        assert(!ptp_wifi_as_capable(&ftm, false, 0));
    }
    /* Peer without the FTM Extended Capabilities bits, or a local port without FTM. */
    ptp_wifi_media_t half = {.ftm_local = true, .granted_frames = 3};
    assert(ptp_wifi_tm_ftm_support(&half) == 0 && !ptp_wifi_as_capable(&half, true, 0));
    half = (ptp_wifi_media_t){.ftm_peer = true, .granted_frames = 3};
    assert(!ptp_wifi_as_capable(&half, true, 0));
    /* Timing Measurement: neighbor capability, or domain 0 legacy interoperation. */
    ptp_wifi_media_t tm = {.tm_local = true, .tm_peer = true};
    assert(ptp_wifi_tm_ftm_support(&tm) == 1);
    assert(ptp_wifi_as_capable(&tm, true, 5) && ptp_wifi_as_capable(&tm, false, 0));
    assert(!ptp_wifi_as_capable(&tm, false, 1));
    ptp_wifi_media_t both = {.tm_local = true, .tm_peer = true, .ftm_local = true, .ftm_peer = true};
    assert(ptp_wifi_tm_ftm_support(&both) == 3 && ptp_wifi_as_capable(&both, true, 2));
    puts("Wi-Fi media capability: tmFtmSupport bits, FTM grant sizes, neighbor capability and domain 0 legacy cases passed");
}
