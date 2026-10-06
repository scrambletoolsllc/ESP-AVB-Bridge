#include <inttypes.h>
#include <limits.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_private/wifi.h"
#include "driver/gptimer.h"
#include "driver/mcpwm_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "transition_bounds.h"

#if CONFIG_MAC_TRANSITION_MCPWM
typedef mcpwm_timer_handle_t probe_timer_t;
#else
typedef gptimer_handle_t probe_timer_t;
#endif
extern void mac_transition_sample(probe_timer_t timer, uint64_t *before,
                                  uint32_t *first, uint32_t *second,
                                  uint64_t *after);

static const char *TAG = "mac_transition";

static void probe_task(void *context)
{
    (void)context;
    vTaskDelay(pdMS_TO_TICKS(30000));
#if CONFIG_MAC_TRANSITION_DIRECT_READ
    for (unsigned check = 0; check < 16; ++check) {
        uint32_t before = esp_wifi_internal_get_mac_clock_time();
        uint32_t direct = *(volatile const uint32_t *)0x600ad000U;
        uint32_t after = esp_wifi_internal_get_mac_clock_time();
        if (after < before || direct < before || direct > after) {
            ESP_LOGE(TAG, "direct MAC register failed API bracket check");
            vTaskDelete(NULL);
            return;
        }
    }
    ESP_LOGI(TAG, "MAC_TRANSITION_READ,DIRECT,API_bracket_check_passed");
#else
    ESP_LOGI(TAG, "MAC_TRANSITION_READ,API");
#endif
    probe_timer_t timer;
#if CONFIG_MAC_TRANSITION_MCPWM
    const mcpwm_timer_config_t config = {
        .group_id = 0, .clk_src = MCPWM_TIMER_CLK_SRC_DEFAULT,
        .resolution_hz = 40000000, .count_mode = MCPWM_TIMER_COUNT_MODE_UP,
        .period_ticks = 60000,
    };
    esp_err_t status = mcpwm_new_timer(&config, &timer);
#else
    const gptimer_config_t config = {
        .clk_src = GPTIMER_CLK_SRC_PLL_F80M,
        .direction = GPTIMER_COUNT_UP, .resolution_hz = 40000000,
    };
    esp_err_t status = gptimer_new_timer(&config, &timer);
#endif
    if (status != ESP_OK) {
        ESP_LOGE(TAG, "timer unavailable: %s", esp_err_to_name(status));
        vTaskDelete(NULL);
        return;
    }
#if CONFIG_MAC_TRANSITION_MCPWM
    ESP_ERROR_CHECK(mcpwm_timer_enable(timer));
    ESP_ERROR_CHECK(mcpwm_timer_start_stop(timer, MCPWM_TIMER_START_NO_STOP));
    ESP_LOGI(TAG, "MAC_TRANSITION_MODE,MCPWM,phase_modulo_60000_ticks");
    int64_t phase_reference = INT64_MIN;
#else
    ESP_ERROR_CHECK(gptimer_enable(timer));
    ESP_ERROR_CHECK(gptimer_start(timer));
    ESP_LOGI(TAG, "MAC_TRANSITION_MODE,GPTIMER,absolute_offset_ticks");
#endif
    ESP_LOGI(TAG, "MAC_TRANSITION_BEGIN,40MHz,1024 train+1024 heldout attempts,25ns/tick");
    uint32_t previous_mac = 0;
    bool have_previous_mac = false;
    bool discontinuity = false;
    uint32_t phase_state = 0x9e3779b9U;
    ESP_LOGI(TAG, "MAC_TRANSITION_DITHER,0_to_31_iterations,outside_read_bracket");
    for (unsigned round = 0; round < 120; ++round) {
        int64_t lower = INT64_MIN, upper = INT64_MAX;
        int64_t held_lower = INT64_MIN, held_upper = INT64_MAX;
        uint64_t width_min = UINT64_MAX, width_max = 0;
        unsigned train = 0, held = 0, invalid = 0, unchanged = 0;
        unsigned violations = 0;
        int64_t miss_max = 0;
        int64_t started = esp_timer_get_time();
        for (unsigned attempt = 0; attempt < 2048; ++attempt) {
            /* Avoid sampling the same phase of the microsecond divider. */
            phase_state ^= phase_state << 13;
            phase_state ^= phase_state >> 17;
            phase_state ^= phase_state << 5;
            uint64_t before, after;
            uint32_t first, second;
            int64_t wall_before = esp_timer_get_time();
            for (unsigned delay = phase_state & 31; delay; --delay)
                __asm__ volatile ("nop");
            mac_transition_sample(timer, &before, &first, &second, &after);
            int64_t wall_after = esp_timer_get_time();
            if (second < first || (have_previous_mac && first < previous_mac)) {
                discontinuity = true;
                break;
            }
            previous_mac = second;
            have_previous_mac = true;
            if (wall_after < wall_before || wall_after - wall_before > 100 ||
                after < before || after - before > 400 ||
                second - first > 1) {
                ++invalid;
            } else if (second == first) {
                ++unchanged;
            } else {
                transition_bounds_t bounds = transition_bounds(second, before, after);
                int64_t sample_lower = bounds.lower;
                int64_t sample_upper = bounds.upper;
#if CONFIG_MAC_TRANSITION_MCPWM
                if (phase_reference == INT64_MIN) phase_reference = sample_lower % 60000;
                int64_t relative = (sample_lower - phase_reference + 30000) % 60000;
                if (relative < 0) relative += 60000;
                sample_lower = phase_reference + relative - 30000;
                sample_upper = sample_lower + (int64_t)(after - before) + 1;
#endif
                uint64_t width = after - before;
                if (width < width_min) width_min = width;
                if (width > width_max) width_max = width;
                if (attempt < 1024) {
                    ++train;
                    if (sample_lower > lower) lower = sample_lower;
                    if (sample_upper < upper) upper = sample_upper;
                } else {
                    ++held;
                    if (sample_lower > held_lower) held_lower = sample_lower;
                    if (sample_upper < held_upper) held_upper = sample_upper;
                    if (train && lower <= upper) {
                        int64_t midpoint = lower + (upper - lower) / 2;
                        int64_t miss = midpoint < sample_lower ? sample_lower - midpoint :
                                       midpoint > sample_upper ? midpoint - sample_upper : 0;
                        if (miss) ++violations;
                        if (miss > miss_max) miss_max = miss;
                    }
                }
            }
            /* Never wait for a transition with interrupts masked. */
            if ((attempt & 15) == 15) vTaskDelay(1);
        }
        if (discontinuity) break;
        ESP_LOGI(TAG, "MAC_TRANSITION,%u,%" PRId64 ",%" PRId64 ",%u,%u,%u,%u,%"
                 PRId64 ",%" PRId64 ",%" PRId64 ",%" PRId64 ",%u,%" PRId64
                 ",%" PRIu64 ",%" PRIu64,
                 round, started, esp_timer_get_time() - started, train, held,
                 invalid, unchanged, lower, upper, held_lower, held_upper,
                 violations, miss_max, width_min, width_max);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
#if CONFIG_MAC_TRANSITION_MCPWM
    ESP_ERROR_CHECK(mcpwm_timer_start_stop(timer, MCPWM_TIMER_STOP_EMPTY));
    vTaskDelay(1);
    ESP_ERROR_CHECK(mcpwm_timer_disable(timer));
    ESP_ERROR_CHECK(mcpwm_del_timer(timer));
#else
    ESP_ERROR_CHECK(gptimer_stop(timer));
    ESP_ERROR_CHECK(gptimer_disable(timer));
    ESP_ERROR_CHECK(gptimer_del_timer(timer));
#endif
    ESP_LOGI(TAG, "%s", discontinuity ? "MAC_TRANSITION_ABORT,counter_discontinuity" : "MAC_TRANSITION_END");
    vTaskDelete(NULL);
}

__attribute__((constructor)) static void start_probe(void)
{
    if (xTaskCreate(probe_task, "mac_transition", 4096, NULL, 3, NULL) != pdPASS)
        ESP_LOGE(TAG, "could not start transition diagnostic");
}
