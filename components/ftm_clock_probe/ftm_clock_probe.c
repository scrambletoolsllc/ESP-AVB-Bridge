#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <time.h>

#include "sdkconfig.h"
#include "esp_err.h"
#include "esp_event.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "edge_capture_state.h"
#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
#include "ftm_transfer.h"
#include "ftm_radio_association.h"
#include "ftm_follow_up_tx.h"
#endif
#if CONFIG_FTM_CLOCK_PROBE_BRIDGE_MAP
#include "ftm_bridge_clock.h"
#include "soc/hp_sys_clkrst_struct.h"
#endif

#if CONFIG_FTM_CLOCK_PROBE_EDGE
#include "driver/gpio.h"
#include "driver/gpio_etm.h"
#include "driver/gptimer.h"
#include "driver/gptimer_etm.h"
#if CONFIG_IDF_TARGET_ESP32C6
#include "driver/pulse_cnt.h"
#endif
#include "esp_intr_alloc.h"
#include "esp_rom_sys.h"
extern void ftm_probe_sample_register(gptimer_handle_t timer,
                                     volatile const uint32_t *peripheral,
                                     uint64_t *before_ticks, uint32_t *sample,
                                     uint64_t *after_ticks);
#endif
#if CONFIG_IDF_TARGET_ESP32C6
#include "esp_private/wifi.h"
#else
#include "ptp_timing_snapshot.h"
#include "ptp_wifi_association.h"
extern int ptpd_now(struct timespec *timestamp);
#if CONFIG_FTM_CLOCK_PROBE_EDGE
#include "soc/emac_ptp_struct.h"
#endif
#endif

extern esp_err_t esp_hosted_send_custom_data(uint32_t message_id,
                                            const uint8_t *data, size_t length);
extern esp_err_t esp_hosted_register_custom_callback(
    uint32_t message_id,
    void (*callback)(uint32_t, const uint8_t *, size_t, void *), void *context);

#define PROBE_REQUEST_ID 0x434c4b01U
#define PROBE_RESPONSE_ID 0x434c4b02U
#define PROBE_ARM_ID 0x434c4b03U
#define PROBE_ARM_ACK_ID 0x434c4b04U
#define PROBE_VERSION 5U

typedef struct {
    uint32_t version, host_boot, sequence, coprocessor_boot, accepted;
} probe_arm_t;

typedef struct {
    uint32_t sequence;
    uint32_t mac_us;
    uint32_t host_boot;
    uint32_t valid;
    uint64_t edge_ticks;
    uint64_t before_ticks;
    uint64_t after_ticks;
    int64_t observed_us;
} probe_edge_t;

typedef struct {
    uint32_t sequence;
    uint32_t token;
    uint32_t mac_us;
    uint32_t reserved;
    int64_t before_us;
    int64_t after_us;
    uint64_t departure_ps;
    uint64_t arrival_ps;
} probe_frame_t;

/* Private RPC protocol, little-endian on both supported targets. */
typedef struct {
    uint32_t version;
    uint32_t sequence;
    uint32_t host_boot;
    uint32_t reserved;
    int64_t host_before_us;
    int64_t host_ptp_ns;
    int64_t host_after_us;
} probe_request_t;

typedef struct {
    probe_request_t request;
    uint32_t coprocessor_boot;
    uint32_t mac_us;
    int64_t receive_us;
    int64_t mac_before_us;
    int64_t mac_after_us;
    int64_t tsf_before_us;
    int64_t tsf_us;
    int64_t tsf_after_us;
    int64_t send_us;
    probe_frame_t frame;
    probe_edge_t edge;
    uint32_t association_generation, association_count;
    uint8_t association_macs[16][6];
} probe_response_t;

_Static_assert(sizeof(probe_request_t) == 40, "RPC request layout");
_Static_assert(sizeof(probe_response_t) == 304, "RPC response layout");

static const char *TAG = "clock_probe";
static uint32_t boot_id;

#if CONFIG_IDF_TARGET_ESP32C6

static DRAM_ATTR probe_frame_t latest_frame;
static DRAM_ATTR portMUX_TYPE frame_lock = portMUX_INITIALIZER_UNLOCKED;
#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
#define TX_SNAPSHOT_COUNT 8
static DRAM_ATTR ftm_follow_up_tx_t tx_snapshots[TX_SNAPSHOT_COUNT];
static DRAM_ATTR portMUX_TYPE tx_lock = portMUX_INITIALIZER_UNLOCKED;
static DRAM_ATTR uint32_t tx_next, tx_valid_frames, tx_invalid_frames;
static uint32_t transfer_host, transfer_generation, transfer_publication;
static DRAM_ATTR ftm_radio_association_t radio_associations;
static DRAM_ATTR ftm_association_state_t association_map;
static DRAM_ATTR uint32_t admitted_radio_generation;
static DRAM_ATTR int64_t tx_prepared_us[TX_SNAPSHOT_COUNT];

uint32_t ftm_radio_association_begin(const uint8_t mac[6], bool joined)
{
    portENTER_CRITICAL(&tx_lock);
    uint32_t generation = ftm_radio_association_change(&radio_associations, mac, joined);
    admitted_radio_generation = 0;
    ftm_association_retire_all(&association_map);
    for (unsigned index = 0; index < TX_SNAPSHOT_COUNT; ++index)
        tx_snapshots[index].valid = false;
    portEXIT_CRITICAL(&tx_lock);
    return generation;
}

void ftm_radio_association_complete(uint32_t generation, bool queued)
{
    portENTER_CRITICAL(&tx_lock);
    ftm_radio_association_forwarded(&radio_associations, generation, queued);
    portEXIT_CRITICAL(&tx_lock);
}


static void invalidate_transfers(void)
{
    portENTER_CRITICAL(&tx_lock);
    for (unsigned index = 0; index < TX_SNAPSHOT_COUNT; ++index)
        tx_snapshots[index].valid = false;
    portEXIT_CRITICAL(&tx_lock);
}
#endif

#if CONFIG_FTM_CLOCK_PROBE_EDGE
static DRAM_ATTR gptimer_handle_t capture_timer;
static DRAM_ATTR probe_edge_t latest_edge;
static DRAM_ATTR portMUX_TYPE edge_lock = portMUX_INITIALIZER_UNLOCKED;
static DRAM_ATTR edge_capture_state_t capture_state;
static DRAM_ATTR pcnt_unit_handle_t edge_counter;

static void IRAM_ATTR capture_edge(void *context)
{
    (void)context;
    probe_edge_t observation = {0};
    /* Preserve the ETM latch before software captures overwrite it.
     * No other code may read this timer with gptimer_get_raw_count(). */
    if (gptimer_get_captured_count(capture_timer, &observation.edge_ticks) != ESP_OK)
        return;
    int edge_count = 0;
    esp_err_t count_status = pcnt_unit_get_count(edge_counter, &edge_count);
    observation.observed_us = esp_timer_get_time();
    ftm_probe_sample_register(capture_timer, (volatile const uint32_t *)0x600ad000U,
                             &observation.before_ticks, &observation.mac_us,
                             &observation.after_ticks);
    portENTER_CRITICAL_ISR(&edge_lock);
    if (count_status != ESP_OK || edge_count != 1) {
        capture_state.fault = true;
        capture_state.armed = false;
        latest_edge.valid = 0;
    } else if (edge_capture_record(&capture_state, observation.edge_ticks)) {
        observation.sequence = capture_state.sequence;
        observation.host_boot = capture_state.host_boot;
        observation.valid = 1;
        latest_edge = observation;
    } else if (capture_state.fault) {
        latest_edge.valid = 0;
    }
    portEXIT_CRITICAL_ISR(&edge_lock);
}

