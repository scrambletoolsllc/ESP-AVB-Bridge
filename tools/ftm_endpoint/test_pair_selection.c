#include <assert.h>
#include <stdio.h>
#include "ftm_pair_selection.h"
int main(void) {
    ftm_pair_selection_t selection;
    /* Distinct direction minima, with a remote counter wrap and a large
     * unrelated local epoch. Entries have forward/reverse excesses
     * 0/5000, -2000/9000, 1000/1000 ps respectively. */
    uint64_t mask = (UINT64_C(1) << 48) - 1;
    uint64_t remote = mask - 500, local = UINT64_C(800000000000000);
    ftm_pair_selection_init(&selection);
    assert(ftm_pair_selection_add(&selection, 0, remote, local,
        local + 10000, (remote + 15000) & mask, remote, local, 1));
    assert(ftm_pair_selection_add(&selection, 1, (remote + 100000) & mask,
        local + 98000, local + 108000, (remote + 117000) & mask,
        remote, local, 1));
    assert(ftm_pair_selection_add(&selection, 2, (remote + 200000) & mask,
        local + 201000, local + 211000, (remote + 212000) & mask,
        remote, local, 1));
    assert(selection.forward == 1 && selection.reverse == 2);
    assert(selection.forward_ps == -2000 && selection.reverse_ps == 1000);
    assert(!ftm_pair_selection_add(&selection, 3, remote, local - 1,
        local + 1, remote, remote, local, 1));
    assert(!ftm_pair_selection_add(&selection, 3, remote, local,
        local + 1, remote, remote, local, NAN));
    ftm_pair_selection_init(&selection);
    /* A 100 ppm remote/local rate difference is removed before ranking. */
    assert(ftm_pair_selection_add(&selection, 0, 100, 200,
        10200, 11101, 100, 200, 1.0001));
    assert(fabs(selection.forward_ps) < .001);
    assert(fabs(selection.reverse_ps - 1000) < .001);
    puts("Independent direction minima, signed delay, epoch, wrap and rate tests passed");
}
