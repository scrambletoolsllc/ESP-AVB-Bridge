#include "driver/gptimer.h"
#include "gptimer_priv.h"

extern uint32_t esp_wifi_internal_get_mac_clock_time(void);

/* Compiled inside the driver to keep its lock outside the read bracket. */
void IRAM_ATTR mac_transition_sample(gptimer_handle_t timer, uint64_t *before,
                                    uint32_t *first, uint32_t *second,
                                    uint64_t *after)
{
    portENTER_CRITICAL_SAFE(&timer->spinlock);
    *before = timer_hal_capture_and_get_counter_value(&timer->hal);
    *first = esp_wifi_internal_get_mac_clock_time();
    *second = esp_wifi_internal_get_mac_clock_time();
    *after = timer_hal_capture_and_get_counter_value(&timer->hal);
    portEXIT_CRITICAL_SAFE(&timer->spinlock);
}
