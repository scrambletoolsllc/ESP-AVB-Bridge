#pragma once
#include "hal/timer_ll.h"

/* Same latch operation as the HAL, inlined inside the driver's lock. */
static inline __attribute__((always_inline)) uint64_t clock_capture_timer(timer_hal_context_t *timer)
{
    timer_ll_trigger_soft_capture(timer->dev, timer->timer_id);
    return timer_ll_get_counter_value(timer->dev, timer->timer_id);
}
