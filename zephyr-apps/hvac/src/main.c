/*
 * Copyright (c) 2024
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <zephyr/drivers/can.h>
#include <signal.h>

#include "hvac.h"
#include "can_ids.h"

LOG_MODULE_REGISTER(hvac_model, LOG_LEVEL_DBG);

struct hvac_data hvac_data;

/* Work items for periodic updates */
static struct k_work_delayable temp_calc_work;
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

/* Send status update via CAN */
static void send_status_update(void)
{
    uint8_t data[8] = {
        (uint8_t)(hvac_data.cabin_temp * 2),    // Current temp * 2
        (uint8_t)(hvac_data.external_temp * 2), // External temp * 2
        hvac_data.ac_on,                        // AC power state
        hvac_data.fan_speed,                    // Fan speed
        0, 0, 0, 0                              // Reserved
    };
    
    send_can_message(HVAC_STATUS_ID, data, sizeof(data));
    
    LOG_INF("Status - Cabin: %.1f°C, External: %.1f°C, AC: %d, Fan: %d",
            (double)hvac_data.cabin_temp,
            (double)hvac_data.external_temp,
            hvac_data.ac_on,
            hvac_data.fan_speed);
}

/* CAN receiver callback */
static void can_receiver_thread(const struct device *dev, struct can_frame *frame, void *user_data)
{
    ARG_UNUSED(dev);
    ARG_UNUSED(user_data);

    /* Print detailed CAN frame information */
    LOG_DBG("Received CAN frame:");
    LOG_DBG("  ID: 0x%x", frame->id);
    LOG_DBG("  Flags: 0x%x", frame->flags);
    LOG_DBG("  DLC: %d", frame->dlc);
    LOG_DBG("  Data: [%d, %d, %d]", frame->data[0], frame->data[1], frame->data[2]);

    /* Handle messages from ac_panel (AC Control GUI) */
    if (frame->id == HVAC_AC_STATUS_ID) {  // AC status ID
        hvac_data.ac_on = frame->data[0];
        hvac_data.fan_speed = frame->data[1];
        // mode is in frame->data[2] but not used by hvac model
        
        LOG_INF("Received AC status - Power: %d, Fan: %d",
                hvac_data.ac_on,
                hvac_data.fan_speed);
    }
    else if (frame->id == HVAC_POWER_STATUS_ID) {  // Power status ID
        hvac_data.ac_on = frame->data[0];
        
        LOG_INF("Received AC power - State: %d",
                hvac_data.ac_on);
    }
    else if (frame->id == HVAC_CONTROL_ID) {  // Legacy AC control message
        hvac_data.ac_on = frame->data[0];
        hvac_data.target_temp = (float)frame->data[1] / 2.0f;
        hvac_data.fan_speed = frame->data[2];
        
        LOG_INF("Received legacy AC control - Power: %d, Target: %.1f°C, Fan: %d",
                hvac_data.ac_on,
                (double)hvac_data.target_temp,
                hvac_data.fan_speed);
    }
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

    // Add a filter for standard CAN IDs
    struct can_filter std_filter = {
        .id = 0,    // Match any standard ID
        .mask = 0,  // Don't care about any bits
        .flags = 0  // This is a filter for standard IDs
    };

    LOG_INF("Attaching CAN RX filter for all standard messages.");
    ret = can_add_rx_filter(can_dev, can_receiver_thread, NULL, &std_filter);
    if (ret < 0) {
        LOG_ERR("Failed to add standard CAN RX filter (err %d). May not receive standard CAN messages.", ret);
        // Optionally return here if this is critical
    }

    // Add a filter for extended CAN IDs
    struct can_filter ext_filter = {
        .id = 0,    // Match any extended ID
        .mask = 0,  // Don't care about any bits
        .flags = CAN_FILTER_IDE // This is a filter for extended IDs
    };

    LOG_INF("Attaching CAN RX filter for all extended messages.");
    ret = can_add_rx_filter(can_dev, can_receiver_thread, NULL, &ext_filter);
    if (ret < 0) {
        LOG_ERR("Failed to add extended CAN RX filter (err %d). May not receive extended CAN messages.", ret);
        // Optionally return here if this is critical
    }
    
    LOG_INF("CAN setup complete, listening for all messages via two filters.");
}

