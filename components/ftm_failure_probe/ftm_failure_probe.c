#include <inttypes.h>
#include <stddef.h>
#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_memory_utils.h"
#include "esp_private/wifi_os_adapter.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#define ENTRY_LIMIT 16
#if CONFIG_FTM_FAILURE_ASSOC_TEST
static esp_timer_handle_t association_test_timer;
static unsigned association_test_sessions;
extern esp_err_t __real_esp_wifi_ftm_initiate_session(wifi_ftm_initiator_cfg_t *config);

static void association_test_disconnect(void *unused)
{
    (void)unused;
    ESP_LOGI("ftm_failure", "FTM_ASSOC_TEST,disconnect");
    esp_err_t result=esp_wifi_disconnect();
    ESP_LOGI("ftm_failure", "FTM_ASSOC_TEST,result,%d",result);
}

esp_err_t __wrap_esp_wifi_ftm_initiate_session(wifi_ftm_initiator_cfg_t *config)
{
    esp_err_t result=__real_esp_wifi_ftm_initiate_session(config);
    if (result==ESP_OK && ++association_test_sessions==5) {
        esp_timer_create_args_t timer_args={.callback=association_test_disconnect,
                                          .name="ftm_assoc_test"};
        ESP_ERROR_CHECK(esp_timer_create(&timer_args,&association_test_timer));
        ESP_ERROR_CHECK(esp_timer_start_once(association_test_timer,50000));
    }
    return result;
}
#endif
/* Private layout is gated by the object SHA256 in CMakeLists.txt. */
extern const uint8_t *ftm_diag_context;
extern const wifi_ftm_report_entry_t *ftm_diag_report;
extern uint8_t ftm_diag_report_count;
extern int __real_wifi_event_post(int event, void *data, size_t length);
_Static_assert(sizeof(wifi_ftm_report_entry_t)==48, "FTM entry ABI changed");
_Static_assert(offsetof(wifi_ftm_report_entry_t,t1)==8, "FTM entry ABI changed");
_Static_assert(sizeof(wifi_event_ftm_report_t)==28, "FTM event ABI changed");

#if CONFIG_FTM_FAILURE_RX_METADATA
#define METADATA_LIMIT 32
typedef struct {
    uint64_t raw_t3;
    uint32_t sequence, rx_coarse, tx_coarse;
    uint16_t rx_correction;
    uint8_t rx_phase, tx_phase;
} rx_metadata_t;
static rx_metadata_t metadata_ring[METADATA_LIMIT];
static uint32_t metadata_sequence;
static portMUX_TYPE metadata_lock=portMUX_INITIALIZER_UNLOCKED;
extern uint64_t __real_hal_mac_ftm_get_t3(const uint8_t *descriptor);

uint64_t __wrap_hal_mac_ftm_get_t3(const uint8_t *descriptor)
{
    uint64_t timestamp=__real_hal_mac_ftm_get_t3(descriptor);
    rx_metadata_t sample={.raw_t3=timestamp};
    memcpy(&sample.rx_coarse,descriptor+12,4);
    memcpy(&sample.tx_coarse,descriptor+76,4);
    sample.rx_phase=descriptor[11]&127;
    sample.tx_phase=descriptor[80]&127;
    sample.rx_correction=(descriptor[34]>>4)|((descriptor[35]&127)<<4);
    portENTER_CRITICAL(&metadata_lock);
    sample.sequence=++metadata_sequence;
    metadata_ring[(sample.sequence-1)%METADATA_LIMIT]=sample;
    portEXIT_CRITICAL(&metadata_lock);
    return timestamp;
}
#endif

