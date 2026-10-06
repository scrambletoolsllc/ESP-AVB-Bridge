#include <inttypes.h>
#include <string.h>
#include "esp_event.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_private/wifi.h"
#if CONFIG_FTM_LIVE_MODEL
#include "ftm_raw_probe.h"
#endif
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#define ENTRY_LIMIT 16
#define QUEUE_LENGTH 4

typedef struct {
    uint32_t generation, attempt, dropped;
    uint8_t peer[6];
    int64_t before_us, after_us;
    uint32_t mac_us;
    uint8_t count;
    wifi_ftm_report_entry_t entries[ENTRY_LIMIT];
} probe_report_t;

static QueueHandle_t report_queue;
static portMUX_TYPE state_lock = portMUX_INITIALIZER_UNLOCKED;
static uint32_t generation = 1, attempt, dropped;
static uint8_t peer[6];
static bool ready, capture_busy;
static probe_report_t capture_buffer;
static const char *TAG = "ftm_raw";
#if CONFIG_FTM_LIVE_MODEL
static ftm_model_t clock_model;
static ftm_model_report_t model_input;
static ftm_model_snapshot_t published_model;
#if CONFIG_FTM_LIVE_MODEL_SELF_TEST
static int64_t first_report_us;
static unsigned input_pause_state;
static bool rejoin_requested;
#endif

bool ftm_raw_model_snapshot(ftm_model_snapshot_t *snapshot)
{
    int64_t now_us = esp_timer_get_time();
    portENTER_CRITICAL(&state_lock);
    *snapshot = published_model;
    snapshot->valid = snapshot->valid && snapshot->generation == generation &&
        now_us >= snapshot->updated_us && now_us - snapshot->updated_us <= 2000000;
    portEXIT_CRITICAL(&state_lock);
    return snapshot->valid;
}

static void evaluate_model(const probe_report_t *report)
{
    int64_t started_us = esp_timer_get_time();
    model_input.generation = report->generation;
    model_input.attempt = report->attempt;
    model_input.dropped = report->dropped;
    model_input.mac_us = report->mac_us;
    model_input.before_us = report->before_us;
    model_input.after_us = report->after_us;
    model_input.count = report->count;
    memcpy(model_input.peer, report->peer, 6);
    for (unsigned index = 0; index < report->count; ++index) {
        const wifi_ftm_report_entry_t *entry = &report->entries[index];
        model_input.entries[index] = (ftm_model_entry_t){
            .t1=entry->t1, .t2=entry->t2, .t3=entry->t3, .t4=entry->t4, .rtt=entry->rtt};
    }
    portENTER_CRITICAL(&state_lock);
    uint32_t current_generation = generation;
    portEXIT_CRITICAL(&state_lock);
    ftm_model_result_t result = {0};
    ftm_model_status_t status;
    if (current_generation != report->generation) {
        ftm_model_reset(&clock_model);
        status = FTM_MODEL_STALE;
    } else {
        status = ftm_model_observe(&clock_model, &model_input, started_us, &result);
    }
    ftm_model_snapshot_t snapshot;
    ftm_model_snapshot(&clock_model, esp_timer_get_time(), current_generation, &snapshot);
    portENTER_CRITICAL(&state_lock);
    published_model = snapshot;
    if (generation != report->generation || dropped != report->dropped)
        published_model.valid = false;
    snapshot = published_model;
    portEXIT_CRITICAL(&state_lock);
    int64_t elapsed_us = esp_timer_get_time() - started_us;
    ESP_LOGI(TAG, "FTMMODEL,%" PRIu32 ",%u,%u,%u,%.9f,%.3f,%.3f,%u,%u,%" PRId64,
             report->attempt, (unsigned)status, result.entries, result.predicted,
             result.rate_ppm, result.median_error_ps, result.max_abs_error_ps,
             snapshot.valid, result.wraps, elapsed_us);
}
#endif
extern esp_err_t __real_esp_wifi_ftm_get_report(wifi_ftm_report_entry_t *, uint8_t);
extern esp_err_t __real_esp_wifi_ftm_initiate_session(wifi_ftm_initiator_cfg_t *);

static void association_event(void *context, esp_event_base_t base,
                              int32_t event, void *data)
{
    (void)context; (void)base; (void)data;
    if (event == WIFI_EVENT_STA_CONNECTED || event == WIFI_EVENT_STA_DISCONNECTED) {
        portENTER_CRITICAL(&state_lock);
        ++generation;
#if CONFIG_FTM_LIVE_MODEL
        published_model.valid = false;
#endif
        portEXIT_CRITICAL(&state_lock);
    }
}

esp_err_t __wrap_esp_wifi_ftm_initiate_session(wifi_ftm_initiator_cfg_t *config)
{
    if (config) {
        portENTER_CRITICAL(&state_lock);
        ++attempt;
        memcpy(peer, config->resp_mac, sizeof(peer));
        portEXIT_CRITICAL(&state_lock);
    }
    return __real_esp_wifi_ftm_initiate_session(config);
}

