set(probe_sources)
if(CONFIG_FTM_RAW_PROBE)
    list(APPEND probe_sources "ftm_raw_probe.c")
endif()
idf_component_register(SRCS ${probe_sources} INCLUDE_DIRS "include" REQUIRES ftm_clock_model
    PRIV_REQUIRES esp_wifi esp_timer esp_event WHOLE_ARCHIVE)
if(CONFIG_FTM_RAW_PROBE)
    target_link_libraries(${COMPONENT_LIB} INTERFACE
        "-Wl,--wrap=esp_wifi_ftm_get_report"
        "-Wl,--wrap=esp_wifi_ftm_initiate_session")
endif()
