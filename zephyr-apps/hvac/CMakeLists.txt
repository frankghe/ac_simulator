# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)

# Set board and overlay before finding Zephyr package
set(BOARD native_sim)
set(DTC_OVERLAY_FILE ${CMAKE_CURRENT_SOURCE_DIR}/boards/native_sim.overlay)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(hvac)

# Add include directories
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/../common/net)

# Add source files
target_sources(app PRIVATE src/main.c) 