static void initialize_edge_capture(void)
{
    gpio_config_t input = {
        .pin_bit_mask = 1ULL << 2, .mode = GPIO_MODE_INPUT,
        .pull_down_en = GPIO_PULLDOWN_ENABLE, .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&input));
    pcnt_unit_config_t count_config = {.low_limit = -1, .high_limit = 32767};
    ESP_ERROR_CHECK(pcnt_new_unit(&count_config, &edge_counter));
    pcnt_channel_handle_t count_channel;
    pcnt_chan_config_t count_channel_config = {.edge_gpio_num = 2, .level_gpio_num = -1};
    ESP_ERROR_CHECK(pcnt_new_channel(edge_counter, &count_channel_config, &count_channel));
    ESP_ERROR_CHECK(pcnt_channel_set_edge_action(count_channel,
        PCNT_CHANNEL_EDGE_ACTION_INCREASE, PCNT_CHANNEL_EDGE_ACTION_HOLD));
    ESP_ERROR_CHECK(pcnt_unit_enable(edge_counter));
    ESP_ERROR_CHECK(pcnt_unit_clear_count(edge_counter));
    ESP_ERROR_CHECK(pcnt_unit_start(edge_counter));
    gptimer_config_t timer = {
        .clk_src = GPTIMER_CLK_SRC_PLL_F80M, .direction = GPTIMER_COUNT_UP,
        .resolution_hz = 40000000,
    };
    ESP_ERROR_CHECK(gptimer_new_timer(&timer, &capture_timer));
    esp_etm_channel_handle_t channel;
    esp_etm_channel_config_t channel_config = {0};
    ESP_ERROR_CHECK(esp_etm_new_channel(&channel_config, &channel));
    esp_etm_event_handle_t edge;
    gpio_etm_event_config_t edge_config = {.edge = GPIO_ETM_EVENT_EDGE_POS};
    ESP_ERROR_CHECK(gpio_new_etm_event(&edge_config, &edge));
    ESP_ERROR_CHECK(gpio_etm_event_bind_gpio(edge, 2));
    esp_etm_task_handle_t capture;
    gptimer_etm_task_config_t capture_config = {.task_type = GPTIMER_ETM_TASK_CAPTURE};
    ESP_ERROR_CHECK(gptimer_new_etm_task(capture_timer, &capture_config, &capture));
    ESP_ERROR_CHECK(esp_etm_channel_connect(channel, edge, capture));
    ESP_ERROR_CHECK(gptimer_enable(capture_timer));
    ESP_ERROR_CHECK(gptimer_start(capture_timer));
    ESP_ERROR_CHECK(esp_etm_channel_enable(channel));
    esp_err_t result = gpio_install_isr_service(ESP_INTR_FLAG_IRAM);
    if (result != ESP_ERR_INVALID_STATE)
        ESP_ERROR_CHECK(result);
    ESP_ERROR_CHECK(gpio_isr_handler_add(2, capture_edge, NULL));
    ESP_ERROR_CHECK(gpio_set_intr_type(2, GPIO_INTR_POSEDGE));
    ESP_ERROR_CHECK(gpio_intr_enable(2));
    ESP_LOGI(TAG, "GPIO2 edge capture ready, 40 MHz timer");
}
#endif

#if CONFIG_FTM_CLOCK_PROBE_EDGE
static void receive_arm(uint32_t message_id, const uint8_t *data,
                        size_t length, void *context)
{
    (void)context;
    if (message_id != PROBE_ARM_ID || !data || length != sizeof(probe_arm_t)) return;
    probe_arm_t acknowledgment;
    memcpy(&acknowledgment, data, sizeof(acknowledgment));
    if (acknowledgment.version != PROBE_VERSION) return;
    uint64_t baseline;
    if (gptimer_get_captured_count(capture_timer, &baseline) != ESP_OK) return;
    portENTER_CRITICAL(&edge_lock);
    uint32_t previous_host_boot = capture_state.host_boot;
    bool duplicate = capture_state.host_boot == acknowledgment.host_boot &&
        capture_state.sequence == acknowledgment.sequence;
    acknowledgment.accepted = edge_capture_arm(&capture_state,
        acknowledgment.host_boot, acknowledgment.sequence, baseline);
    if (acknowledgment.accepted && !duplicate) {
        /* Count edges in hardware, including coalesced GPIO interrupts. */
        if (pcnt_unit_clear_count(edge_counter) != ESP_OK) {
            capture_state.fault = true;
            capture_state.armed = false;
            acknowledgment.accepted = 0;
        }
        latest_edge = (probe_edge_t){0};
    }
    bool host_changed = previous_host_boot != capture_state.host_boot;
    portEXIT_CRITICAL(&edge_lock);
#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
    if (host_changed) {
        portENTER_CRITICAL(&tx_lock);
        admitted_radio_generation = 0;
        ftm_association_retire_all(&association_map);
        for (unsigned index = 0; index < TX_SNAPSHOT_COUNT; ++index)
            tx_snapshots[index].valid = false;
        portEXIT_CRITICAL(&tx_lock);
    }
#else
    (void)host_changed;
#endif
    acknowledgment.coprocessor_boot = boot_id;
    esp_hosted_send_custom_data(PROBE_ARM_ACK_ID,
        (const uint8_t *)&acknowledgment, sizeof(acknowledgment));
}
#endif

#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
static void receive_associations(const uint8_t *data, size_t length)
{
    ftm_association_packet_t packet;
    uint32_t generation;
    if (!ftm_radio_association_decode(data, length, &generation, &packet)) return;
    uint32_t host_boot = 0;
#if CONFIG_FTM_CLOCK_PROBE_EDGE
    portENTER_CRITICAL(&edge_lock);
    host_boot = capture_state.host_boot;
    portEXIT_CRITICAL(&edge_lock);
#endif
    int64_t now_us = esp_timer_get_time();
    portENTER_CRITICAL(&tx_lock);
    uint32_t previous = admitted_radio_generation;
    uint32_t policy_changed = 0;
    for (unsigned index = 0; index < packet.count; ++index) {
        const ftm_association_entry_t *incoming = &packet.entries[index];
        const ftm_association_entry_t *current = &association_map.entries[index].peer;
        if (!association_map.valid || index >= association_map.count ||
            memcmp(incoming->mac, current->mac, 6) ||
            incoming->association != current->association ||
            incoming->sync_revision != current->sync_revision ||
            incoming->sync_stopped != current->sync_stopped)
            policy_changed |= 1U << index;
    }
    bool accepted = ftm_radio_association_accepts(&radio_associations, generation, &packet) &&
        ftm_association_apply(&association_map, &packet, host_boot, boot_id, now_us);
    if (accepted) admitted_radio_generation = generation;
    portEXIT_CRITICAL(&tx_lock);
    if (accepted && previous != generation)
        ESP_LOGI(TAG, "FTMASSOC,%" PRIu32 ",%" PRIu32, generation, packet.count);
    for (unsigned index = 0; accepted && index < packet.count; ++index)
        if (policy_changed & (1U << index))
            ESP_LOGI(TAG, "FTMPOLICY,%" PRId64 ",%u,%" PRIu32 ",%" PRIu32 ",%u",
                now_us, packet.entries[index].port_number, packet.entries[index].association,
                packet.entries[index].sync_revision, packet.entries[index].sync_stopped);
}

