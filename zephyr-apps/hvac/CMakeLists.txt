# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
# Include common module manually
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/../common/net)
add_subdirectory(${CMAKE_CURRENT_SOURCE_DIR}/../common/net net_lib)
project(hvac)

# Add source files
target_sources(app PRIVATE src/main.c)

# Link with the network module
target_link_libraries(app PRIVATE ac_net) 