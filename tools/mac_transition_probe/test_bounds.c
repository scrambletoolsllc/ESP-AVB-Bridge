#include <assert.h>
#include <stdint.h>
#include "transition_bounds.h"

int main(void)
{
    /* An edge late in the final fractional tick must remain admissible. */
    transition_bounds_t bounds = transition_bounds(1, 8, 10);
    double actual_offset = 40.0 - 10.75;
    assert(bounds.lower <= actual_offset && actual_offset <= bounds.upper);
    /* Identical quantized reads still have a one-tick uncertainty. */
    bounds = transition_bounds(1, 10, 10);
    assert(bounds.upper - bounds.lower == 1);
    /* Local timer origin may precede the MAC origin. */
    bounds = transition_bounds(0, 100, 110);
    assert(bounds.lower == -111 && bounds.upper == -100);
    /* Multiplication must not overflow 32 bits near the MAC rollover. */
    bounds = transition_bounds(UINT32_MAX, 100, 110);
    assert(bounds.upper == INT64_C(171798691700));
    return 0;
}
