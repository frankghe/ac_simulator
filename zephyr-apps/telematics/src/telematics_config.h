/*
 * Copyright (c) 2024
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef TELEMATICS_CONFIG_H
#define TELEMATICS_CONFIG_H

#include "can_ids.h"

/* CAN IDs allowed to be received from internet and sent on CAN */
#define ALLOWED_INTERNET_TO_CAN_IDS { \
    HVAC_CONTROL_ID,                 \
    HVAC_AC_STATUS_ID,               \
    HVAC_POWER_STATUS_ID,            \
    /* Add more IDs as needed */     \
}

/* CAN IDs allowed to be received from CAN and sent over internet */
#define ALLOWED_CAN_TO_INTERNET_IDS { \
    HVAC_STATUS_ID,                  \
    /* Add more IDs as needed */     \
}

/* TCP server configuration */
#define TCP_SERVER_PORT 8080
#define TCP_MAX_CONNECTIONS 1
#define TCP_RX_BUFFER_SIZE 1024
#define TCP_TX_BUFFER_SIZE 1024

/* Message queue sizes */
#define CAN_TX_QUEUE_SIZE 32
#define TCP_TX_QUEUE_SIZE 32

/* Thread stack sizes */
#define TCP_THREAD_STACK_SIZE 2048
#define CAN_THREAD_STACK_SIZE 2048

/* Thread priorities */
#define TCP_THREAD_PRIORITY 5
#define CAN_THREAD_PRIORITY 5

#endif /* TELEMATICS_CONFIG_H */ 