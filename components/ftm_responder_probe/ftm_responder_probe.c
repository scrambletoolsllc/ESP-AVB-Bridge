#include <inttypes.h>
#include <stdint.h>
#include <string.h>
#include "esp_log.h"
#include "ftm_responder_fields.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

/* Private ABI and offsets are gated by object hashes in CMakeLists.txt. */
extern void __real_wDev_ftm_record_t1t4(const uint8_t *peer, uint32_t token,
    uint64_t raw_t1, uint64_t raw_t4, int32_t rssi);
extern const uint8_t *ftm_get_resp_session_for_peer(const uint8_t *peer);

typedef struct {
    uint64_t raw_t1, raw_t4, t1, t4;
    int64_t time_us;
    uint32_t sequence, dropped, token;
    int32_t rssi;
    uint16_t compensation;
    uint8_t peer[6], context_found;
#if CONFIG_FTM_RESPONDER_RX_METADATA
    uint32_t words[3], metadata_us;
    uint8_t slot, matches, unstable;
#endif
} responder_record_t;
static QueueHandle_t queue;
static uint32_t sequence, dropped;

#if CONFIG_FTM_RESPONDER_RX_METADATA
/* These slots are read repeatedly by the audited lmac timestamp path. */
static void capture_fields(responder_record_t *record)
{
    int64_t started = esp_timer_get_time();
    record->slot = UINT8_MAX;
    if (!record->raw_t1 || !record->raw_t4) return;
    for (unsigned slot = 0; slot < 16; ++slot) {
        volatile const uint32_t *registers =
            (volatile const uint32_t *)(UINT32_C(0x600a54f0) - slot * 116);
        uint32_t words[3] = {registers[0], registers[1], 0};
        if (ftm_responder_tx_ticks(words) != record->raw_t1) continue;
        words[2] = registers[2];
        /* Retain a TX candidate on failure to distinguish the two checks. */
        if (!record->matches) {
            record->slot = slot;
            memcpy(record->words, words, sizeof(words));
        }
        if (ftm_responder_rx_ticks(words) != record->raw_t4) continue;
        bool stable = true;
        for (unsigned index = 0; index < 3; ++index)
            if (registers[index] != words[index]) stable = false;
        if (!stable) { ++record->unstable; continue; }
        ++record->matches;
        record->slot = slot;
        memcpy(record->words, words, sizeof(words));
    }
    record->metadata_us = esp_timer_get_time() - started;
}
#endif


void __wrap_wDev_ftm_record_t1t4(const uint8_t *peer, uint32_t token,
    uint64_t raw_t1, uint64_t raw_t4, int32_t rssi)
{
    __real_wDev_ftm_record_t1t4(peer,token,raw_t1,raw_t4,rssi);
    if (!queue || !peer || !token) return;
    responder_record_t record={.raw_t1=raw_t1,.raw_t4=raw_t4,
        .time_us=esp_timer_get_time(),.sequence=++sequence,.dropped=dropped,
        .token=token,.rssi=rssi};
    memcpy(record.peer,peer,6);
    const uint8_t *context=ftm_get_resp_session_for_peer(peer);
    if (context && raw_t1) {
        record.context_found=1;
        memcpy(&record.t1,context+48,8);
        memcpy(&record.t4,context+56,8);
        memcpy(&record.compensation,context+118,2);
    }
#if CONFIG_FTM_RESPONDER_RX_METADATA
    capture_fields(&record);
#endif
    if (xQueueSend(queue,&record,0)!=pdPASS) ++dropped;
}

static void log_records(void *unused)
{
    (void)unused;
    responder_record_t record;
    /* Keep RPC chatter from blocking diagnostic UART output. */
    esp_log_level_set("slave_rpc",ESP_LOG_WARN);
    esp_log_level_set("ptp",ESP_LOG_WARN);
    ESP_LOGI("ftm_responder","FTMRESP_BEGIN,1");
    while (xQueueReceive(queue,&record,portMAX_DELAY)==pdPASS) {
        ESP_LOGI("ftm_responder","FTMRESP,%" PRIu32 ",%" PRId64 ",%02x%02x%02x%02x%02x%02x,%" PRIu32 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%u,%" PRId32 ",%u,%" PRIu32,
            record.sequence,record.time_us,record.peer[0],record.peer[1],
            record.peer[2],record.peer[3],record.peer[4],record.peer[5],
            record.token,record.raw_t1,record.raw_t4,record.t1,record.t4,
            record.compensation,record.rssi,record.context_found,record.dropped);
#if CONFIG_FTM_RESPONDER_RX_METADATA
        ESP_LOGI("ftm_responder","FTMRESPMETA,%" PRIu32 ",%u,%u,%u,%" PRIu32 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32,
            record.sequence,record.slot,record.matches,record.unstable,
            record.words[0],record.words[1],record.words[2],record.metadata_us);
#endif
    }
}

__attribute__((constructor)) static void start_responder_probe(void)
{
    queue=xQueueCreate(64,sizeof(responder_record_t));
    if (!queue) return;
    if (xTaskCreate(log_records,"ftm_responder",4096,NULL,2,NULL)!=pdPASS) {
        vQueueDelete(queue);
        queue=NULL;
    }
}
