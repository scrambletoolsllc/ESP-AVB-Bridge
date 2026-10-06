#include <assert.h>
#include "ptp_ftm_counter.h"

int main(void)
{
    const uint64_t period = UINT64_C(1) << 48;
    const uint64_t second = UINT64_C(1000000000000);
    assert(!ptp_ftm_counter_backward(UINT64_C(281317135057221),
                                     UINT64_C(349504946565)));
    assert(!ptp_ftm_counter_backward(period - second, second));
    assert(!ptp_ftm_counter_backward(period - 1, 0));
    assert(!ptp_ftm_counter_backward(0, second));
    assert(ptp_ftm_counter_backward(10 * second, second));
    assert(!ptp_ftm_counter_backward(10 * second, 10 * second - 1));
    assert(ptp_ftm_counter_backward(second, period - second));
    assert(!ptp_ftm_counter_backward(0, period - second));
    assert(ptp_ftm_counter_backward(3 * second, period - second));
    assert(!ptp_ftm_counter_backward(0, period / 2));
    assert(!ptp_ftm_counter_backward(period, 0));
    return 0;
}
