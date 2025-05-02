/*
 * Copyright (c) 2024
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <string.h>
#include <stdio.h>
#include <zephyr/drivers/can.h>
#include <signal.h>

#include "lighting.h"
#include "can_ids.h"

LOG_MODULE_REGISTER(lighting_ecu, LOG_LEVEL_INF);

struct lighting_data lighting_data;

/* Work items for periodic updates */
static struct k_work_delayable blinker_work;
static struct k_work_delayable status_work;
static const struct device *can_dev;

/* Flag to indicate shutdown requested */
static volatile sig_atomic_t running = 1;

/* Signal handler */
static void signal_handler(int sig)
{
    LOG_INF("Signal %d received, shutting down...", sig);
    running = 0;
}

/* CAN standard ID mask if not defined */
#ifndef CAN_STD_ID_MASK
#define CAN_STD_ID_MASK     0x7FF
#endif

/* Forward declaration of CAN receiver callback */
static void can_receiver_thread(const struct device *dev, struct can_frame *frame, void *user_data);

static void send_can_message(uint32_t id, uint8_t *msg_data, size_t len)
{
    struct can_frame frame;
    int ret;

    /* Prepare CAN frame */
    frame.id = id & CAN_STD_ID_MASK;  /* Ensure ID is within standard CAN range */
    frame.flags = 0;                   /* Standard CAN frame */
    frame.dlc = len > CAN_MAX_DLC ? CAN_MAX_DLC : len;
    memcpy(frame.data, msg_data, frame.dlc);

    /* Send frame */
    ret = can_send(can_dev, &frame, K_MSEC(100), NULL, NULL);
    if (ret != 0) {
        LOG_ERR("Failed to send CAN frame (err %d)", ret);
    } else {
        LOG_DBG("Sent CAN frame ID 0x%x, len %d", id, frame.dlc);
    }
}

static void send_status_update(void)
{
    uint8_t data[3];

    data[0] = lighting_data.headlight_state;
    data[1] = lighting_data.blinker_state;
    data[2] = lighting_data.hazard_state;

    /* Send status update via CAN */
    send_can_message(LIGHTING_STATUS_ID, data, sizeof(data));

    LOG_INF("Status - Headlights: %d, Blinker: %d, Hazard: %d",
            lighting_data.headlight_state,
            lighting_data.blinker_state,
            lighting_data.hazard_state);
}

static void status_update(struct k_work *work)
{
    /* Send status update */
    send_status_update();

    /* Schedule next update (2 second interval) */
    k_work_schedule(&status_work, K_MSEC(2000));
}

static void blinker_update(struct k_work *work)
{
    static uint8_t blink_state = 0;

    if (lighting_data.hazard_state) {
        /* Hazard lights override blinkers */
        blink_state = !blink_state;
        LOG_INF("Hazard lights: %s", blink_state ? "ON" : "OFF");
    } else if (lighting_data.blinker_state == BLINKER_LEFT) {
        /* Left blinker */
        blink_state = !blink_state;
        LOG_INF("Left blinker: %s", blink_state ? "ON" : "OFF");
    } else if (lighting_data.blinker_state == BLINKER_RIGHT) {
        /* Right blinker */
        blink_state = !blink_state;
        LOG_INF("Right blinker: %s", blink_state ? "ON" : "OFF");
    } else {
        /* No blinking state active */
        blink_state = 0;
    }

    /* Send status update */
    send_status_update();

    /* Schedule next update (2 second interval) */
    k_work_schedule(&blinker_work, K_MSEC(2000));
}

static void setup_can(void)
{
    /* Get CAN device */
    can_dev = device_get_binding("my_can");
    if (!can_dev) {
        LOG_ERR("Failed to get CAN device binding");
        return;
    }
    
    if (!device_is_ready(can_dev)) {
        LOG_ERR("CAN device is not ready");
        return;
    }

    /* Start CAN device */
    int ret = can_start(can_dev);
    if (ret != 0) {
        LOG_ERR("Failed to start CAN device (err %d)", ret);
        return;
    }

    /* Set up filter for lighting control messages */
    struct can_filter filter = {
        .id = LIGHTING_CONTROL_ID,
        .mask = CAN_STD_ID_MASK,
        .flags = 0  /* Changed from CAN_FILTER_IDE to 0 for standard frames */
    };

    LOG_INF("Adding CAN filter for ID 0x%x with mask 0x%x", filter.id, filter.mask);
    ret = can_add_rx_filter(can_dev, can_receiver_thread, NULL, &filter);
    if (ret < 0) {
        LOG_ERR("Failed to add CAN filter (err %d)", ret);
        /* Continue anyway, we'll receive all messages */
    } else {
        LOG_INF("CAN filter added successfully with ID %d", ret);
    }
    
    LOG_INF("CAN setup complete");
}

static void can_receiver_thread(const struct device *dev, struct can_frame *frame, void *user_data)
{
    ARG_UNUSED(dev);
    ARG_UNUSED(user_data);

    /* Print detailed CAN frame information */
    LOG_INF("Received CAN frame:");
    LOG_INF("  ID: 0x%x", frame->id);
    LOG_INF("  Flags: 0x%x", frame->flags);
    LOG_INF("  DLC: %d", frame->dlc);
    LOG_INF("  Data: [%d, %d, %d]", frame->data[0], frame->data[1], frame->data[2]);

    /* Process frame */
    if (frame->id == LIGHTING_CONTROL_ID) {
        lighting_data.headlight_state = frame->data[0];
        lighting_data.blinker_state = frame->data[1];
        lighting_data.hazard_state = frame->data[2];
        
        LOG_INF("Received lighting control - Headlights: %d, Blinker: %d, Hazard: %d",
                lighting_data.headlight_state,
                lighting_data.blinker_state,
                lighting_data.hazard_state);
    }
}

void start_lighting(void)
{
    /* Initialize lighting data */
    memset(&lighting_data, 0, sizeof(lighting_data));
    lighting_data.initialized = true;

    /* Setup CAN */
    setup_can();

    /* Initialize work queues */
    k_work_init_delayable(&blinker_work, blinker_update);
    k_work_init_delayable(&status_work, status_update);
    
    /* Start periodic updates */
    k_work_schedule(&blinker_work, K_MSEC(500));  /* Blinker updates every 500ms */
    k_work_schedule(&status_work, K_MSEC(2000));  /* Status updates every 2 seconds */

    /* Send initial status update */
    send_status_update();
}

void stop_lighting(void)
{
    /* Clean up resources */
    k_work_cancel_delayable(&blinker_work);
    k_work_cancel_delayable(&status_work);
    if (can_dev) {
        can_stop(can_dev);
    }
    LOG_INF("Lighting ECU Application stopped successfully");
}

int main(void)
{
    LOG_INF("Lighting ECU Application");

    /* Set up signal handling */
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    start_lighting();
    
    /* Main loop - wait for signal to exit */
    while (running) {
        k_sleep(K_MSEC(100));
    }
    
    /* Clean shutdown */
    LOG_INF("Lighting ECU Application preparing to shutdown...");
    stop_lighting();
    
    return 0;
}