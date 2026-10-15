# Build root for the ESP-AVB-Bridge coprocessor (C6) firmware: the
# esp_hosted component's coprocessor side, with esp_hosted_avb and the
# FTM probes from components/.

cmake_minimum_required(VERSION 3.16)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(avb_bridge_coprocessor)