static void receive_transfer(uint32_t message_id, const uint8_t *data,
                             size_t length, void *context)
{
    (void)context;
    if (message_id != PROBE_TRANSFER_ID || !data || length != sizeof(ftm_transfer_t)) return;
    int64_t prepared_us = esp_timer_get_time();
    ftm_transfer_t transfer;
    memcpy(&transfer, data, sizeof(transfer));
    if (transfer.version != PROBE_TRANSFER_VERSION || transfer.radio_boot != boot_id) return;
    if (transfer_host == transfer.host_boot &&
        (int32_t)(transfer.publication - transfer_publication) <= 0) return;
    if (transfer_host != transfer.host_boot || transfer_generation != transfer.generation)
        invalidate_transfers();
    transfer_host = transfer.host_boot;
    transfer_generation = transfer.generation;
    transfer_publication = transfer.publication;
    probe_edge_t edge;
    portENTER_CRITICAL(&edge_lock);
    edge = latest_edge;
    portEXIT_CRITICAL(&edge_lock);
    if (!transfer.valid || !edge.valid || edge.host_boot != transfer.host_boot ||
        edge.sequence != transfer.edge_sequence || edge.edge_ticks != transfer.radio_edge ||
        edge.mac_us != transfer.mac_us || !transfer.generation ||
        transfer.upstream_receive_ns < 0 || transfer.upstream_receive_ns > INT64_MAX - INT64_C(2000000000) ||
        transfer.reference_ns < 0 || transfer.reference_ns > INT64_MAX - INT64_C(2000000000) ||
        transfer.rate_q32 < INT64_C(4286377361) || transfer.rate_q32 > INT64_C(4303557231)) {
        invalidate_transfers();
        return;
    }
    probe_frame_t frame;
    portENTER_CRITICAL(&frame_lock);
    frame = latest_frame;
    portEXIT_CRITICAL(&frame_lock);
    if (!frame.departure_ps) return;
    uint32_t now_mac = esp_wifi_internal_get_mac_clock_time();
    uint32_t age_us = now_mac - transfer.mac_us;
    if (age_us > 1500000) { invalidate_transfers(); return; }
    int64_t now_reference = transfer.reference_ns +
        (int64_t)age_us * 1000 * transfer.rate_q32 / INT64_C(4294967296);
    int64_t source_age_ns = now_reference - transfer.upstream_receive_ns;
    if (source_age_ns < 0 || source_age_ns > 500000000) { invalidate_transfers(); return; }
    uint64_t frame_us = frame.departure_ps / 1000000;
    uint32_t delta = transfer.mac_us - (uint32_t)frame_us;
    int64_t anchor_us = (int64_t)frame_us + (delta <= INT32_MAX ? (int64_t)delta :
        (int64_t)delta - INT64_C(4294967296));
    if (anchor_us < 0 || (uint64_t)anchor_us > UINT64_MAX / 1000000 - 2000000) return;
    int64_t residence_ns = transfer.reference_ns - transfer.upstream_receive_ns + transfer.peer_delay_ns;
    if (residence_ns < -2000000000 || residence_ns > 2000000000) return;
    int64_t remaining_us = (500000000 - source_age_ns) / 1000;
    if (remaining_us > 1500000 - age_us) remaining_us = 1500000 - age_us;
    ftm_follow_up_tx_t next = {
        .anchor_ps = (uint64_t)anchor_us * 1000000,
        .not_before_ps = ((uint64_t)anchor_us + age_us + 1) * 1000000,
        .expires_us = esp_timer_get_time() + remaining_us,
        .rate_q32 = transfer.rate_q32, .generation = transfer.generation, .valid = true,
    };
    int64_t cumulative_rate = (transfer.rate_q32 - INT64_C(4294967296)) * 512;
    if (!ftm_follow_up_relay(transfer.follow_up, sizeof(transfer.follow_up), transfer.source_port,
            0, -3, residence_ns * 65536, cumulative_rate, next.ie)) return;
    ftm_follow_up_fields_t fields;
    if (!ftm_follow_up_parse(next.ie, sizeof(next.ie), &fields)) return;
    next.correction_scaled = fields.correction_scaled;
    portENTER_CRITICAL(&tx_lock);
    if (association_map.valid && association_map.host_boot == transfer.host_boot &&
        !memcmp(association_map.clock_identity, transfer.source_port, 8)) {
        unsigned slot = tx_next++ % TX_SNAPSHOT_COUNT;
        tx_snapshots[slot] = next;
        tx_prepared_us[slot] = prepared_us;
    }
    portEXIT_CRITICAL(&tx_lock);
    if (!(transfer.publication % 5))
        ESP_LOGI(TAG, "FTMPUBLISH,%" PRIu32 ",%" PRIu32 ",%" PRIu32 ",%" PRId64 ",%u",
            transfer.publication, transfer.generation, transfer.edge_sequence, source_age_ns, age_us);
}
#endif

#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
/* Per-port Follow_Up sequenceId pools (10.5.7), keyed by logical port number.
 * Caller holds tx_lock. The table lives in DRAM for the lmac TX path. */
static struct { uint16_t port, sequence; } tx_sequences[FTM_ASSOC_MAX];

static IRAM_ATTR uint16_t follow_up_sequence(const uint8_t source_port[10])
{
    uint16_t port = ((uint16_t)source_port[8] << 8) | source_port[9];
    unsigned free_slot = FTM_ASSOC_MAX;
    for (unsigned index = 0; index < FTM_ASSOC_MAX; ++index) {
        if (tx_sequences[index].port == port) return ++tx_sequences[index].sequence;
        if (!tx_sequences[index].port && free_slot == FTM_ASSOC_MAX) free_slot = index;
    }
    if (free_slot == FTM_ASSOC_MAX) free_slot = port % FTM_ASSOC_MAX;
    tx_sequences[free_slot].port = port;
    tx_sequences[free_slot].sequence = 1;
    return 1;
}
#endif

