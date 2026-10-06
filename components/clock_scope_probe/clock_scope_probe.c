#include <inttypes.h>
#include <limits.h>
#include <time.h>
#include "sdkconfig.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "driver/gpio.h"
#include "driver/gpio_etm.h"
#include "driver/gptimer.h"
#include "driver/gptimer_etm.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "scope_math.h"

extern int ptpd_now(struct timespec *timestamp);
#if CONFIG_IDF_TARGET_ESP32C6
#include "ptp_clock_affine.h"
extern bool scope_capture_local(gptimer_handle_t timer, uint64_t *before,
                                 uint64_t *local_ticks, uint64_t *after);
#endif
#if CONFIG_IDF_TARGET_ESP32P4
#include "esp_ldo_regulator.h"
#include "soc/emac_ptp_struct.h"
extern void scope_capture_register(gptimer_handle_t timer,
    volatile const uint32_t *counter, uint64_t *before, uint32_t *value, uint64_t *after);
#define SCOPE_GPIO 45
static esp_ldo_channel_handle_t output_supply;
#else
#define SCOPE_GPIO 18
#endif

static const char *TAG = "clock_scope";
static gptimer_handle_t pulse_timer;
static TaskHandle_t pulse_task;

typedef struct {
    int64_t ptp_ns;
    uint64_t ticks;
    uint64_t bracket_ticks;
    int32_t rate_ppb;
} scope_anchor_t;

static bool read_anchor(scope_anchor_t *best)
{
    best->bracket_ticks = UINT64_MAX;
    for (unsigned attempt = 0; attempt < 4; ++attempt) {
        uint64_t before, after;
        int64_t clock_ns;
        bool valid;
#if CONFIG_IDF_TARGET_ESP32C6
        /* Keep the clock snapshot stable across the raw timer bracket. */
        vTaskSuspendAll();
        ptp_clock_affine_t mapping = {0};
        bool initialized = ptp_clock_sw_snapshot(&mapping);
        uint64_t ticks;
        valid = scope_capture_local(pulse_timer, &before, &ticks, &after);
        xTaskResumeAll();
        /* Affine arithmetic is outside the hardware sampling bracket. */
        int64_t local_ns = (int64_t)(ticks / 2 * 125 + (ticks & 1) * 62);
        clock_ns = ptp_clock_affine_now(&mapping, local_ns);
        valid = valid && initialized;
#else
        struct timespec api_before, api_after;
        bool api_valid = ptpd_now(&api_before) == 0;
        uint32_t control = EMAC_PTP.timestamp_ctrl.val;
        bool digital = EMAC_PTP.timestamp_ctrl.ts_digit_bin_roll_ctrl;
        uint32_t seconds = EMAC_PTP.sys_seconds.ts_second;
        uint32_t fraction;
        scope_capture_register(pulse_timer, &EMAC_PTP.sys_nanosec.val,
                               &before, &fraction, &after);
        fraction &= 0x7fffffffU;
        uint32_t nanos = digital ? fraction :
            (uint32_t)(((uint64_t)fraction * 1000000000ULL) >> 31);
        valid = control == EMAC_PTP.timestamp_ctrl.val &&
            seconds == EMAC_PTP.sys_seconds.ts_second &&
            EMAC_PTP.timestamp_ctrl.en_timestamp &&
            !EMAC_PTP.timestamp_ctrl.ts_initialize && !EMAC_PTP.timestamp_ctrl.ts_update &&
            nanos < 1000000000U;
        clock_ns = (int64_t)seconds * 1000000000LL + nanos;
        api_valid = api_valid && ptpd_now(&api_after) == 0;
        valid = valid && api_valid &&
            clock_ns >= (int64_t)api_before.tv_sec * 1000000000LL + api_before.tv_nsec &&
            clock_ns <= (int64_t)api_after.tv_sec * 1000000000LL + api_after.tv_nsec;
#endif
        if (!valid || after < before || clock_ns < 0)
            continue;
        if (after - before < best->bracket_ticks) {
            best->ptp_ns = clock_ns;
#if CONFIG_IDF_TARGET_ESP32C6
            best->rate_ppb = mapping.rate_ppb;
#endif
            best->ticks = before + (after - before) / 2;
            best->bracket_ticks = after - before;
        }
    }
    return best->bracket_ticks <= 400; /* At most 10 us. */
}

static bool IRAM_ATTR alarm_notify(gptimer_handle_t timer,
                                  const gptimer_alarm_event_data_t *event,
                                  void *context)
{
    (void)timer;
    (void)event;
    (void)context;
    BaseType_t wake = pdFALSE;
    vTaskNotifyGiveFromISR(pulse_task, &wake);
    return wake == pdTRUE;
}


