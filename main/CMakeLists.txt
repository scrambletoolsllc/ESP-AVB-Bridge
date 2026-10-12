set(srcs "avb_bridge_main.c")

if(CONFIG_AVB_BRIDGE_PERF_TEST_MODE)
    list(APPEND srcs "avb_bridge_perf_test.c")
endif()

# The project builds only these and what they require (see the
# top-level CMakeLists.txt), so list everything main includes; esp_avb's
# avb.h, reached through avbbridge.h, includes the I2C and I2S drivers,
# and the perf test uses NVS.
idf_component_register(SRCS ${srcs}
                       PRIV_REQUIRES esp_avb esp_ptp esp_eth esp_netif esp_event
                                     esp_timer esp_wifi esp_driver_gpio
                                     esp_driver_i2c esp_driver_i2s esp_rom heap
                                     log nvs_flash espressif__ip101)