static IRAM_ATTR int capture_frame(const uint8_t peer[6], uint8_t token,
                                  uint8_t followup, uint64_t departure,
                                  uint64_t arrival, uint8_t *buffer,
                                  uint16_t *length)
{
    (void)token;
    if (*length < 6)
        return 1;
    if (followup && departure && arrival) {
        int64_t before = esp_timer_get_time();
        /* Diagnostic C6 register, verified against this SDK's MAC getter.
         * The getter itself resides in flash and cannot run in this callback. */
        uint32_t mac = *(volatile uint32_t *)0x600ad000U;
        int64_t after = esp_timer_get_time();
        portENTER_CRITICAL_ISR(&frame_lock);
        latest_frame.sequence++;
        latest_frame.token = followup;
        latest_frame.mac_us = mac;
        latest_frame.before_us = before;
        latest_frame.after_us = after;
        latest_frame.departure_ps = departure;
        latest_frame.arrival_ps = arrival;
        portEXIT_CRITICAL_ISR(&frame_lock);
    }
#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
    int64_t now_us = esp_timer_get_time();
    const ftm_follow_up_tx_t *chosen = NULL;
    uint8_t source_port[10];
    portENTER_CRITICAL_ISR(&tx_lock);
    if (radio_associations.forwarded && admitted_radio_generation &&
        admitted_radio_generation == radio_associations.generation) {
        for (unsigned count = 0; count < TX_SNAPSHOT_COUNT; ++count) {
            unsigned slot = (tx_next - 1 - count) % TX_SNAPSHOT_COUNT;
            const ftm_follow_up_tx_t *snapshot = &tx_snapshots[slot];
            if (snapshot->valid && departure >= snapshot->not_before_ps && now_us <= snapshot->expires_us) {
                if (ftm_association_select(&association_map, peer, now_us, tx_prepared_us[slot], source_port))
                    chosen = snapshot;
                /* Older publications cannot cross a newer association boundary. */
                break;
            }
        }
    }
    uint16_t sequence = chosen ? follow_up_sequence(source_port) : 0;
    bool emitted = ftm_follow_up_emit(chosen, departure, now_us, followup, sequence, buffer, *length);
    if (emitted) {
        for (unsigned index = 0; index < 10; ++index) buffer[26 + index] = source_port[index];
        ++tx_valid_frames;
    } else ++tx_invalid_frames;
    portEXIT_CRITICAL_ISR(&tx_lock);
    *length = FTM_FOLLOW_UP_IE_SIZE;
    return emitted ? 0 : 1;
#else
    buffer[2] = 0xaa;
    buffer[3] = 0xbb;
    buffer[4] = 0xcc;
    buffer[5] = 'C';
    *length = 6;
    return 0;
#endif
}

static void receive_request(uint32_t message_id, const uint8_t *data,
                            size_t length, void *context)
{
#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
    if (message_id == PROBE_TRANSFER_ID && length == FTM_ASSOC_ADMISSION_SIZE) {
        receive_associations(data, length);
        return;
    }
    if (message_id == PROBE_TRANSFER_ID && length == sizeof(ftm_transfer_t)) {
        receive_transfer(message_id, data, length, context);
        return;
    }
#endif
    const int64_t receive_us = esp_timer_get_time();
    (void)context;
    if (message_id != PROBE_REQUEST_ID || !data || length != sizeof(probe_request_t))
        return;
    probe_response_t response = {0};
    memcpy(&response.request, data, sizeof(response.request));
    if (response.request.version != PROBE_VERSION)
        return;
    response.coprocessor_boot = boot_id;
    response.receive_us = receive_us;
    response.mac_before_us = esp_timer_get_time();
    response.mac_us = esp_wifi_internal_get_mac_clock_time();
    response.mac_after_us = esp_timer_get_time();
    response.tsf_before_us = esp_timer_get_time();
    response.tsf_us = esp_wifi_get_tsf_time(WIFI_IF_AP);
    response.tsf_after_us = esp_timer_get_time();
    portENTER_CRITICAL(&frame_lock);
    response.frame = latest_frame;
    portEXIT_CRITICAL(&frame_lock);
#if CONFIG_FTM_CLOCK_PROBE_EDGE
    portENTER_CRITICAL(&edge_lock);
    response.edge = latest_edge;
    portEXIT_CRITICAL(&edge_lock);
#endif
#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
    portENTER_CRITICAL(&tx_lock);
    if (radio_associations.forwarded) {
        response.association_generation = radio_associations.generation;
        response.association_count = radio_associations.count;
        memcpy(response.association_macs, radio_associations.macs, sizeof(response.association_macs));
    }
    portEXIT_CRITICAL(&tx_lock);
#endif
    response.send_us = esp_timer_get_time();
#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
    if (!(response.request.sequence % 5))
        ESP_LOGI(TAG, "FTMTX,%" PRIu32 ",%" PRIu32, tx_valid_frames, tx_invalid_frames);
#endif
    esp_err_t result = esp_hosted_send_custom_data(
        PROBE_RESPONSE_ID, (const uint8_t *)&response, sizeof(response));
    if (result != ESP_OK)
        ESP_LOGW(TAG, "response failed: %s", esp_err_to_name(result));
}

#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
/* Status telemetry only; the asynchronous event cannot establish a complete grant. */
static void observe_ftm_request(void *context, esp_event_base_t base, int32_t id, void *data)
{
    (void)context; (void)base; (void)id;
    if (!data) return;
    const wifi_event_ftm_request_t *request = data;
    static uint32_t seen;
    static uint8_t previous_count, previous_delta;
    static uint16_t previous_period;
    static bool previous_accepted;
    bool changed = request->frm_count != previous_count ||
        request->min_delta_ftm != previous_delta || request->burst_period != previous_period ||
        request->accepted != previous_accepted;
    previous_count = request->frm_count;
    previous_delta = request->min_delta_ftm;
    previous_period = request->burst_period;
    previous_accepted = request->accepted;
    if ((++seen % 64) != 1 && !changed) return;
    bool associated = false;
    portENTER_CRITICAL(&tx_lock);
    uint32_t generation = radio_associations.generation;
    for (unsigned index = 0; index < radio_associations.count; ++index)
        if (!memcmp(radio_associations.macs[index], request->peer_mac, 6)) associated = true;
    portEXIT_CRITICAL(&tx_lock);
    ESP_LOGI(TAG, "FTMREQUEST,%" PRIu32 ",%" PRIu32 ",%u,%02x%02x%02x%02x%02x%02x,%u,%u,%u,%u",
        seen, generation, associated,
        request->peer_mac[0], request->peer_mac[1], request->peer_mac[2],
        request->peer_mac[3], request->peer_mac[4], request->peer_mac[5],
        request->accepted, request->frm_count, request->burst_period, request->min_delta_ftm);
}
#endif

static void probe_task(void *context)
{
    (void)context;
    boot_id = esp_random() | 1U;
    esp_log_level_set("slave_rpc", ESP_LOG_WARN);
    esp_log_level_set("ptp", ESP_LOG_WARN);
#if CONFIG_FTM_CLOCK_PROBE_EDGE
    initialize_edge_capture();
    ESP_ERROR_CHECK(esp_hosted_register_custom_callback(PROBE_ARM_ID, receive_arm, NULL));
#endif
    ESP_ERROR_CHECK(esp_hosted_register_custom_callback(
        PROBE_REQUEST_ID, receive_request, NULL));
    ESP_LOGI(TAG, "C6 mapping probe ready boot=%" PRIu32, boot_id);
    while (true) {
        unsigned ie_size = 6;
#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
        ie_size = FTM_FOLLOW_UP_IE_SIZE;
#endif
        if (esp_wifi_get_tsf_time(WIFI_IF_AP) > 0 &&
            esp_wifi_ftm_resp_register_vendor_ie_cb(capture_frame, ie_size, false) == ESP_OK)
            break;
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_FTM_REQUEST,
                                               observe_ftm_request, NULL));
#endif
    ESP_LOGI(TAG, "FTM clock observation enabled");
    vTaskDelete(NULL);
}

#else

typedef struct {
    probe_response_t response;
    int64_t receive_us;
    int64_t ptp_ns;
    int64_t after_us;
} probe_observation_t;