typedef struct {
    uint32_t sequence, dropped, allocated;
    int64_t time_us;
    wifi_event_ftm_report_t event;
    uint16_t word72, word74;
    uint8_t received, count, source;
    wifi_ftm_report_entry_t entries[ENTRY_LIMIT];
#if CONFIG_FTM_FAILURE_RX_METADATA
    rx_metadata_t metadata[METADATA_LIMIT];
#endif
} diagnostic_t;
static QueueHandle_t queue;
static diagnostic_t staging;
static uint32_t sequence, dropped;
static wifi_osi_funcs_t diagnostic_osi;
static void (*original_free)(void *);
static wifi_ftm_report_entry_t released_entries[ENTRY_LIMIT];
static uint8_t released_count;
static const uint8_t *released_context;
extern esp_err_t __real_esp_wifi_init(const wifi_init_config_t *config);

/* The failing report is released inside ftm_parse_data before event posting.
 * Match only that buffer, after it has moved out of the active session.
 * No allocation, queue, formatting or timestamp callback is added here.
 */
#if CONFIG_FTM_FAILURE_RETAIN
extern const wifi_ftm_vendor_data_t *ftm_diag_vendor;
extern uint8_t ftm_diag_vendor_count;
_Static_assert(sizeof(wifi_ftm_vendor_data_t) == 102, "FTM vendor ABI changed");
static wifi_ftm_vendor_data_t retained_vendors[ENTRY_LIMIT];
static wifi_ftm_report_entry_t retained_entries[ENTRY_LIMIT];
static uint8_t retained_count, retained_vendor_count;
static wifi_event_ftm_report_t retained_event;
static bool retained_ready;
static int64_t retained_us;
static portMUX_TYPE retention_lock = portMUX_INITIALIZER_UNLOCKED;

void ftm_failure_retention_reset(void)
{
    portENTER_CRITICAL(&retention_lock);
    retained_ready = false;
    retained_count = retained_vendor_count = 0;
    portEXIT_CRITICAL(&retention_lock);
}

bool ftm_failure_recover(const wifi_event_ftm_report_t *event,
                        wifi_ftm_report_entry_t *entries, unsigned *count,
                        wifi_ftm_vendor_data_t *vendors, unsigned *vendor_count)
{
    int64_t now_us = esp_timer_get_time();
    portENTER_CRITICAL(&retention_lock);
    int64_t age = now_us - retained_us;
    bool valid = retained_ready && age >= 0 && age < 2000000 &&
        !memcmp(event, &retained_event, sizeof(*event)) &&
        *count >= retained_count && *vendor_count >= retained_vendor_count;
    if (valid) {
        *count = retained_count;
        *vendor_count = retained_vendor_count;
        memcpy(entries, retained_entries, retained_count * sizeof(*entries));
        memcpy(vendors, retained_vendors, retained_vendor_count * sizeof(*vendors));
    }
    retained_ready = false;
    portEXIT_CRITICAL(&retention_lock);
    return valid;
}
#endif

static void capture_free(void *pointer)
{
    if (pointer && pointer==(const void *)ftm_diag_report) {
        const uint8_t *context=ftm_diag_context;
        const void *active_report=NULL;
        if (context && esp_ptr_internal(context) && esp_ptr_byte_accessible(context)) {
            memcpy(&active_report,context+80,sizeof(active_report));
            unsigned count=ftm_diag_report_count;
            if (!active_report && context[76] && count && count<=ENTRY_LIMIT) {
                memcpy(released_entries,pointer,count*sizeof(released_entries[0]));
                released_context=context;
                released_count=count;
#if CONFIG_FTM_FAILURE_RETAIN
                unsigned vendor_count = ftm_diag_vendor_count;
                if (vendor_count && vendor_count <= ENTRY_LIMIT && ftm_diag_vendor &&
                    esp_ptr_internal(ftm_diag_vendor) && esp_ptr_byte_accessible(ftm_diag_vendor)) {
                    portENTER_CRITICAL(&retention_lock);
                    memcpy(retained_entries, pointer, count * sizeof(retained_entries[0]));
                    memcpy(retained_vendors, ftm_diag_vendor, vendor_count * sizeof(retained_vendors[0]));
                    retained_count = count;
                    retained_vendor_count = vendor_count;
                    portEXIT_CRITICAL(&retention_lock);
                }
#endif
            }
        }
    }
    original_free(pointer);
}

