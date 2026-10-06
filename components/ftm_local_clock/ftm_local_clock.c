#include <inttypes.h>
#include <limits.h>
#include "ftm_local_clock.h"
#include "esp_timer_impl.h"
#include "esp_private/wifi.h"
#include "esp_log.h"
#include "hal/systimer_ll.h"
#include "soc/systimer_struct.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static portMUX_TYPE mapping_lock = portMUX_INITIALIZER_UNLOCKED;
static ftm_local_clock_snapshot_t current;
static portMUX_TYPE sample_lock = portMUX_INITIALIZER_UNLOCKED;

static bool sample_local(uint32_t *first, uint64_t *ticks, uint32_t *second)
{
    /* Single-core C6: exclude ISR readers until the shared latch is copied.
     * Only the snapshot strobe/ack belong inside the MAC read bracket. */
    portENTER_CRITICAL(&sample_lock);
    *first = esp_wifi_internal_get_mac_clock_time();
    systimer_ll_counter_snapshot(&SYSTIMER, 0);
    unsigned attempts = 0;
    while (!systimer_ll_is_counter_value_valid(&SYSTIMER, 0) && ++attempts < 64) {}
    *second = esp_wifi_internal_get_mac_clock_time();
    uint32_t low = systimer_ll_get_counter_value_low(&SYSTIMER, 0);
    uint32_t high = systimer_ll_get_counter_value_high(&SYSTIMER, 0);
    portEXIT_CRITICAL(&sample_lock);
    *ticks = ((uint64_t)high << 32) | low;
    return attempts < 64;
}

static int64_t local_now(void)
{
    uint64_t ticks = esp_timer_impl_get_counter_reg();
    return (int64_t)(ticks / 2 * 125 + (ticks & 1) * 62);
}

bool ftm_local_clock_snapshot(ftm_local_clock_snapshot_t *snapshot)
{
    if (!snapshot) return false;
    portENTER_CRITICAL(&mapping_lock);
    *snapshot = current;
    portEXIT_CRITICAL(&mapping_lock);
    int64_t now = local_now();
    if (now < snapshot->refreshed_ns || now - snapshot->refreshed_ns > 1000000000)
        snapshot->valid = false;
    return snapshot->valid;
}

static void mapping_task(void *argument)
{
    (void)argument;
    vTaskDelay(pdMS_TO_TICKS(10000));
    uint32_t generation = 1, phase = 0x9e3779b9;
    int64_t previous_offset = 0;
    bool previous_valid = false;
    unsigned round = 0;
    for (;;) {
        uint32_t anchor_mac = 0;
        int64_t anchor_local = 0, lower = INT64_MIN, upper = INT64_MAX;
        int64_t held_lower = INT64_MIN, held_upper = INT64_MAX;
        unsigned transitions = 0, held = 0, rejected = 0;
        for (unsigned attempt = 0; attempt < 256; ++attempt) {
            phase ^= phase << 13; phase ^= phase >> 17; phase ^= phase << 5;
            for (unsigned delay = phase & 31; delay; --delay) __asm__ volatile ("nop");
            uint32_t first, second;
            uint64_t ticks;
            bool captured = sample_local(&first, &ticks, &second);
            int64_t local = (int64_t)(ticks / 2 * 125 + (ticks & 1) * 62);
            uint32_t span = second - first;
            if (!captured || span > 2) {
                ++rejected;
                continue;
            }
            if (!transitions) { anchor_mac = first; anchor_local = local; }
            uint32_t delta = first - anchor_mac;
            if (delta > 1000000) { ++rejected; continue; }
            /* The local snapshot lies inside these coarse MAC reads.
             * Include both counters' quantization in the offset bounds. */
            int64_t sample_lower = local - anchor_local - ((int64_t)delta + span + 1) * 1000;
            int64_t sample_upper = local + 63 - anchor_local - (int64_t)delta * 1000;
            if (attempt < 128) {
                if (sample_lower > lower) lower = sample_lower;
                if (sample_upper < upper) upper = sample_upper;
                ++transitions;
            } else {
                if (sample_lower > held_lower) held_lower = sample_lower;
                if (sample_upper < held_upper) held_upper = sample_upper;
                ++held;
            }
        }
        int64_t midpoint = 0;
        bool valid = transitions >= 8 && held >= 8 && lower <= upper && upper - lower <= 1000;
        if (valid) {
            midpoint = lower + (upper - lower) / 2;
            valid = midpoint >= held_lower && midpoint <= held_upper;
        }
        ftm_local_clock_snapshot_t next = {.generation = generation,
            .mac_us = anchor_mac, .local_ns = anchor_local + midpoint,
            .refreshed_ns = local_now(), .valid = valid};
        if (valid) {
            next.uncertainty_ns = (uint32_t)((upper - lower + 1) / 2);
            /* Compare modulo the MAC's 32-bit microsecond wrap. */
            int64_t offset = next.local_ns - (int64_t)anchor_mac * 1000;
            int64_t innovation = offset - previous_offset;
            if (innovation > INT64_C(2147483648000)) innovation -= INT64_C(4294967296000);
            if (innovation < -INT64_C(2147483648000)) innovation += INT64_C(4294967296000);
            if (previous_valid && (innovation < -2000 || innovation > 2000)) ++generation;
            previous_offset = offset;
        } else if (previous_valid) {
            ++generation;
        }
        previous_valid = valid;
        next.generation = generation;
        portENTER_CRITICAL(&mapping_lock);
        current = next;
        portEXIT_CRITICAL(&mapping_lock);
        if (!(round++ % 10) || !valid)
            ESP_LOGI("ftm_local_clock", "FTMLOCAL,%u,%u,%u,%" PRIu32 ",%" PRId64
                     ",%" PRId64 ",%" PRId64 ",%u,%u,%u,%" PRId64 ",%" PRId64,
                     round, generation, valid, anchor_mac, anchor_local,
                     lower, upper, transitions, held, rejected, held_lower, held_upper);
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

__attribute__((constructor)) static void initialize_mapping(void)
{
    if (xTaskCreate(mapping_task, "ftm_local", 3072, NULL, 2, NULL) != pdPASS)
        ESP_LOGE("ftm_local_clock", "could not start mapping");
}
