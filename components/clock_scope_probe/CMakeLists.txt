set(scope_sources)
if(CONFIG_CLOCK_SCOPE_PROBE)
    list(APPEND scope_sources "clock_scope_probe.c")
endif()
idf_component_register(SRCS ${scope_sources}
    PRIV_REQUIRES esp_ptp esp_timer esp_driver_gpio esp_driver_gptimer esp_hw_support
    WHOLE_ARCHIVE)
if(CONFIG_CLOCK_SCOPE_PROBE)
    idf_component_get_property(timer_library esp_driver_gptimer COMPONENT_LIB)
    target_sources(${timer_library} PRIVATE "${CMAKE_CURRENT_LIST_DIR}/scope_capture.c")
    set_source_files_properties("${CMAKE_CURRENT_LIST_DIR}/scope_capture.c"
        TARGET_DIRECTORY ${timer_library}
        PROPERTIES COMPILE_OPTIONS "-O2")
    if(IDF_TARGET STREQUAL "esp32c6")
        target_link_libraries(${timer_library} PRIVATE idf::esp_hal_systimer)
    endif()
endif()