esp_err_t __wrap_esp_wifi_init(const wifi_init_config_t *config)
{
    if (!config || !config->osi_funcs || !config->osi_funcs->_free)
        return __real_esp_wifi_init(config);
    wifi_init_config_t copy=*config;
    diagnostic_osi=*config->osi_funcs;
    original_free=diagnostic_osi._free;
    diagnostic_osi._free=capture_free;
    copy.osi_funcs=&diagnostic_osi;
    return __real_esp_wifi_init(&copy);
}
static const char *TAG="ftm_failure";

/* Called by the Wi-Fi task after RTT classification, before report cleanup.
 * No report getter is called here, so ownership stays with the driver.
 */
int __wrap_wifi_event_post(int event, void *data, size_t length)
{
    if (event==WIFI_EVENT_FTM_REPORT && data && length==sizeof(wifi_event_ftm_report_t)) {
        diagnostic_t *record=&staging;
        memset(record,0,sizeof(*record));
        record->sequence=++sequence;
        record->dropped=dropped;
        record->time_us=esp_timer_get_time();
        memcpy(&record->event,data,sizeof(record->event));
        const uint8_t *context=ftm_diag_context;
        const wifi_ftm_report_entry_t *entries=NULL;
        if (context && esp_ptr_internal(context) && esp_ptr_byte_accessible(context)) {
            memcpy(&record->allocated,context+48,4);
            memcpy(&record->word72,context+72,2);
            memcpy(&record->word74,context+74,2);
            record->received=context[76];
            memcpy(&entries,context+80,sizeof(entries));
            record->source=1;
            if (!entries && record->event.status==FTM_STATUS_SUCCESS) {
                entries=ftm_diag_report;
                record->source=2;
            }
            unsigned count=record->source==1 ? record->allocated : ftm_diag_report_count;
            if (record->event.status==FTM_STATUS_NO_VALID_MSMT && released_context==context && released_count) {
                entries=released_entries;
                count=released_count;
                record->source=3;
            }
            if (entries && count<=64 && esp_ptr_internal(entries) && esp_ptr_byte_accessible(entries)) {
                record->count=count>ENTRY_LIMIT ? ENTRY_LIMIT : count;
                memcpy(record->entries,entries,record->count*sizeof(*entries));
            }
        }
#if CONFIG_FTM_FAILURE_RETAIN
        portENTER_CRITICAL(&retention_lock);
        retained_ready = record->event.status == FTM_STATUS_NO_VALID_MSMT &&
            released_context == context && released_count && retained_count && retained_vendor_count;
        retained_event = record->event;
        retained_us = record->time_us;
        portEXIT_CRITICAL(&retention_lock);
#endif
        released_count=0;
        released_context=NULL;
#if CONFIG_FTM_FAILURE_RX_METADATA
        portENTER_CRITICAL(&metadata_lock);
        memcpy(record->metadata,metadata_ring,sizeof(metadata_ring));
        portEXIT_CRITICAL(&metadata_lock);
#endif
        if (queue && xQueueSend(queue,record,0)!=pdPASS) ++dropped;
    }
    return __real_wifi_event_post(event,data,length);
}

