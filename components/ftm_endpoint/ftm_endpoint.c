#include <inttypes.h>
#include <math.h>
#include <stdatomic.h>
#include <string.h>
#include "esp_wifi.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "ptp.h"
#include "ptp_clock_affine.h"
#include "ftm_local_clock.h"
#include "ftm_follow_up.h"
#include "ftm_discipline.h"
#include "ftm_pair_selection.h"
#include "ptp_ftm_clock.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

extern void ftm_failure_retention_reset(void) __attribute__((weak));
#ifndef WIFI_FTM_VENDOR_IE_MAX_LEN
/* Stock IDF: no FTM vendor IE API, so no Follow_Up can arrive; keep the
 * report path compiling and report zero IEs. */
typedef struct {
    uint8_t dialog_token;
    uint8_t vendor_ie_len;
    uint8_t vendor_ie[100];
} wifi_ftm_vendor_data_t;
static inline esp_err_t esp_wifi_ftm_get_vendor_data(wifi_ftm_vendor_data_t *data, uint8_t count) {
    (void)data; (void)count; return ESP_ERR_NOT_SUPPORTED;
}
#define FTM_VENDOR_ENTRIES(report) 0u
#else
#define FTM_VENDOR_ENTRIES(report) ((report)->ftm_vendor_num_entries)
#endif
extern bool ftm_failure_recover(const wifi_event_ftm_report_t *, wifi_ftm_report_entry_t *,
    unsigned *, wifi_ftm_vendor_data_t *, unsigned *) __attribute__((weak));

#define MAX_ENTRIES 64
#define REMOTE_MASK ((UINT64_C(1) << 48) - 1)
static wifi_ftm_report_entry_t entries[MAX_ENTRIES];
static wifi_ftm_vendor_data_t vendors[MAX_ENTRIES];
static ftm_follow_up_fields_t fields[MAX_ENTRIES];
static bool paired[MAX_ENTRIES];
static uint32_t acquisition_generation, reports;
static atomic_uint association_generation = 1;
static int64_t status_applied_us;
static uint32_t status_generation, status_association;
static bool status_phase_ready;
typedef struct {
    int64_t local_ns, reference_ns, received_us;
    uint32_t association, mapping;
    uint16_t time_base;
    uint8_t source_port[10], domain;
    int8_t log_interval;
} clock_observation_t;
static QueueHandle_t observations;

bool ptp_ftm_discipline_enabled(void) {
#if CONFIG_FTM_ENDPOINT_DISCIPLINE
    return true;
#else
    return false;
#endif
}

/* Called only by the PTP daemon, which also applies observations. */
bool ptp_ftm_clock_ready(uint32_t generation)
{
    if (!ptp_ftm_discipline_enabled()) return true;
    int64_t age_us = esp_timer_get_time() - status_applied_us;
    bool ready = status_phase_ready && generation == status_generation &&
        status_association == atomic_load(&association_generation) &&
        age_us >= 0 && age_us <= 375000;
    static int previous = -1;
    if (previous != (int)ready) {
        ESP_LOGI("ftm_endpoint", "FTMREADY,%u,%u,%" PRId64, ready, generation, age_us);
        previous = ready;
    }
    return ready;
}

void ptp_ftm_reset_hook(void)
{
    ++association_generation;
    acquisition_generation = 0;
    if (observations) xQueueReset(observations);
}

