/*
 * Copyright 2026 Scramble Tools
 * License: MIT
 *
 * ESP-AVB-Bridge coprocessor. esp_hosted starts the coprocessor side
 * from its own constructor and esp_hosted_avb registers as one of its
 * features, so this only provides what both expect from the app.
 */

#include "esp_event.h"
#include "nvs_flash.h"

void app_main(void) {
  esp_err_t result = nvs_flash_init();
  if (result == ESP_ERR_NVS_NO_FREE_PAGES ||
      result == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    ESP_ERROR_CHECK(nvs_flash_erase());
    result = nvs_flash_init();
  }
  ESP_ERROR_CHECK(result);
  ESP_ERROR_CHECK(esp_event_loop_create_default());
}
