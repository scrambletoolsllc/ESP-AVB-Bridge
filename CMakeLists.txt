cmake_minimum_required(VERSION 3.16)

# Build only main, what it requires, PSRAM for the heap, and the bench
# probes, whose Kconfig options keep them out of the image unless set.
set(COMPONENTS main esp_psram ftm_clock_probe clock_scope_probe)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(avb_bridge)