esp_err_t __wrap_esp_wifi_ftm_get_report(wifi_ftm_report_entry_t *entries, uint8_t count)
{
    esp_err_t result = __real_esp_wifi_ftm_get_report(entries, count);
    if (result != ESP_OK || !entries || !count) return result;
    probe_report_t *report = &capture_buffer;
    portENTER_CRITICAL(&state_lock);
    bool capture = ready && count <= ENTRY_LIMIT && !capture_busy;
    if (capture) {
        capture_busy = true;
        report->generation = generation;
        report->attempt = attempt;
        report->dropped = dropped;
        memcpy(report->peer, peer, sizeof(peer));
    } else {
        ++dropped;
#if CONFIG_FTM_LIVE_MODEL
        published_model.valid = false;
#endif
    }
    portEXIT_CRITICAL(&state_lock);
    if (!capture) return result;
    report->before_us = esp_timer_get_time();
    report->mac_us = esp_wifi_internal_get_mac_clock_time();
    report->after_us = esp_timer_get_time();
    report->count = count;
    memcpy(report->entries, entries, count * sizeof(*entries));
    bool queued = xQueueSend(report_queue, report, 0) == pdPASS;
    portENTER_CRITICAL(&state_lock);
    if (!queued) {
        ++dropped;
#if CONFIG_FTM_LIVE_MODEL
        published_model.valid = false;
#endif
    }
    capture_busy = false;
    portEXIT_CRITICAL(&state_lock);
    return result;
}

static void log_reports(void *context)
{
    (void)context;
    esp_err_t status;
    do {
        status = esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                            association_event, NULL);
        if (status == ESP_ERR_INVALID_STATE) vTaskDelay(pdMS_TO_TICKS(100));
    } while (status == ESP_ERR_INVALID_STATE);
    if (status != ESP_OK) {
        ESP_LOGE(TAG, "event registration failed: %s", esp_err_to_name(status));
        vTaskDelete(NULL);
        return;
    }
    ESP_LOGI(TAG, "FTMRAW_BEGIN,1");
    portENTER_CRITICAL(&state_lock);
    ready = true;
    portEXIT_CRITICAL(&state_lock);
    probe_report_t report;
    while (true) {
        if (xQueueReceive(report_queue, &report, pdMS_TO_TICKS(100)) != pdPASS) {
#if CONFIG_FTM_LIVE_MODEL
            ftm_model_snapshot_t snapshot;
            if (!ftm_raw_model_snapshot(&snapshot)) {
                portENTER_CRITICAL(&state_lock);
                bool expired = published_model.valid;
                published_model.valid = false;
                portEXIT_CRITICAL(&state_lock);
                if (expired) ESP_LOGI(TAG, "FTMMODEL_EXPIRED");
            }
#endif
            continue;
        }
#if CONFIG_FTM_LIVE_MODEL
        bool evaluate = true;
#if CONFIG_FTM_LIVE_MODEL_SELF_TEST
        int64_t now_us = esp_timer_get_time();
        if (!first_report_us) first_report_us = now_us;
        int64_t runtime_us = now_us - first_report_us;
        if (runtime_us >= 60000000 && runtime_us < 64000000) {
            if (!input_pause_state) {
                input_pause_state = 1;
                ESP_LOGI(TAG, "FTMMODEL_TEST,pause_input_begin");
            }
            evaluate = false;
            ESP_LOGI(TAG, "FTMMODEL_SKIPPED,%" PRIu32, report.attempt);
        } else if (input_pause_state == 1) {
            input_pause_state = 2;
            ESP_LOGI(TAG, "FTMMODEL_TEST,pause_input_end");
        }
        if (runtime_us >= 360000000 && !rejoin_requested) {
            rejoin_requested = true;
            ESP_LOGI(TAG, "FTMMODEL_TEST,request_rejoin");
            esp_err_t rejoin_status = esp_wifi_disconnect();
            ESP_LOGI(TAG, "FTMMODEL_TEST,rejoin_result,%d", rejoin_status);
        }
#endif
        if (evaluate) evaluate_model(&report);
#endif
        ESP_LOGI(TAG, "FTMRAW,%" PRIu32 ",%" PRIu32 ",%02x%02x%02x%02x%02x%02x"
                 ",%" PRId64 ",%" PRIu32 ",%" PRId64 ",%u,%" PRIu32,
                 report.generation, report.attempt, report.peer[0], report.peer[1],
                 report.peer[2], report.peer[3], report.peer[4], report.peer[5],
                 report.before_us, report.mac_us, report.after_us, report.count,
                 report.dropped);
        for (unsigned index = 0; index < report.count; ++index) {
            const wifi_ftm_report_entry_t *entry = &report.entries[index];
            ESP_LOGI(TAG, "FTMSTAMP,%" PRIu32 ",%u,%u,%d,%" PRIu32 ",%" PRIu64
                     ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%d",
                     report.attempt, index, entry->dlog_token, entry->rssi,
                     entry->rtt, entry->t1, entry->t2, entry->t3, entry->t4,
                     entry->ppm);
        }
    }
}

__attribute__((constructor)) static void start_raw_probe(void)
{
    report_queue = xQueueCreate(QUEUE_LENGTH, sizeof(probe_report_t));
    if (!report_queue) return;
    if (xTaskCreate(log_reports, "ftm_raw", 6144, NULL, 2, NULL) != pdPASS) {
        vQueueDelete(report_queue);
        report_queue = NULL;
    }
}
