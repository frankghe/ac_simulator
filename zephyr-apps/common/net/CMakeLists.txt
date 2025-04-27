# SPDX-License-Identifier: Apache-2.0

#cmake_minimum_required(VERSION 3.20.0)

#find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
#project(ac_net)

message(STATUS ">>> [common] included and building")

# Create a library for the network module
zephyr_library_named(ac_net)
zephyr_library_sources(ac_net.c)
zephyr_library_include_directories(.)
