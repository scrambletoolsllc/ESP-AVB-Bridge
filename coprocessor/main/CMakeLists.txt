idf_component_register(SRCS "app_main.c"
                       PRIV_REQUIRES esp_event esp_wifi nvs_flash)

# With TX statistics on, count host frames refused by a full TX buffer pool.
if(CONFIG_ESP_WIFI_ENABLE_WIFI_TX_STATS)
  target_link_libraries(${COMPONENT_LIB} INTERFACE
                        "-Wl,--wrap=esp_wifi_internal_tx")
endif()