static QueueHandle_t observations;

#if CONFIG_FTM_CLOCK_PROBE_EDGE
static gptimer_handle_t host_capture_timer;
static uint32_t host_edge_sequence;
static uint32_t armed_coprocessor_boot;
static QueueHandle_t arm_acknowledgments;
#if CONFIG_FTM_CLOCK_PROBE_BRIDGE_MAP
static ftm_bridge_clock_t bridge_clock;
static ftm_bridge_observation_t host_clock_anchor;
static ptp_timing_snapshot_t host_clock_source;
#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
ESP_EVENT_DEFINE_BASE(FTM_ASSOCIATION_EVENT);
typedef struct {
    uint32_t radio_boot, generation, count;
    uint8_t macs[FTM_ASSOC_MAX][6];
    int64_t received_us;
} host_association_event_t;

static void reconcile_associations(void *context, esp_event_base_t base, int32_t id, void *data)
{
    (void)context; (void)base; (void)id;
    const host_association_event_t *event = data;
    int64_t age = esp_timer_get_time() - event->received_us;
    if (event->radio_boot != armed_coprocessor_boot || age < 0 || age >= FTM_ASSOC_MAX_AGE_US)
        return;
    static uint32_t previous_boot, previous_generation;
    bool accepted = ptpd_wifi_association_reconcile(1, event->radio_boot, event->generation,
                                                    event->macs, event->count);
    if (accepted && (previous_boot != event->radio_boot || previous_generation != event->generation)) {
        previous_boot = event->radio_boot;
        previous_generation = event->generation;
        ESP_LOGI(TAG, "HOSTASSOC,%" PRIu32 ",%" PRIu32 ",%" PRIu32,
            event->radio_boot, event->generation, event->count);
    }
}

static void publish_associations(const ptp_timing_snapshot_t *source)
{
    static uint32_t publication;
    ptp_wifi_association_snapshot_t snapshot;
    if (!ptpd_wifi_association_snapshot(1, &snapshot) ||
        snapshot.radio_boot != armed_coprocessor_boot || !snapshot.radio_generation) return;
    if (!++publication) ++publication;
    ftm_association_packet_t packet = {.host_boot = boot_id,
        .radio_boot = snapshot.radio_boot, .publication = publication, .count = snapshot.count};
    memcpy(packet.clock_identity, source->own_identity, 8);
    for (unsigned index = 0; index < snapshot.count; ++index) {
        memcpy(packet.entries[index].mac, snapshot.entries[index].mac, 6);
        packet.entries[index].port_number = snapshot.entries[index].port_number;
        packet.entries[index].association = snapshot.entries[index].association;
        packet.entries[index].sync_stopped = snapshot.entries[index].sync_stopped;
        packet.entries[index].sync_revision = snapshot.entries[index].sync_revision;
    }
    uint8_t wire[FTM_ASSOC_ADMISSION_SIZE];
    if (ftm_radio_association_encode(snapshot.radio_generation, &packet, wire, sizeof(wire)))
        (void)esp_hosted_send_custom_data(PROBE_TRANSFER_ID, wire, sizeof(wire));
}

static void publish_timing(void)
{
    static uint32_t publication;
    ftm_bridge_snapshot_t mapped;
    ptp_timing_snapshot_t source;
    bool mapped_valid = ftm_bridge_clock_snapshot(&bridge_clock, esp_timer_get_time(), &mapped);
    bool source_valid = ptpd_time_source_snapshot(&source);
    if (source_valid) publish_associations(&source);
    ftm_transfer_t transfer = {
        .version = PROBE_TRANSFER_VERSION, .host_boot = boot_id,
        .radio_boot = armed_coprocessor_boot, .publication = ++publication,
        .generation = source.generation,
    };
    if (mapped_valid && source_valid && source.hardware_clock &&
        mapped.source_generation == source.generation &&
        source.offset_ns >= -1000 && source.offset_ns <= 1000) {
        transfer.reference_ns = mapped.reference_ns;
        transfer.rate_q32 = mapped.rate_q32;
        transfer.upstream_receive_ns = source.local_receive_ns;
        transfer.radio_edge = bridge_clock.history[bridge_clock.count - 1].radio_edge;
        transfer.edge_sequence = mapped.sequence;
        transfer.mac_us = mapped.mac_us;
        transfer.peer_delay_ns = source.peer_delay_ns;
        transfer.valid = true;
        memcpy(transfer.follow_up, source.follow_up, sizeof(transfer.follow_up));
        memcpy(transfer.source_port, source.own_identity, 8);
        transfer.source_port[9] = 2;
        memcpy(transfer.btc_identity, source.btc_identity, 8);
    }
    esp_err_t result = esp_hosted_send_custom_data(PROBE_TRANSFER_ID,
        (const uint8_t *)&transfer, sizeof(transfer));
    if (result != ESP_OK) ESP_LOGW(TAG, "timing publication failed: %s", esp_err_to_name(result));
}
#endif
#endif

#if CONFIG_FTM_CLOCK_PROBE_CORE_AUDIT
typedef struct {
    uint32_t core, mode;
    uint64_t minimum, maximum, total;
} capture_audit_t;

static void audit_capture_core(void *context)
{
    QueueHandle_t results = context;
    for (unsigned mode = 0; mode < 4; ++mode) {
        capture_audit_t result = {.core = xPortGetCoreID(), .mode = mode,
                                .minimum = UINT64_MAX};
        for (unsigned attempt = 0; attempt < 64; ++attempt) {
            if (mode & 1) {
                struct timespec timestamp;
                ptpd_now(&timestamp);
            }
            if (mode & 2) {
                volatile uint32_t control = EMAC_PTP.timestamp_ctrl.val;
                volatile uint32_t seconds = EMAC_PTP.sys_seconds.ts_second;
                (void)control;
                (void)seconds;
            }
            uint64_t before, after;
            uint32_t fraction;
            ftm_probe_sample_register(host_capture_timer, &EMAC_PTP.sys_nanosec.val,
                                     &before, &fraction, &after);
            uint64_t width = after - before;
            if (width < result.minimum) result.minimum = width;
            if (width > result.maximum) result.maximum = width;
            result.total += width;
            vTaskDelay(1);
        }
        xQueueSend(results, &result, portMAX_DELAY);
    }
    vTaskDelete(NULL);
}

static void audit_capture_cores(void)
{
    QueueHandle_t results = xQueueCreate(1, sizeof(capture_audit_t));
    if (!results) return;
    for (unsigned core = 0; core < portNUM_PROCESSORS; ++core) {
        if (xTaskCreatePinnedToCore(audit_capture_core, "capture_audit", 2048,
                                   results, 3, NULL, core) != pdPASS) continue;
        for (unsigned mode = 0; mode < 4; ++mode) {
            capture_audit_t result;
            if (xQueueReceive(results, &result, portMAX_DELAY) == pdTRUE)
                ESP_LOGI(TAG, "CORECAP,%" PRIu32 ",%" PRIu32 ",64,%" PRIu64 ",%" PRIu64 ",%" PRIu64,
                    result.core, result.mode, result.minimum * 25,
                    result.total * 25 / 64, result.maximum * 25);
        }
    }
    vQueueDelete(results);
}
#endif

