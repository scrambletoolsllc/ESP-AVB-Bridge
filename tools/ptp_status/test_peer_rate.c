#include <assert.h>
#include <stdio.h>
#include "ptp_peer_rate.h"

static void encode(uint8_t wire[8], int64_t scaled)
{
    uint64_t value = (uint64_t)scaled;
    for (unsigned index = 0; index < 8; ++index) { wire[7-index] = value; value >>= 8; }
}
int main(void)
{
    ptp_peer_rate_t rate = {0};
    uint8_t responder[10] = {1};
    struct timespec remote = {1000000000, 0}, local = {10, 0};
    assert(!ptp_peer_rate_update(&rate, 1, responder, &remote, .25, &local));
    remote.tv_sec++; remote.tv_nsec = 100000; local.tv_sec++;
    assert(ptp_peer_rate_update(&rate, 1, responder, &remote, .25, &local));
    assert(fabs(rate.ratio-1.0001)<1e-12);
    double delay;
    /* 30 ms turnaround, 500 ns one-way local delay, remote clock +100 ppm. */
    assert(ptp_peer_delay_local(rate.ratio, 30001000, 30003000, 0, 0, &delay));
    assert(fabs(delay-500)<1e-6);
    assert(!ptp_peer_delay_local(1, 30001000, 30003000, 0, 0, &delay));
    assert(ptp_peer_delay_local(.9999, 30001000, 29997000, 0, 0, &delay));
    assert(fabs(delay-500)<1e-6);
    assert(ptp_peer_delay_local(1, 4000, 2000, .25, .75, &delay));
    assert(fabs(delay-999.75)<1e-9);
    assert(!ptp_peer_delay_local(NAN, 4000, 2000, 0, 0, &delay));
    assert(!ptp_peer_delay_local(1, -1, 2000, 0, 0, &delay));
    assert(!ptp_peer_rate_update(&rate, 2, responder, &remote, 0, &local));
    remote.tv_sec++; local.tv_sec++;
    assert(ptp_peer_rate_update(&rate, 2, responder, &remote, 0, &local));
    responder[9]++;
    assert(!ptp_peer_rate_update(&rate, 2, responder, &remote, 0, &local));
    remote.tv_sec += 20; local.tv_sec += 20;
    assert(!ptp_peer_rate_update(&rate, 2, responder, &remote, 0, &local));
    remote.tv_sec++; local.tv_sec++;
    assert(ptp_peer_rate_update(&rate, 2, responder, &remote, 0, &local));
    assert(!ptp_peer_rate_update(&rate, 2, responder, &remote, 0, &local));
    remote.tv_sec++; local.tv_sec += 2;
    assert(!ptp_peer_rate_update(&rate, 2, responder, &remote, 0, &local));
    uint8_t correction[8];
    encode(correction, 16384); assert(ptp_peer_correction(correction)==.25);
    encode(correction, -49152); assert(ptp_peer_correction(correction)==-.75);
    puts("Peer rate handles unrelated epochs, +/-100ppm, fractional corrections, identity/lifecycle changes, gaps and invalid rates");
}
