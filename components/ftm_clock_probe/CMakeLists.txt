set(probe_requirements esp_timer esp_wifi esp_system ftm_follow_up
    esp_driver_gpio esp_driver_gptimer esp_driver_pcnt esp_hw_support)
if(IDF_TARGET STREQUAL "esp32p4")
    list(APPEND probe_requirements esp_ptp ftm_bridge_clock)
endif()
set(probe_sources)
if(CONFIG_FTM_CLOCK_PROBE)
    list(APPEND probe_sources "ftm_clock_probe.c")
endif()
idf_component_register(SRCS ${probe_sources}
    PRIV_REQUIRES ${probe_requirements} WHOLE_ARCHIVE)

if(CONFIG_FTM_CLOCK_PROBE_EDGE)
    idf_component_get_property(timer_library esp_driver_gptimer COMPONENT_LIB)
    target_sources(${timer_library} PRIVATE "${CMAKE_CURRENT_LIST_DIR}/ftm_timer_pair.c")
    set_source_files_properties("${CMAKE_CURRENT_LIST_DIR}/ftm_timer_pair.c"
        TARGET_DIRECTORY ${timer_library}
        PROPERTIES COMPILE_OPTIONS "-O2")
endif()
