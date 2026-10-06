#include "driver/gptimer.h"
#include "gptimer_priv.h"
#include "../ftm_clock_probe/timer_capture.h"
#if CONFIG_IDF_TARGET_ESP32C6
#include "hal/systimer_ll.h"
#include "soc/systimer_struct.h"

bool scope_capture_local(gptimer_handle_t timer, uint64_t *before,
                         uint64_t *local_ticks, uint64_t *after)
{
    /* C6 is single core. Preserve the shared SYSTIMER latch against ISR reads. */
    portENTER_CRITICAL(&timer->spinlock);
    uint64_t first = clock_capture_timer(&timer->hal);
    systimer_ll_counter_snapshot(&SYSTIMER, 0);
    unsigned attempts = 0;
    while (!systimer_ll_is_counter_value_valid(&SYSTIMER, 0) && ++attempts < 64) {}
    uint64_t last = clock_capture_timer(&timer->hal);
    uint32_t low = systimer_ll_get_counter_value_low(&SYSTIMER, 0);
    uint32_t high = systimer_ll_get_counter_value_high(&SYSTIMER, 0);
    portEXIT_CRITICAL(&timer->spinlock);
    *before = first;
    *after = last;
    *local_ticks = ((uint64_t)high << 32) | low;
    return attempts < 64;
}
#else
void scope_capture_register(gptimer_handle_t timer, volatile const uint32_t *counter,
                            uint64_t *before, uint32_t *value, uint64_t *after)
{
    portENTER_CRITICAL(&timer->spinlock);
    uint64_t first = clock_capture_timer(&timer->hal);
    uint32_t sample = *counter;
    uint64_t last = clock_capture_timer(&timer->hal);
    portEXIT_CRITICAL(&timer->spinlock);
    *before = first;
    *value = sample;
    *after = last;
}
#endif
