/*
 * Copyright (c) 2024
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef TELEMATICS_H
#define TELEMATICS_H

#include <zephyr/kernel.h>
#include <zephyr/net/socket.h>
#include <zephyr/drivers/can.h>
#include <stdbool.h>

/* Message structure for queueing messages between threads */
struct telematics_msg {
    uint32_t can_id;
    uint8_t data[8];
    uint8_t dlc;
    bool is_can_to_internet;  /* true if message is from CAN to internet */
};

/* Telematics gateway state */
struct telematics_data {
    bool initialized;
    bool tcp_connected;
    int server_socket;
    int tcp_socket;
    const struct device *can_dev;
    struct k_msgq *can_tx_queue;  /* Pointer to static message queue */
    struct k_msgq *tcp_tx_queue;  /* Pointer to static message queue */
    
    struct k_thread tcp_accept_rx_thread;
    struct k_thread tcp_tx_thread;
    struct k_thread can_tx_thread;
    
    k_tid_t tcp_accept_rx_thread_id;
    k_tid_t tcp_tx_thread_id;
    k_tid_t can_tx_thread_id;
};

/* Function declarations */
void start_telematics(void);
void stop_telematics(void);
bool is_can_id_allowed(uint32_t can_id, bool is_can_to_internet);

#endif /* TELEMATICS_H */ 