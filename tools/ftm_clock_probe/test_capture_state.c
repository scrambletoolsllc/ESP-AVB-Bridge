#include <assert.h>
#include "edge_capture_state.h"

int main(void)
{
    edge_capture_state_t state = {0};
    assert(!edge_capture_record(&state, 1));
    assert(edge_capture_arm(&state, 10, 1, 100));
    assert(!edge_capture_record(&state, 100));
    assert(state.armed);
    assert(edge_capture_record(&state, 110));
    assert(state.captured && !state.armed);
    assert(edge_capture_arm(&state, 10, 1, 110));
    assert(state.captured && !state.armed);
    assert(!edge_capture_record(&state, 120));
    assert(state.fault && !state.captured);
    assert(!edge_capture_arm(&state, 10, 1, 120));
    assert(edge_capture_arm(&state, 10, 2, 120));
    assert(!edge_capture_arm(&state, 10, 1, 120));
    assert(state.sequence == 2);
    assert(edge_capture_arm(&state, 11, 1, 120));
    assert(state.host_boot == 11 && state.sequence == 1);
    assert(!edge_capture_arm(&state, 11, 0, 120));
    assert(edge_capture_record(&state, 130));
    return 0;
}