void ptp_ftm_daemon_tick(void)
{
    if (!ptp_ftm_discipline_enabled() || !observations) return;
    static ftm_discipline_t model;
    static uint32_t source_generation, local_generation, association, fit_generation = 1;
    static uint16_t time_base;
    static bool disciplined;
    static bool holdover;
    static int64_t last_applied_us;
    clock_observation_t observation;
    while (xQueueReceive(observations, &observation, 0) == pdTRUE) {
        uint32_t generation;
        int64_t age_us = esp_timer_get_time() - observation.received_us;
        if (observation.association != association_generation || age_us < 0 || age_us > 1000000 ||
            !ptpd_ftm_source_observed(0, observation.source_port, observation.domain, observation.log_interval, observation.received_us, &generation)) continue;
        if (generation != source_generation || association != observation.association ||
            time_base != observation.time_base) disciplined = false;
        if (generation != source_generation || association != observation.association ||
            time_base != observation.time_base || observation.mapping != local_generation) ++fit_generation;
        source_generation = generation; association = observation.association;
        local_generation = observation.mapping; time_base = observation.time_base;
        int64_t innovation;
        bool fitted = ftm_discipline_observe(&model, fit_generation, time_base,
            observation.local_ns, observation.reference_ns, &innovation);
        if (!model.valid) status_phase_ready = false;
        int64_t error = INT64_MIN;
        int32_t applied = 0;
        int result = -1;
        bool step = !disciplined;
        if (fitted) {
            result = ptp_clock_sw_discipline(model.local_anchor, model.reference_anchor,
                model.rate_ppb, step, &error, &applied);
            if (!result) {
                disciplined = true;
                holdover = false;
                last_applied_us = esp_timer_get_time();
                status_applied_us = last_applied_us;
                status_generation = generation;
                status_association = observation.association;
                status_phase_ready = !step && error >= -1000 && error <= 1000;
            }
        }
        ESP_LOGI("ftm_endpoint", "FTMDISC,%u,%u,%u,%u,%" PRId64 ",%" PRId64 ",%" PRId32 ",%" PRId32 ",%d",
            fit_generation, model.count, fitted, step, innovation, error, model.rate_ppb, applied, result);
    }
    if (disciplined && !holdover && esp_timer_get_time() - last_applied_us > 1500000) {
        ptp_clock_affine_t clock;
        if (ptp_clock_sw_snapshot(&clock)) {
            int64_t now_ns = ptp_clock_local_ns(), error;
            int32_t applied;
            ptp_clock_sw_discipline(now_ns, ptp_clock_affine_now(&clock, now_ns),
                model.rate_ppb, false, &error, &applied);
            holdover = true;
            ESP_LOGW("ftm_endpoint", "FTMHOLD,%" PRId32, model.rate_ppb);
        }
    }
}

__attribute__((constructor)) static void initialize_receiver(void)
{
    observations = xQueueCreate(16, sizeof(clock_observation_t));
#if CONFIG_FTM_ENDPOINT_PAIR_SELECTION
    ESP_LOGI("ftm_endpoint", "Independent forward/reverse FTM selection enabled");
#endif
#if CONFIG_FTM_ENDPOINT_SIGNED_RTT_EXPERIMENT
    ESP_LOGW("ftm_endpoint", "Signed RTT experiment enabled, -25 ns guard is not a calibration bound");
#endif
}

void ptp_ftm_begin_hook(const uint8_t peer[6])
{
    (void)peer;
    if (ftm_failure_retention_reset) ftm_failure_retention_reset();
    ftm_local_clock_snapshot_t map;
    acquisition_generation = ftm_local_clock_snapshot(&map) ? map.generation : 0;
}

static bool report_source_consistent(unsigned first, unsigned last)
{
    for (unsigned index = first + 1; index <= last; ++index) {
        if (paired[index] &&
            (memcmp(fields[first].source_port, fields[index].source_port, 10) ||
             fields[first].time_base != fields[index].time_base ||
             fields[first].domain != fields[index].domain)) return false;
    }
    return true;
}