static void receive_arm_ack(uint32_t message_id, const uint8_t *data,
                            size_t length, void *context)
{
    (void)context;
    if (message_id != PROBE_ARM_ACK_ID || !data || length != sizeof(probe_arm_t)) return;
    probe_arm_t acknowledgment;
    memcpy(&acknowledgment, data, sizeof(acknowledgment));
    if (acknowledgment.version == PROBE_VERSION && acknowledgment.host_boot == boot_id)
        xQueueSend(arm_acknowledgments, &acknowledgment, 0);
}

static bool arm_edge(void)
{
    probe_arm_t request = {.version = PROBE_VERSION, .host_boot = boot_id,
        .sequence = ++host_edge_sequence};
    if (!request.sequence) return false;
    xQueueReset(arm_acknowledgments);
    if (esp_hosted_send_custom_data(PROBE_ARM_ID, (const uint8_t *)&request,
                                    sizeof(request)) != ESP_OK) return false;
    probe_arm_t acknowledgment;
    if (xQueueReceive(arm_acknowledgments, &acknowledgment, pdMS_TO_TICKS(1000)) != pdTRUE ||
        acknowledgment.sequence != request.sequence || !acknowledgment.accepted ||
        !acknowledgment.coprocessor_boot) {
        ESP_LOGW(TAG, "edge arm failed, no pulse emitted");
        return false;
    }
    armed_coprocessor_boot = acknowledgment.coprocessor_boot;
#if CONFIG_FTM_CLOCK_PROBE_FAULT_TEST
    if (request.sequence == 7) {
        ESP_LOGW(TAG, "EDGEFAULT,ignore_ack,7,no_pulse");
        return false;
    }
#endif
    ESP_LOGI(TAG, "EDGEARM,%" PRIu32 ",%" PRIu32 ",%" PRIu32,
        boot_id, request.sequence, armed_coprocessor_boot);
    return true;
}

static void initialize_host_capture(void)
{
    gpio_config_t pin = {
        .pin_bit_mask = 1ULL << 6, .mode = GPIO_MODE_INPUT_OUTPUT,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_set_level(6, 0));
    ESP_ERROR_CHECK(gpio_config(&pin));
    gptimer_config_t timer = {
        .clk_src = GPTIMER_CLK_SRC_PLL_F80M, .direction = GPTIMER_COUNT_UP,
        .resolution_hz = 40000000,
    };
    ESP_ERROR_CHECK(gptimer_new_timer(&timer, &host_capture_timer));
    esp_etm_channel_handle_t channel;
    esp_etm_channel_config_t channel_config = {0};
    ESP_ERROR_CHECK(esp_etm_new_channel(&channel_config, &channel));
    esp_etm_event_handle_t edge;
    gpio_etm_event_config_t edge_config = {.edge = GPIO_ETM_EVENT_EDGE_POS};
    ESP_ERROR_CHECK(gpio_new_etm_event(&edge_config, &edge));
    ESP_ERROR_CHECK(gpio_etm_event_bind_gpio(edge, 6));
    esp_etm_task_handle_t capture;
    gptimer_etm_task_config_t capture_config = {.task_type = GPTIMER_ETM_TASK_CAPTURE};
    ESP_ERROR_CHECK(gptimer_new_etm_task(host_capture_timer, &capture_config, &capture));
    ESP_ERROR_CHECK(esp_etm_channel_connect(channel, edge, capture));
    ESP_ERROR_CHECK(gptimer_enable(host_capture_timer));
    ESP_ERROR_CHECK(gptimer_start(host_capture_timer));
    ESP_ERROR_CHECK(esp_etm_channel_enable(channel));
    ESP_LOGI(TAG, "GPIO6 pulse capture ready, 40 MHz timer");
}
#endif

static bool sample_ptp(int64_t *nanoseconds)
{
    struct timespec timestamp;
    if (ptpd_now(&timestamp) != 0)
        return false;
    *nanoseconds = (int64_t)timestamp.tv_sec * 1000000000LL + timestamp.tv_nsec;
    return true;
}

#if CONFIG_FTM_CLOCK_PROBE_EDGE
static bool sample_hardware_ptp(int64_t *nanoseconds)
{
    uint32_t control = EMAC_PTP.timestamp_ctrl.val;
    if (!EMAC_PTP.timestamp_ctrl.en_timestamp ||
        EMAC_PTP.timestamp_ctrl.ts_initialize || EMAC_PTP.timestamp_ctrl.ts_update)
        return false;
    uint32_t seconds = EMAC_PTP.sys_seconds.ts_second;
    uint32_t fraction = EMAC_PTP.sys_nanosec.ts_sub_seconds;
    if (seconds != EMAC_PTP.sys_seconds.ts_second ||
        control != EMAC_PTP.timestamp_ctrl.val)
        return false;
    uint32_t nanos = EMAC_PTP.timestamp_ctrl.ts_digit_bin_roll_ctrl
        ? fraction : (uint32_t)(((uint64_t)fraction * 1000000000ULL) >> 31);
    if (nanos >= 1000000000U)
        return false;
    *nanoseconds = (int64_t)seconds * 1000000000LL + nanos;
    return true;
}