static void log_reports(void *unused)
{
    (void)unused;
    diagnostic_t record;
#if CONFIG_FTM_FAILURE_RESET_TEST
    int64_t first_report_us=0;
    unsigned test_stage=0;
#endif
    ESP_LOGI(TAG,"FTMDEBUG_BEGIN,1,reset=%d",esp_reset_reason());
    while (xQueueReceive(queue,&record,portMAX_DELAY)==pdPASS) {
#if CONFIG_FTM_FAILURE_RESET_TEST
        if (!first_report_us) first_report_us=record.time_us;
#endif
        const wifi_event_ftm_report_t *event=&record.event;
        ESP_LOGI(TAG,"FTMDEBUG,%" PRIu32 ",%" PRId64 ",%d,%u,%" PRIu32 ",%u,%u,%u,%u,%u,%" PRIu32 ",%" PRIu32 ",%" PRIu32,
                 record.sequence,record.time_us,event->status,event->ftm_report_num_entries,
                 record.allocated,record.received,record.source,record.count,
                 record.word72,record.word74,event->rtt_raw,event->rtt_est,record.dropped);
        for (unsigned index=0;index<record.count;++index) {
            const wifi_ftm_report_entry_t *entry=&record.entries[index];
            ESP_LOGI(TAG,"FTMREJECT,%" PRIu32 ",%u,%u,%d,%" PRIu32 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%d",
                     record.sequence,index,entry->dlog_token,entry->rssi,entry->rtt,
                     entry->t1,entry->t2,entry->t3,entry->t4,entry->ppm);
#if CONFIG_FTM_FAILURE_RX_METADATA
            const rx_metadata_t *matched=NULL;
            unsigned matches=0;
            for (unsigned slot=0;slot<METADATA_LIMIT;++slot) {
                const rx_metadata_t *sample=&record.metadata[slot];
                uint64_t ticks=sample->raw_t3+record.word74;
                if (sample->sequence && ticks*1562+ticks/2==entry->t3) {
                    matched=sample;
                    ++matches;
                }
            }
            if (matches==1) {
                ESP_LOGI(TAG,"FTMRXMETA,%" PRIu32 ",%u,%" PRIu32 ",%" PRIu64 ",%" PRIu32 ",%u,%u,%" PRIu32 ",%u",
                         record.sequence,index,matched->sequence,matched->raw_t3,
                         matched->rx_coarse,matched->rx_phase,matched->rx_correction,
                         matched->tx_coarse,matched->tx_phase);
            } else {
                ESP_LOGW(TAG,"FTMRXMETA_MISSING,%" PRIu32 ",%u,%u",record.sequence,index,matches);
            }
#endif
        }
#if CONFIG_FTM_FAILURE_RESET_TEST
        int64_t elapsed=esp_timer_get_time()-first_report_us;
        if (test_stage==0 && elapsed>=60000000) {
            test_stage=1;
            ESP_LOGI(TAG,"FTMRESET,reconnect_begin,%" PRId64,esp_timer_get_time());
            esp_err_t result=esp_wifi_disconnect();
            ESP_LOGI(TAG,"FTMRESET,reconnect_result,%d,%" PRId64,result,esp_timer_get_time());
        } else if (test_stage==1 && elapsed>=120000000) {
            test_stage=2;
            ESP_LOGI(TAG,"FTMRESET,radio_stop_begin,%" PRId64,esp_timer_get_time());
            esp_err_t stop_result=esp_wifi_stop();
            ESP_LOGI(TAG,"FTMRESET,radio_stop_result,%d,%" PRId64,stop_result,esp_timer_get_time());
            esp_err_t start_result=esp_wifi_start();
            ESP_LOGI(TAG,"FTMRESET,radio_start_result,%d,%" PRId64,start_result,esp_timer_get_time());
        } else if (test_stage==2 && elapsed>=180000000) {
            test_stage=3;
            ESP_LOGI(TAG,"FTMRESET,complete,%" PRId64,esp_timer_get_time());
        }
#endif
    }
}

__attribute__((constructor)) static void start_failure_probe(void)
{
#if CONFIG_FTM_FAILURE_RETAIN
    ESP_LOGW(TAG, "Discarded-report retention enabled, exact-blob diagnostic only");
    return;
#endif
    queue=xQueueCreate(4,sizeof(diagnostic_t));
    if (!queue) return;
    if (xTaskCreate(log_reports,"ftm_failure",6144,NULL,2,NULL)!=pdPASS) {
        vQueueDelete(queue);
        queue=NULL;
    }
}