bool ptp_ftm_report_hook(const wifi_event_ftm_report_t *report)
{
    ++reports;
    unsigned count = report->ftm_report_num_entries, vendor_count = FTM_VENDOR_ENTRIES(report);
    bool recovered = false;
    if (report->status == FTM_STATUS_NO_VALID_MSMT && ftm_failure_recover) {
        count = vendor_count = MAX_ENTRIES;
        recovered = ftm_failure_recover(report, entries, &count, vendors, &vendor_count);
        if (recovered) ESP_LOGI("ftm_endpoint", "FTMRETAIN,%u,%u,%u", reports, count, vendor_count);
        else count = vendor_count = 0;
    }
    if ((!recovered && report->status != FTM_STATUS_SUCCESS) || !count || count > MAX_ENTRIES || vendor_count > MAX_ENTRIES) {
        esp_wifi_ftm_get_report(NULL, 0);
        esp_wifi_ftm_get_vendor_data(NULL, 0);
        ESP_LOGI("ftm_endpoint", "FTMRX,%u,%u,%u,%u,0", reports, report->status, count, vendor_count);
        return true;
    }
    memset(paired, 0, sizeof(paired));
    if (!recovered) {
        memset(entries, 0, sizeof(entries));
        memset(vendors, 0, sizeof(vendors));
        esp_err_t report_status = esp_wifi_ftm_get_report(entries, count);
        esp_err_t vendor_status = esp_wifi_ftm_get_vendor_data(vendors, vendor_count);
        if (report_status != ESP_OK || vendor_status != ESP_OK) return true;
    }
    unsigned matches = 0, mismatches = 0;
    for (unsigned index = 0; index < count; ++index) {
        if (!entries[index].dlog_token || !entries[index].t1 || !entries[index].t2 ||
            entries[index].t3 <= entries[index].t2 || entries[index].t1 > REMOTE_MASK ||
            entries[index].t4 > REMOTE_MASK) continue;
        unsigned found = 0;
        for (unsigned vendor = 0; vendor < vendor_count; ++vendor) {
            if (vendors[vendor].dialog_token != entries[index].dlog_token) continue;
            ftm_follow_up_fields_t decoded;
            if (!ftm_follow_up_parse(vendors[vendor].vendor_ie, vendors[vendor].vendor_ie_len, &decoded)) {
                ++mismatches;
                continue;
            }
            static bool reported_wire_header;
            if (!reported_wire_header) {
                const uint8_t *wire = vendors[vendor].vendor_ie + 6;
                ESP_LOGI("ftm_endpoint", "FTMWIRE,%u,%u,%u,%u,%u,%u,%u",
                         wire[1], wire[5], wire[16], wire[17], wire[18], wire[19], wire[32]);
                reported_wire_header = true;
            }
            int64_t correction_ns = decoded.correction_scaled / 65536;
            if (correction_ns < -2000000000 || correction_ns > 2000000000 ||
                decoded.origin_ns > INT64_MAX - INT64_C(3000000000) ||
                decoded.origin_ns + correction_ns < 0) continue;
            fields[index] = decoded;
            ++found;
        }
        paired[index] = found == 1;
        matches += paired[index];
    }
    ESP_LOGI("ftm_endpoint", "FTMRX,%u,%u,%u,%u,%u,%u", reports, report->status, count, vendor_count, matches, mismatches);
    if (matches < 2) return true;
    unsigned first = 0, last = count - 1;
    while (!paired[first]) ++first;
    while (!paired[last]) --last;
    if (!report_source_consistent(first, last)) return true;
    uint64_t remote_span = (entries[last].t1 - entries[first].t1) & REMOTE_MASK;
    if (entries[last].t2 <= entries[first].t2 || remote_span < UINT64_C(500000000) ||
        remote_span > UINT64_C(1500000000000)) return true;
    uint64_t local_span = entries[last].t2 - entries[first].t2;
    double neighbor_rate = (double)remote_span / local_span;
    if (!isfinite(neighbor_rate) || fabs(neighbor_rate - 1) > .001) return true;
#if CONFIG_FTM_ENDPOINT_PAIR_SHADOW || CONFIG_FTM_ENDPOINT_PAIR_SELECTION
    ftm_pair_selection_t independent;
    ftm_pair_selection_init(&independent);
#endif
    int best = -1;
    double minimum_rtt = 1e12;
    double lowest_rtt = 1e12, highest_rtt = -1e12;
    for (unsigned index = 0; index < count; ++index) {
        if (!paired[index]) continue;
        uint64_t response_ps = (entries[index].t4 - entries[index].t1) & REMOTE_MASK;
        uint64_t turnaround_ps = entries[index].t3 - entries[index].t2;
        if (response_ps > UINT64_C(1000000000) || turnaround_ps > UINT64_C(1000000000)) continue;
        double rtt = response_ps - turnaround_ps * neighbor_rate;
        if (rtt < lowest_rtt) lowest_rtt = rtt;
        if (rtt > highest_rtt) highest_rtt = rtt;
#if CONFIG_FTM_ENDPOINT_SIGNED_RTT_EXPERIMENT
        if (rtt < -25000 || rtt > 2000000) continue;
#else
        if (rtt < 0 || rtt > 2000000) continue;
#endif
#if CONFIG_FTM_ENDPOINT_PAIR_SHADOW || CONFIG_FTM_ENDPOINT_PAIR_SELECTION
        ftm_pair_selection_add(&independent, index, entries[index].t1,
            entries[index].t2, entries[index].t3, entries[index].t4,
            entries[first].t1, entries[first].t2, neighbor_rate);
#endif
        if (rtt < minimum_rtt) { minimum_rtt = rtt; best = index; }
    }
    if (reports % 8 == 0) ESP_LOGI("ftm_endpoint", "FTMQUALITY,%u,%" PRIu64 ",%.6f,%.3f,%.3f,%d",
        reports, remote_span, (neighbor_rate - 1) * 1e6, lowest_rtt / 1000, highest_rtt / 1000, best);
    if (best < 0) return true;
    ftm_local_clock_snapshot_t map;
    int64_t local_ns;
    if (!ftm_local_clock_snapshot(&map) || !acquisition_generation ||
        !ftm_local_clock_convert(&map, acquisition_generation, entries[best].t2,
                                ptp_clock_local_ns(), &local_ns)) return true;
    double reference_rate = 1 + fields[best].cumulative_rate_offset / 2199023255552.0;
    int64_t reference_ns = fields[best].origin_ns + fields[best].correction_scaled / 65536 +
        (int64_t)llround(minimum_rtt * reference_rate / 2000);
    ptp_clock_affine_t clock;
    if (!ptp_clock_sw_snapshot(&clock)) return true;
    int64_t error_ns = reference_ns - ptp_clock_affine_now(&clock, local_ns);
#if CONFIG_FTM_ENDPOINT_PAIR_SHADOW || CONFIG_FTM_ENDPOINT_PAIR_SELECTION
    if (independent.forward < 0 || independent.reverse < 0) return true;
#if CONFIG_FTM_ENDPOINT_PAIR_SELECTION
    bool compare_pairs = true;
#else
    bool compare_pairs = reports % 8 == 0;
#endif
    if (compare_pairs) {
        unsigned forward = independent.forward;
        int64_t alternate_local;
        double alternate_rtt = independent.forward_ps + independent.reverse_ps;
        double alternate_rate = 1 + fields[forward].cumulative_rate_offset / 2199023255552.0;
        if (ftm_local_clock_convert(&map, acquisition_generation, entries[forward].t2,
                                   ptp_clock_local_ns(), &alternate_local)) {
            int64_t alternate_reference = fields[forward].origin_ns +
                fields[forward].correction_scaled / 65536 +
                (int64_t)llround(alternate_rtt * alternate_rate / 2000);
            int64_t alternate_error = alternate_reference -
                ptp_clock_affine_now(&clock, alternate_local);
#if CONFIG_FTM_ENDPOINT_PAIR_SHADOW
            if (reports % 8 == 0) ESP_LOGI("ftm_endpoint", "FTMPAIR,%u,%d,%d,%d,%.3f,%.3f,%" PRId64,
                reports, best, independent.forward, independent.reverse,
                minimum_rtt / 1000, alternate_rtt / 1000, alternate_error - error_ns);
#endif
#if CONFIG_FTM_ENDPOINT_PAIR_SELECTION
#if CONFIG_FTM_ENDPOINT_SIGNED_RTT_EXPERIMENT
            if (alternate_rtt < -25000 || alternate_rtt > 2000000) return true;
#else
            if (alternate_rtt < 0 || alternate_rtt > 2000000) return true;
#endif
            best = forward;
            minimum_rtt = alternate_rtt;
            reference_rate = alternate_rate;
            local_ns = alternate_local;
            reference_ns = alternate_reference;
            error_ns = alternate_error;
#endif
        } else {
#if CONFIG_FTM_ENDPOINT_PAIR_SELECTION
            return true;
#endif
        }
    }
#endif
    bool suppress_observation = false;
#if CONFIG_FTM_ENDPOINT_LOSS_TEST
    int64_t uptime_us = esp_timer_get_time();
    suppress_observation = uptime_us >= 60000000 && uptime_us < 65000000;
    static bool was_suppressed;
    if (was_suppressed != suppress_observation) {
        ESP_LOGW("ftm_endpoint", "FTMLOSS,%u,%" PRId64, suppress_observation, uptime_us);
        was_suppressed = suppress_observation;
    }
#endif
    if (!suppress_observation && ptp_ftm_discipline_enabled() && observations) {
        clock_observation_t observation = {
            .local_ns = local_ns, .reference_ns = reference_ns,
            .received_us = esp_timer_get_time(), .association = association_generation,
            .mapping = map.generation, .time_base = fields[best].time_base,
            .domain = fields[best].domain, .log_interval = fields[best].log_interval,
        };
        memcpy(observation.source_port, fields[best].source_port, 10);
        if (xQueueSend(observations, &observation, 0) != pdTRUE)
            ESP_LOGW("ftm_endpoint", "clock observation queue full");
    }
    ESP_LOGI("ftm_endpoint", "FTMOBS,%u,%u,%" PRId64 ",%" PRId64 ",%" PRId64 ",%.3f,%.6f,%u",
        reports, entries[best].dlog_token, local_ns, reference_ns, error_ns,
        minimum_rtt / 1000, (neighbor_rate * reference_rate - 1) * 1e6, map.uncertainty_ns);
    return true;
}