static void generate_edge(void)
{
#if CONFIG_FTM_CLOCK_PROBE_BRIDGE_MAP
    host_clock_anchor.source_valid = false;
    ptp_timing_snapshot_t source_before;
    bool source_before_valid = ptpd_time_source_snapshot(&source_before);
#endif
#if CONFIG_FTM_CLOCK_PROBE_FAULT_TEST
    if (host_edge_sequence == 3) {
        ESP_LOGW(TAG, "EDGEFAULT,missing_pulse,3");
        return;
    }
#endif
    uint64_t edge_ticks, before_ticks, after_ticks;
    int64_t ptp_ns;
    int64_t api_before, hardware_check, api_after;
    if (!sample_ptp(&api_before) || !sample_hardware_ptp(&hardware_check) ||
        !sample_ptp(&api_after) || hardware_check < api_before || hardware_check > api_after) {
        ESP_LOGW(TAG, "hardware PTP read failed API bracket check");
        return;
    }
    ESP_ERROR_CHECK(gpio_set_level(6, 1));
    esp_rom_delay_us(5);
    ESP_ERROR_CHECK(gpio_set_level(6, 0));
#if CONFIG_FTM_CLOCK_PROBE_FAULT_TEST
    if (host_edge_sequence == 5) {
        esp_rom_delay_us(5);
        ESP_ERROR_CHECK(gpio_set_level(6, 1));
        esp_rom_delay_us(5);
        ESP_ERROR_CHECK(gpio_set_level(6, 0));
        ESP_LOGW(TAG, "EDGEFAULT,extra_pulse,5");
    }
#endif
    ESP_ERROR_CHECK(gptimer_get_captured_count(host_capture_timer, &edge_ticks));
    for (unsigned attempt = 0; attempt < 4; ++attempt) {
        uint32_t control = EMAC_PTP.timestamp_ctrl.val;
        bool digital = EMAC_PTP.timestamp_ctrl.ts_digit_bin_roll_ctrl;
        uint32_t seconds = EMAC_PTP.sys_seconds.ts_second;
        uint32_t fraction;
    #if CONFIG_FTM_CLOCK_PROBE_BRIDGE_MAP
        uint32_t addend = EMAC_PTP.timestamp_addend.val;
        uint32_t increment = EMAC_PTP.sub_sec_incre.sub_second_incre_value;
        uint32_t clock_select = HP_SYS_CLKRST.peri_clk_ctrl01.reg_emac_ptp_ref_clk_src_sel;
    #endif
        ftm_probe_sample_register(host_capture_timer, &EMAC_PTP.sys_nanosec.val,
                                 &before_ticks, &fraction, &after_ticks);
        fraction &= 0x7fffffffU;
        bool valid = seconds == EMAC_PTP.sys_seconds.ts_second &&
            control == EMAC_PTP.timestamp_ctrl.val &&
            !EMAC_PTP.timestamp_ctrl.ts_initialize && !EMAC_PTP.timestamp_ctrl.ts_update;
        uint32_t nanos = digital ? fraction
            : (uint32_t)(((uint64_t)fraction * 1000000000ULL) >> 31);
        valid = valid && nanos < 1000000000U;
        ptp_ns = (int64_t)seconds * 1000000000LL + nanos;
    #if CONFIG_FTM_CLOCK_PROBE_BRIDGE_MAP
        valid = valid && !EMAC_PTP.timestamp_ctrl.addend_reg_update &&
            EMAC_PTP.timestamp_ctrl.ts_fine_coarse_update &&
            addend == EMAC_PTP.timestamp_addend.val &&
            increment == EMAC_PTP.sub_sec_incre.sub_second_incre_value &&
            clock_select == HP_SYS_CLKRST.peri_clk_ctrl01.reg_emac_ptp_ref_clk_src_sel;
        double source_hz = clock_select ? 80000000.0 : 40000000.0;
        double increment_ns = digital ? increment : increment * (1e9 / 2147483648.0);
        int64_t host_rate_q32 = (int64_t)(addend * increment_ns * source_hz / 1e9 + .5);
        bool source_after_valid = ptpd_time_source_snapshot(&host_clock_source);
        host_clock_anchor = (ftm_bridge_observation_t){
            .host_boot = boot_id, .radio_boot = armed_coprocessor_boot,
            .source_generation = host_clock_source.generation,
            .sequence = host_edge_sequence, .host_edge = edge_ticks,
            .host_before = before_ticks, .host_after = after_ticks,
            .ptp_ns = ptp_ns, .received_us = esp_timer_get_time(),
            .trim_ppb = host_clock_source.trim_ppb,
            .host_rate_q32 = host_rate_q32,
            .source_valid = valid && source_before_valid && source_after_valid &&
                source_before.generation == host_clock_source.generation &&
                host_clock_source.hardware_clock && host_clock_source.offset_ns >= -1000 &&
                host_clock_source.offset_ns <= 1000,
        };
        if (attempt < 3 && (!valid || after_ticks - before_ticks > 40)) {
            ESP_LOGW(TAG, "HOSTRETRY,%u,%u,%" PRIu64,
                     host_edge_sequence, attempt + 1, after_ticks - before_ticks);
            continue;
        }
        ESP_LOGI(TAG, "HWRATE,%" PRIu32 ",%" PRId32 ",%" PRId64 ",%" PRIu32 ",%" PRIu32 ",%u",
            host_edge_sequence, host_clock_source.trim_ppb, host_rate_q32, addend,
            increment, clock_select);
    #endif
        if (valid)
            ESP_LOGI(TAG, "HOSTEDGE,%" PRIu32 ",%" PRIu32 ",%" PRIu64
                ",%" PRIu64 ",%" PRId64 ",%" PRIu64,
                boot_id, host_edge_sequence, edge_ticks, before_ticks, ptp_ns, after_ticks);
        break;
    }
}
#endif

static void receive_response(uint32_t message_id, const uint8_t *data,
                             size_t length, void *context)
{
    const int64_t receive_us = esp_timer_get_time();
    (void)context;
    if (message_id != PROBE_RESPONSE_ID || !data || length != sizeof(probe_response_t))
        return;
    probe_observation_t observation = {.receive_us = receive_us};
    if (!sample_ptp(&observation.ptp_ns))
        return;
    observation.after_us = esp_timer_get_time();
    memcpy(&observation.response, data, sizeof(observation.response));
    if (observation.response.request.version != PROBE_VERSION ||
        observation.response.request.host_boot != boot_id)
        return;
#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
    if (observation.response.association_generation && observation.response.association_count <= FTM_ASSOC_MAX) {
        host_association_event_t event = {.radio_boot = observation.response.coprocessor_boot,
            .generation = observation.response.association_generation,
            .count = observation.response.association_count, .received_us = receive_us};
        memcpy(event.macs, observation.response.association_macs, sizeof(event.macs));
        (void)esp_event_post(FTM_ASSOCIATION_EVENT, 0, &event, sizeof(event), 0);
    }
#endif
    if (xQueueSend(observations, &observation, 0) != pdTRUE)
        ESP_LOGW(TAG, "observation queue full");
}

