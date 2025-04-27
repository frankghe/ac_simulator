/*
 * Copyright (c) 2024
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef COMMON_H
#define COMMON_H

#include <zephyr/kernel.h>
#include <zephyr/net/socket.h>
#include <zephyr/net/net_ip.h>

#define MY_PORT CONFIG_HVAC_PORT
#if defined(CONFIG_NET_SOCKETS_SOCKOPT_TLS) || defined(CONFIG_NET_TCP) || \
    defined(CONFIG_COVERAGE_GCOV)
#define STACK_SIZE 4096
#else
#define STACK_SIZE 2048
#endif

#if defined(CONFIG_NET_TC_THREAD_COOPERATIVE)
#define THREAD_PRIORITY K_PRIO_COOP(CONFIG_NUM_COOP_PRIORITIES - 1)
#else
#define THREAD_PRIORITY K_PRIO_PREEMPT(8)
#endif

#define MAX_MSG_SIZE 256
#define STATS_TIMER 60 /* How often to print statistics (in seconds) */

/* Thermal model parameters */
#define AMBIENT_TEMP 25.0f
#define HVAC_MASS 100.0f
#define HEAT_TRANSFER_COEFF 0.1f

#if defined(CONFIG_USERSPACE)
#include <zephyr/app_memory/app_memdomain.h>
extern struct k_mem_partition app_partition;
extern struct k_mem_domain app_domain;
#define APP_BMEM K_APP_BMEM(app_partition)
#define APP_DMEM K_APP_DMEM(app_partition)
#else
#define APP_BMEM
#define APP_DMEM
#endif

struct hvac_data {
    int sock;
    char recv_buffer[MAX_MSG_SIZE];
    uint32_t counter;
    atomic_t bytes_received;
    struct k_work_delayable stats_print;
    bool connected;
    
    /* Thermal model state */
    float cabin_temp;     // Current cabin temperature
    float target_temp;    // Target temperature from AC
    uint8_t fan_speed;    // Current fan speed
    bool ac_power;        // AC power state
    float external_temp;  // External temperature (simulated)
};

extern struct hvac_data hvac_data;

/* Thread stack and data */
K_THREAD_STACK_DEFINE(hvac_stack, STACK_SIZE);
extern struct k_thread hvac_thread_data;

void start_hvac(void);
void stop_hvac(void);

#endif /* COMMON_H */ 