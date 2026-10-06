#include "driver/gptimer.h"
#include "gptimer_priv.h"
#include "timer_capture.h"

/* Diagnostic compiled inside the timer driver for access to its own lock.
 * Keep the lock overhead outside the measured hardware-read bracket. */
void IRAM_ATTR ftm_probe_sample_register(gptimer_handle_t timer,
                                        volatile const uint32_t *peripheral,
                                        uint64_t *before_ticks,
                                        uint32_t *sample,
                                        uint64_t *after_ticks)
{
    portENTER_CRITICAL_SAFE(&timer->spinlock);
    uint64_t before = clock_capture_timer(&timer->hal);
    uint32_t value = *peripheral;
    uint64_t after = clock_capture_timer(&timer->hal);
    portEXIT_CRITICAL_SAFE(&timer->spinlock);
    *before_ticks = before;
    *sample = value;
    *after_ticks = after;
}