static void initialize_output(void)
{
#if CONFIG_IDF_TARGET_ESP32P4
    /* Waveshare P4-WIFI6-POE-ETH supplies GPIO45's bank from LDO4. */
    const esp_ldo_channel_config_t supply = {
        .chan_id = 4, .voltage_mv = 3300, .voltage_stable_delay_us = 1000,
    };
    ESP_ERROR_CHECK(esp_ldo_acquire_channel(&supply, &output_supply));
    ESP_LOGI(TAG, "GPIO45 bank supply LDO4 enabled at 3300 mV");
#endif
    gpio_config_t output = {.pin_bit_mask = 1ULL << SCOPE_GPIO,
                            .mode = GPIO_MODE_INPUT_OUTPUT};
    ESP_ERROR_CHECK(gpio_config(&output));
    ESP_ERROR_CHECK(gpio_set_level(SCOPE_GPIO, 0));
    gptimer_config_t timer = {.clk_src = GPTIMER_CLK_SRC_PLL_F80M,
        .direction = GPTIMER_COUNT_UP, .resolution_hz = 40000000};
    ESP_ERROR_CHECK(gptimer_new_timer(&timer, &pulse_timer));
    gptimer_event_callbacks_t callbacks = {.on_alarm = alarm_notify};
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(pulse_timer, &callbacks, NULL));
    esp_etm_event_handle_t event;
    gptimer_etm_event_config_t event_config = {.event_type = GPTIMER_ETM_EVENT_ALARM_MATCH};
    ESP_ERROR_CHECK(gptimer_new_etm_event(pulse_timer, &event_config, &event));
    esp_etm_task_handle_t task;
    gpio_etm_task_config_t task_config = {.action = GPIO_ETM_TASK_ACTION_SET};
    ESP_ERROR_CHECK(gpio_new_etm_task(&task_config, &task));
    ESP_ERROR_CHECK(gpio_etm_task_add_gpio(task, SCOPE_GPIO));
    esp_etm_channel_handle_t channel;
    esp_etm_channel_config_t channel_config = {0};
    ESP_ERROR_CHECK(esp_etm_new_channel(&channel_config, &channel));
    ESP_ERROR_CHECK(esp_etm_channel_connect(channel, event, task));
    ESP_ERROR_CHECK(esp_etm_channel_enable(channel));
    ESP_ERROR_CHECK(gptimer_enable(pulse_timer));
    ESP_ERROR_CHECK(gptimer_start(pulse_timer));
}

static void scope_task(void *context)
{
    (void)context;
    pulse_task = xTaskGetCurrentTaskHandle();
    vTaskDelay(pdMS_TO_TICKS(30000));
    initialize_output();
    ESP_LOGI(TAG, "GPIO%d hardware rising edges, 40 MHz, nominal 1 pulse/s; experimental clock monitor", SCOPE_GPIO);
    scope_anchor_t previous = {0};
    int64_t last_target_ns = -1;
    unsigned sequence = 0;
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(20));
        scope_anchor_t anchor;
        if (!read_anchor(&anchor)) {
            previous.ticks = 0;
            continue;
        }
        int64_t target_ns = (anchor.ptp_ns / 1000000000LL + 1) * 1000000000LL;
        int64_t elapsed_ns = anchor.ptp_ns - previous.ptp_ns;
        int64_t elapsed_ticks = (int64_t)anchor.ticks - (int64_t)previous.ticks;
        uint64_t target_ticks;
        bool ready = previous.ticks && target_ns != last_target_ns &&
#if CONFIG_IDF_TARGET_ESP32C6
            scope_rate_valid(elapsed_ns, elapsed_ticks) &&
            scope_target_affine(target_ns - anchor.ptp_ns, anchor.rate_ppb,
                                anchor.ticks, &target_ticks);
#else
            scope_target_ticks(target_ns - anchor.ptp_ns, elapsed_ns,
                               elapsed_ticks, anchor.ticks, &target_ticks);
#endif
        previous = anchor;
        if (!ready)
            continue;
        uint64_t now_ticks;
        ESP_ERROR_CHECK(gptimer_get_raw_count(pulse_timer, &now_ticks));
        if (target_ticks <= now_ticks + 40000) /* Leave at least 1 ms to arm. */
            continue;
        ulTaskNotifyTake(pdTRUE, 0);
        gptimer_alarm_config_t alarm = {.alarm_count = target_ticks};
        ESP_ERROR_CHECK(gptimer_set_alarm_action(pulse_timer, &alarm));
        last_target_ns = target_ns;
        if (!ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(100))) {
            ESP_ERROR_CHECK(gptimer_set_alarm_action(pulse_timer, NULL));
            gpio_set_level(SCOPE_GPIO, 0);
            ESP_LOGW(TAG, "alarm timeout");
            previous.ticks = 0;
            continue;
        }
        scope_anchor_t post;
        bool post_valid = read_anchor(&post);
        post_valid = post_valid && post.ticks > target_ticks && gpio_get_level(SCOPE_GPIO);
        int64_t edge_error_ns = INT64_MIN;
        if (post_valid) {
            int64_t span_ticks = (int64_t)(post.ticks - anchor.ticks);
            int64_t span_ns = post.ptp_ns - anchor.ptp_ns;
            /* Use the same generous rate gate, with a longer virtual span. */
            post_valid = span_ticks > 0 && span_ticks < 8000000 &&
                span_ns > 0 && span_ns < 200000000 &&
                span_ns - span_ticks * 25 >= -span_ticks * 25 / 1000 &&
                span_ns - span_ticks * 25 <= span_ticks * 25 / 1000;
            if (post_valid)
                edge_error_ns = anchor.ptp_ns +
                    (int64_t)(target_ticks - anchor.ticks) * span_ns / span_ticks - target_ns;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
        ESP_ERROR_CHECK(gpio_set_level(SCOPE_GPIO, 0));
        ESP_LOGI(TAG, "SCOPE_EDGE,%u,%d,%" PRId64 ",%" PRIu64 ",%" PRIu64
                 ",%" PRIu64 ",%" PRId64 ",%" PRId64 ",%" PRId64 ",%d",
                 ++sequence, SCOPE_GPIO, target_ns, target_ticks,
                 anchor.bracket_ticks * 25,
                 post.bracket_ticks == UINT64_MAX ? 0 : post.bracket_ticks * 25,
                 target_ns - anchor.ptp_ns, elapsed_ns - elapsed_ticks * 25,
                 edge_error_ns, post_valid);
        previous.ticks = 0;
    }
}

__attribute__((constructor)) static void start_scope_probe(void)
{
    if (xTaskCreate(scope_task, "clock_scope", 4096, NULL, 4, NULL) != pdPASS)
        ESP_LOGE(TAG, "could not start timing diagnostic");
}
