#include "driver/mcpwm_timer.h"
#include "mcpwm_private.h"

extern uint32_t esp_wifi_internal_get_mac_clock_time(void);

void IRAM_ATTR mac_transition_sample(mcpwm_timer_handle_t timer, uint64_t *before,
                                    uint32_t *first, uint32_t *second,
                                    uint64_t *after)
{
    volatile const uint32_t *counter =
        &timer->group->hal.dev->timer[timer->timer_id].timer_status.val;
    /* Called only by the diagnostic task. */
    portENTER_CRITICAL(&timer->spinlock);
#if CONFIG_MAC_TRANSITION_DIRECT_READ
    /* C6 SDK getter is one load from 0x600ad000, verified in this build. */
    uint32_t before_value, first_value, second_value, after_value;
    volatile const uint32_t *mac_counter = (volatile const uint32_t *)0x600ad000U;
    /* Preload both addresses; keep compiler bookkeeping outside the bracket. */
    __asm__ volatile (
        "lw %[before], 0(%[counter])\n\t"
        "lw %[first], 0(%[mac])\n\t"
        "lw %[second], 0(%[mac])\n\t"
        "lw %[after], 0(%[counter])"
        : [before] "=&r" (before_value), [first] "=&r" (first_value),
          [second] "=&r" (second_value), [after] "=&r" (after_value)
        : [counter] "r" (counter), [mac] "r" (mac_counter)
        : "memory");
#else
    uint32_t before_value = *counter;
    uint32_t first_value = esp_wifi_internal_get_mac_clock_time();
    uint32_t second_value = esp_wifi_internal_get_mac_clock_time();
    uint32_t after_value = *counter;
#endif
    portEXIT_CRITICAL(&timer->spinlock);
    /* Match C6 HAL's next-count correction for fixed UP mode, period 60000. */
    before_value &= 0xffff;
    after_value &= 0xffff;
    *before = before_value ? before_value - 1 : 59999;
    *first = first_value;
    *second = second_value;
    *after = after_value ? after_value - 1 : 59999;
}
