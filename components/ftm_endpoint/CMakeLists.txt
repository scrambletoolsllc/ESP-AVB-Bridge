set(endpoint_sources)
if(CONFIG_FTM_ENDPOINT)
    list(APPEND endpoint_sources "ftm_endpoint.c" "ftm_discipline.c")
endif()
idf_component_register(SRCS ${endpoint_sources} PRIV_REQUIRES esp_wifi esp_ptp
    ftm_local_clock ftm_follow_up esp_timer WHOLE_ARCHIVE)