/* Status update work handler */
static void status_update(struct k_work *work)
{
    /* Send status update */
    send_status_update();

    /* Schedule next update (2 second interval) */
    k_work_schedule(&status_work, K_MSEC(2000));
}

/* Temperature calculation work handler */
static void calculate_temperature(struct k_work *work)
{
    if (hvac_data.ac_on) {
        // If AC is on but no target temp is set, use default cooling temp
        if (hvac_data.target_temp == AMBIENT_TEMP) {
            hvac_data.target_temp = AMBIENT_TEMP - 3.0f; // Default cooling target
            LOG_INF("Using default cooling target: %.1f°C", (double)hvac_data.target_temp);
        }
        
        // Calculate heat transfer
        float temp_diff = hvac_data.target_temp - hvac_data.cabin_temp;
        // Use fan speed with the enhanced coefficient from hvac.h
        float cooling_power = hvac_data.fan_speed * HEAT_TRANSFER_COEFF;
        
        // Simple hvac model
        float heat_flow = cooling_power * temp_diff;
        float cabin_temp_change = heat_flow / HVAC_MASS;
        
        LOG_DBG("AC calculation: diff=%.2f, power=%.2f, flow=%.4f, change=%.4f°C",
                (double)temp_diff, (double)cooling_power, (double)heat_flow, (double)cabin_temp_change);
        
        hvac_data.cabin_temp += cabin_temp_change;
        
        // Reduced external heat influence when AC is on (AC recirculates internal air)
        // Modern cars with AC on reduce outside air influence significantly
        float external_factor = 0.003f; // Further reduced external influence when AC is on
        float external_influence = (hvac_data.external_temp - hvac_data.cabin_temp) * external_factor;
        hvac_data.cabin_temp += external_influence;
        
        LOG_DBG("External influence: %.4f°C", (double)external_influence);
    } else {
        // When AC is off, cabin temperature slowly approaches external temperature
        // Higher rate when AC is off (windows might be open, normal air exchange)
        float temp_change = (hvac_data.external_temp - hvac_data.cabin_temp) * 0.03f;
        hvac_data.cabin_temp += temp_change;
        LOG_DBG("AC off: cabin temp changing by %.4f°C toward external", (double)temp_change);
    }
    
    // Log current state
    LOG_INF("Thermal - Cabin: %.1f°C, Target: %.1f°C, External: %.1f°C",
            (double)hvac_data.cabin_temp,
            (double)hvac_data.target_temp,
            (double)hvac_data.external_temp);
            
    // Schedule next update
    k_work_schedule(&temp_calc_work, K_MSEC(1000));
}

void start_ac_ecu(void)
{
    // Initialize hvac data
    memset(&hvac_data, 0, sizeof(hvac_data));
    hvac_data.cabin_temp = AMBIENT_TEMP;
    hvac_data.target_temp = AMBIENT_TEMP;
    hvac_data.fan_speed = 1;
    hvac_data.ac_on = false;
    hvac_data.external_temp = AMBIENT_TEMP + 5.0f;  // Slightly warmer outside
    hvac_data.initialized = true;

    // Setup CAN
    setup_can();

    // Initialize work queues
    k_work_init_delayable(&temp_calc_work, calculate_temperature);
    k_work_init_delayable(&status_work, status_update);
    
    // Start periodic updates
    k_work_schedule(&temp_calc_work, K_MSEC(1000));  // Temperature updates every 1 second
    k_work_schedule(&status_work, K_MSEC(2000));     // Status updates every 2 seconds

    // Send initial status update
    send_status_update();
}

void stop_hvac(void)
{
    // Clean up resources
    k_work_cancel_delayable(&temp_calc_work);
    k_work_cancel_delayable(&status_work);
    if (can_dev) {
        can_stop(can_dev);
    }
    LOG_INF("HVAC ECU Application stopped successfully");
}

int main(void)
{
    LOG_INF("HVAC ECU Application");

    /* Set up signal handling */
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    start_ac_ecu();
    
    /* Main loop - wait for signal to exit */
    while (running) {
        k_sleep(K_MSEC(100));
    }
    
    /* Clean shutdown */
    LOG_INF("HVAC ECU Application preparing to shutdown...");
    stop_hvac();
    
    return 0;
} 