static void log_observation(const probe_observation_t *observation)
{
    const probe_response_t *response = &observation->response;
    const probe_request_t *request = &response->request;
    ESP_LOGI(TAG, "CLOCK,%" PRIu32 ",%" PRIu32 ",%" PRIu32
        ",%" PRId64 ",%" PRId64 ",%" PRId64
        ",%" PRId64 ",%" PRId64 ",%" PRIu32 ",%" PRId64
        ",%" PRId64 ",%" PRId64 ",%" PRId64 ",%" PRId64
        ",%" PRId64 ",%" PRId64 ",%" PRId64,
        request->host_boot, response->coprocessor_boot, request->sequence,
        request->host_before_us, request->host_ptp_ns, request->host_after_us,
        response->receive_us, response->mac_before_us, response->mac_us,
        response->mac_after_us, response->tsf_before_us, response->tsf_us,
        response->tsf_after_us, response->send_us,
        observation->receive_us, observation->ptp_ns, observation->after_us);
    static uint32_t previous_frame;
    const probe_frame_t *frame = &response->frame;
    if (frame->sequence && frame->sequence != previous_frame) {
        previous_frame = frame->sequence;
        ESP_LOGI(TAG, "FTMCLOCK,%" PRIu32 ",%" PRIu32 ",%" PRIu32
            ",%" PRIu32 ",%" PRIu32 ",%" PRId64 ",%" PRId64
            ",%" PRIu64 ",%" PRIu64,
            request->host_boot, response->coprocessor_boot, frame->sequence,
            frame->token, frame->mac_us, frame->before_us, frame->after_us,
            frame->departure_ps, frame->arrival_ps);
    }
#if CONFIG_FTM_CLOCK_PROBE_EDGE
    static uint32_t previous_edge;
    const probe_edge_t *edge = &response->edge;
    if (request->reserved && (!edge->valid || edge->host_boot != boot_id ||
        response->coprocessor_boot != armed_coprocessor_boot || edge->sequence != request->reserved)) {
#if CONFIG_FTM_CLOCK_PROBE_BRIDGE_MAP
        ftm_bridge_clock_reset(&bridge_clock);
#endif
        ESP_LOGW(TAG, "EDGEREJECT,%" PRIu32 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32,
            boot_id, request->reserved, edge->sequence, edge->valid);
    }
    if (edge->valid && edge->host_boot == boot_id &&
        response->coprocessor_boot == armed_coprocessor_boot &&
        edge->sequence == request->reserved && edge->sequence != previous_edge) {
        previous_edge = edge->sequence;
#if CONFIG_FTM_CLOCK_PROBE_BRIDGE_MAP
        ftm_bridge_snapshot_t previous, mapped;
        int64_t now_us = esp_timer_get_time();
        bool previous_valid = ftm_bridge_clock_snapshot(&bridge_clock, now_us, &previous);
        ftm_bridge_observation_t input = host_clock_anchor;
        ptp_timing_snapshot_t source;
        bool source_valid = ptpd_time_source_snapshot(&source);
        input.source_valid = input.source_valid && input.sequence == edge->sequence &&
            source_valid && source.generation == input.source_generation;
        input.radio_edge = edge->edge_ticks;
        input.radio_before = edge->before_ticks;
        input.radio_after = edge->after_ticks;
        input.mac_us = edge->mac_us;
        ftm_bridge_result_t result = ftm_bridge_clock_observe(&bridge_clock, &input);
        bool mapped_valid = ftm_bridge_clock_snapshot(&bridge_clock, now_us, &mapped);
        int64_t predicted = 0, residual = INT64_MIN;
        if (mapped_valid && previous_valid && previous.host_boot == mapped.host_boot &&
            previous.radio_boot == mapped.radio_boot &&
            previous.source_generation == mapped.source_generation &&
            ftm_bridge_clock_convert(&previous, (uint64_t)mapped.mac_us * 1000000,
                                     now_us, &predicted))
            residual = mapped.reference_ns - predicted;
        ESP_LOGI(TAG, "BRIDGEMAP,%u,%" PRIu32 ",%u,%" PRIu32 ",%" PRId64
            ",%" PRId64 ",%" PRIu32 ",%" PRId64 ",%" PRId64,
            (unsigned)result, input.sequence, mapped_valid, mapped.mac_us,
            mapped.reference_ns, mapped.rate_q32, mapped.read_uncertainty_ns,
            now_us - mapped.refreshed_us, residual);
#endif
        ESP_LOGI(TAG, "EDGECLOCK,%" PRIu32 ",%" PRIu32 ",%" PRIu32
            ",%" PRIu32 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64
            ",%" PRId64 ",%" PRId64 ",%" PRId64 ",%" PRId64 ",%" PRIu32,
            request->host_boot, response->coprocessor_boot, edge->sequence,
            edge->mac_us, edge->edge_ticks, edge->before_ticks, edge->after_ticks,
            edge->observed_us, response->receive_us,
            request->host_ptp_ns, observation->ptp_ns, request->reserved);
    }
#endif
}

static TaskHandle_t host_probe_task;

void ftm_clock_probe_transport_ready(void)
{
    if (host_probe_task) xTaskNotifyGive(host_probe_task);
}

static void probe_task(void *context)
{
    (void)context;
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    boot_id = esp_random() | 1U;
    observations = xQueueCreate(16, sizeof(probe_observation_t));
    if (!observations) {
        ESP_LOGE(TAG, "observation allocation failed");
        vTaskDelete(NULL);
        return;
    }
    ESP_ERROR_CHECK(esp_hosted_register_custom_callback(
        PROBE_RESPONSE_ID, receive_response, NULL));
#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
    ESP_ERROR_CHECK(esp_event_handler_register(FTM_ASSOCIATION_EVENT, 0, reconcile_associations, NULL));
#endif
#if CONFIG_FTM_CLOCK_PROBE_EDGE
    initialize_host_capture();
#if CONFIG_FTM_CLOCK_PROBE_CORE_AUDIT
    audit_capture_cores();
#endif
    arm_acknowledgments = xQueueCreate(4, sizeof(probe_arm_t));
    if (!arm_acknowledgments) { vTaskDelete(NULL); return; }
    ESP_ERROR_CHECK(esp_hosted_register_custom_callback(PROBE_ARM_ACK_ID, receive_arm_ack, NULL));
#endif
    ESP_LOGI(TAG, "columns: host_boot,cp_boot,sequence,host_before_us,host_ptp_ns,"
        "host_after_us,cp_receive_us,mac_before_us,mac_us,mac_after_us,"
        "tsf_before_us,tsf_us,tsf_after_us,cp_send_us,host_receive_us,"
        "host_receive_ptp_ns,host_receive_after_us");
    uint32_t sequence = 0;
#if CONFIG_FTM_CLOCK_PROBE_EDGE
    int64_t next_edge_us = 0;
#endif
    while (true) {
#if CONFIG_IDF_TARGET_ESP32P4
        if (sequence % 5 == 0) {
            ptp_timing_snapshot_t source;
            bool source_valid = ptpd_time_source_snapshot(&source);
            unsigned time_base = ((unsigned)source.follow_up[58] << 8) | source.follow_up[59];
            ESP_LOGI(TAG, "TIMINGSOURCE,%" PRIu32 ",%u,%" PRId64 ",%" PRId64
                ",%" PRId32 ",%" PRId32 ",%" PRId64 ",%u,"
                "%02x%02x%02x%02x%02x%02x%02x%02x",
                source.generation, source_valid, source.received_us, source.offset_ns,
                source.trim_ppb, source.peer_delay_ns, source.correction_ns, time_base,
                source.btc_identity[0], source.btc_identity[1], source.btc_identity[2],
                source.btc_identity[3], source.btc_identity[4], source.btc_identity[5],
                source.btc_identity[6], source.btc_identity[7]);
        }
#endif
#if CONFIG_FTM_CLOCK_PROBE_EDGE
        int64_t edge_now_us = esp_timer_get_time();
        if (edge_now_us >= next_edge_us) {
            /* Reserve margin below the 1.5-second map lifetime under RPC load. */
            next_edge_us = edge_now_us + 750000;
            if (arm_edge()) generate_edge();
        }
#endif
        probe_request_t request = {
            .version = PROBE_VERSION, .sequence = ++sequence, .host_boot = boot_id,
            .host_before_us = esp_timer_get_time(),
        };
#if CONFIG_FTM_CLOCK_PROBE_EDGE
        request.reserved = host_edge_sequence;
#endif
        bool valid = sample_ptp(&request.host_ptp_ns);
        request.host_after_us = esp_timer_get_time();
        if (valid) {
            esp_err_t result = esp_hosted_send_custom_data(
                PROBE_REQUEST_ID, (const uint8_t *)&request, sizeof(request));
            if (result != ESP_OK)
                ESP_LOGW(TAG, "request failed: %s", esp_err_to_name(result));
        }
        probe_observation_t observation;
        if (xQueueReceive(observations, &observation, pdMS_TO_TICKS(1000)) == pdTRUE)
            log_observation(&observation);
        else
            ESP_LOGW(TAG, "response timeout sequence=%" PRIu32, sequence);
#if CONFIG_FTM_CLOCK_PROBE_FOLLOW_UP
        publish_timing();
#endif
        vTaskDelay(pdMS_TO_TICKS(200));
    }
}
#endif

__attribute__((constructor)) static void start_clock_probe(void)
{
#if CONFIG_IDF_TARGET_ESP32P4
    xTaskCreate(probe_task, "clock_probe", 4096, NULL, 2, &host_probe_task);
#else
    xTaskCreate(probe_task, "clock_probe", 4096, NULL, 2, NULL);
#endif
}
