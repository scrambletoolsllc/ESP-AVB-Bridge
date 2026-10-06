#include <assert.h>
#include "ptp_clock_affine.h"
int main(void)
{
    ptp_clock_affine_t clock = {.local_ns=100, .ptp_ns=123456789, .rate_ppb=50000};
    int64_t local=1000000123;
    int64_t before=ptp_clock_affine_now(&clock,local);
    ptp_clock_affine_adjust_rate(&clock,local,20000);
    assert(ptp_clock_affine_now(&clock,local)==before);
    assert(clock.rate_ppb==70001);
    ptp_clock_affine_reanchor(&clock,local+62,-123);
    assert(ptp_clock_affine_now(&clock,local+62)==before+62-123);
    assert(ptp_clock_rate_correction(INT64_C(86400000000000),100000000)==INT64_C(8640000000000));
    assert(ptp_clock_rate_correction(INT64_C(-86400000000000),100000000)==INT64_C(-8640000000000));
    for (int32_t rate=-1000000;rate<=1000000;rate+=100003) {
        for (int64_t delta=-1000000017;delta<=1000000017;delta+=100000003) {
            __int128 expected=(__int128)delta*rate/1000000000;
            assert(ptp_clock_rate_correction(delta,rate)==expected);
        }
    }
    clock.rate_ppb=100000000;
    ptp_clock_affine_adjust_rate(&clock,local+1000,100000000);
    assert(clock.rate_ppb==100000000);
    return 0;
}
