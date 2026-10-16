/*
 * Copyright 2026 Scramble Tools
 * License: MIT
 *
 * ESP-AVB-Bridge coprocessor. esp_hosted starts the coprocessor side
 * from its own constructor and esp_hosted_avb registers as one of its
 * features, so this only provides what both expect from the app.
 */

#include "sdkconfig.h"
#include "driver/uart.h"
#include "driver/uart_vfs.h"
#include "esp_event.h"
#include "nvs_flash.h"

#if CONFIG_ESP_WIFI_ENABLE_WIFI_TX_STATS
#include <inttypes.h>
#include "esp_attr.h"
#include "esp_bit_defs.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_wifi_he.h"
#include "esp_private/esp_wifi_he_private.h"
#include "esp_private/wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define TX_STATS_INTERVAL_MS 10000

static const char *TAG = "tx_stats";

/* Host frames reach esp_wifi through esp_wifi_internal_tx (linked with
 * --wrap). A full TX buffer pool returns ESP_ERR_NO_MEM, and esp-hosted
 * then waits 1 ms and retries the same frame up to its retry limit. */
static volatile uint32_t host_tx_calls;
static volatile uint32_t host_tx_no_mem;
static volatile uint32_t no_mem_run;
static volatile uint32_t no_mem_run_max;

int __real_esp_wifi_internal_tx(wifi_interface_t wifi_if, void *buffer,
                                uint16_t len);

IRAM_ATTR int __wrap_esp_wifi_internal_tx(wifi_interface_t wifi_if,
                                          void *buffer, uint16_t len) {
  int result = __real_esp_wifi_internal_tx(wifi_if, buffer, len);
  host_tx_calls++;
  if (result == ESP_ERR_NO_MEM) {
    host_tx_no_mem++;
    if (++no_mem_run > no_mem_run_max) no_mem_run_max = no_mem_run;
  } else {
    no_mem_run = 0;
  }
  return result;
}

static uint32_t take_count(volatile uint32_t *count) {
  return __atomic_exchange_n(count, 0, __ATOMIC_RELAXED);
}

static esp_test_tx_statistics_t tx_stats;
static esp_test_tx_fail_statistics_t tx_fail[TEST_TX_FAIL_MAX];

/* Logs the best effort category, which carries the audio, every interval
 * and clears it, so each line covers one interval. */
static void tx_stats_task(void *context) {
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(TX_STATS_INTERVAL_MS));
    uint32_t calls = take_count(&host_tx_calls);
    uint32_t no_mem = take_count(&host_tx_no_mem);
    uint32_t run_max = take_count(&no_mem_run_max);
    if (!(esp_wifi_get_tx_statistics_ena_acibitmap() & BIT(ESP_WIFI_ACI_BE)))
      continue;
    if (esp_wifi_get_tx_statistics(ESP_WIFI_ACI_BE, &tx_stats, tx_fail) !=
        ESP_OK)
      continue;
    esp_wifi_clr_tx_statistics(ESP_WIFI_ACI_BE);
    uint32_t attempts =
        tx_stats.tb_times + (tx_stats.tx_enable - tx_stats.tb_last);
    uint32_t failures = 0;
    for (int state = TEST_TX_FAIL_RTS; state < TEST_TX_FAIL_MAX; state++)
      failures += tx_fail[state].count;
    ESP_LOGI(TAG,
             "BE ppdu=%" PRIu32 " ok=%" PRIu32 " ack=%" PRIu32 " ba=%" PRIu32
             " retry=%" PRIu32 " fail=%" PRIu32 " coll=%" PRIu32
             " tmo=%" PRIu32 " nomem=%" PRIu32 " rtt=%" PRIu32 "/%" PRIu32
             "/%" PRIu32 "us host=%" PRIu32 "/%" PRIu32 "/%" PRIu32,
             attempts, tx_stats.tx_succ, tx_stats.rx_ack, tx_stats.rx_ba,
             tx_stats.retry_edca, failures, tx_stats.collision,
             tx_stats.timeout, tx_stats.tx_no_mem,
             attempts ? tx_stats.tx_tot_rtt / attempts : 0,
             tx_stats.tx_max_rtt, tx_stats.tx_seq_max_rtt, calls, no_mem,
             run_max);
  }
}

static void enable_tx_stats(void *context, esp_event_base_t base, int32_t id,
                            void *data) {
  esp_wifi_enable_tx_statistics(ESP_WIFI_ACI_BE, true);
}
#endif

/* Console writes go through the UART driver, so a log call copies into
 * the TX buffer and returns instead of spinning until the port sends it.
 * Its RPC task shares a priority with the task that moves host frames to
 * the radio, and each clock probe line held it for 4 to 9 ms. */
static void console_use_driver(void) {
#if CONFIG_ESP_CONSOLE_UART
  if (uart_driver_install(CONFIG_ESP_CONSOLE_UART_NUM,
                          2 * UART_HW_FIFO_LEN(CONFIG_ESP_CONSOLE_UART_NUM),
                          4096, 0, NULL, 0) == ESP_OK)
    uart_vfs_dev_use_driver(CONFIG_ESP_CONSOLE_UART_NUM);
#endif
}

void app_main(void) {
  console_use_driver();
  esp_err_t result = nvs_flash_init();
  if (result == ESP_ERR_NVS_NO_FREE_PAGES ||
      result == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    ESP_ERROR_CHECK(nvs_flash_erase());
    result = nvs_flash_init();
  }
  ESP_ERROR_CHECK(result);
  ESP_ERROR_CHECK(esp_event_loop_create_default());
#if CONFIG_ESP_WIFI_ENABLE_WIFI_TX_STATS
  ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_AP_START,
                                             enable_tx_stats, NULL));
  xTaskCreate(tx_stats_task, "tx_stats", 3072, NULL, 1, NULL);
#endif
}
