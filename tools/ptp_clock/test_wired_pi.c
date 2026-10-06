#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include "ptp_wired_pi.h"

static void simulate(int64_t interval_ns, int32_t oscillator_ppb, double start_ns)
{
    int64_t integral = 0;
    int32_t previous = 0;
    double offset = start_ns, trim = 0, peak = 0;
    unsigned steps = (unsigned)(INT64_C(600000000000) / interval_ns);
    for (unsigned step = 0; step < steps; ++step) {
        int32_t target = ptp_wired_pi_step(&integral, (int64_t)llround(offset), interval_ns);
        int32_t relative = ptp_trim_relative_delta(previous, target);
        trim += relative * (1.0 + trim / 1e9);
        previous = target;
        offset += (oscillator_ppb - trim) * interval_ns / 1e9;
        if (fabs(offset) > peak) peak = fabs(offset);
        assert(isfinite(offset) && fabs(offset) < fabs(start_ns) + 1000000);
    }
    printf("period=%lld ns drift=%d ppb initial=%.0f ns final=%.3f ns peak=%.3f ns\n",
           (long long)interval_ns, oscillator_ppb, start_ns, offset, peak);
    assert(fabs(offset) < 100);
    assert(fabs(trim - oscillator_ppb) < 10);
}

int main(void)
{
    const int64_t intervals[] = {1000000, 15625000, 125000000, 1000000000, 4000000000};
    for (unsigned index = 0; index < sizeof(intervals)/sizeof(intervals[0]); ++index) {
        simulate(intervals[index], 30000, 0);
        simulate(intervals[index], -50000, 1000000);
    }
    int64_t integral = 0;
    assert(ptp_wired_pi_step(&integral, INT64_MAX, 125000000) == PTP_WIRED_TRIM_LIMIT);
    assert(integral == 0);
    assert(ptp_wired_pi_step(&integral, INT64_MIN, 125000000) == -PTP_WIRED_TRIM_LIMIT);
    assert(integral == 0);
    return 0;
}
