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

#include "hvac.h"

LOG_MODULE_REGISTER(hvac_model, LOG_LEVEL_INF);

struct hvac_data hvac_data;

/* Work item for periodic temperature calculation */
static struct k_work_delayable temp_calc_work;

static void send_can_message(uint32_t id, uint8_t *msg_data, size_t len)
{
    // Create raw frame in the format: [4 bytes ID][1 byte len][data bytes]
    uint8_t raw_frame[13]; // Max 4+1+8 bytes
    size_t data_len = len > 8 ? 8 : len; // Limit to 8 bytes max
    
    // Add CAN ID (4 bytes, network byte order)
    raw_frame[0] = (id >> 24) & 0xFF;
    raw_frame[1] = (id >> 16) & 0xFF;
    raw_frame[2] = (id >> 8) & 0xFF;
    raw_frame[3] = id & 0xFF;
    
    // Add data length (1 byte)
    raw_frame[4] = data_len;
    
    // Add data
    for (int i = 0; i < data_len; i++) {
        raw_frame[i + 5] = msg_data[i];
    }
    
    // Calculate total frame size
    size_t frame_size = 5 + data_len;
    
    // Send the raw frame
    ac_net_send(&hvac_data.net, raw_frame, frame_size);
    
    LOG_INF("Sent raw CAN frame: ID=0x%x, len=%d", id, data_len);
}

static void handle_network_message(const char *msg, size_t len)
{
    // For raw frame handling, we need at least 5 bytes (4 for ID, 1 for length)
    if (len < 5) {
        LOG_ERR("Received message too short: %d bytes", len);
        return;
    }
    
    // Print raw message bytes for debugging
    LOG_INF("Received raw CAN frame: %d bytes", len);
    
    // Extract CAN ID (first 4 bytes)
    uint32_t msg_id = 0;
    msg_id = ((uint32_t)((uint8_t)msg[0]) << 24) | 
             ((uint32_t)((uint8_t)msg[1]) << 16) | 
             ((uint32_t)((uint8_t)msg[2]) << 8) | 
             (uint32_t)((uint8_t)msg[3]);
    
    // Extract data length (next byte)
    uint8_t data_len = (uint8_t)msg[4];
    
    // Verify we have enough data
    if (len < 5 + data_len) {
        LOG_ERR("Incomplete CAN frame: expected %d bytes, got %d", 5 + data_len, len);
        return;
    }
    
    // Extract data bytes
    uint8_t msg_data[8] = {0};
    for (int i = 0; i < data_len && i < 8; i++) {
        msg_data[i] = (uint8_t)msg[5 + i];
    }
    
    LOG_INF("Decoded CAN frame - ID: 0x%x, Length: %d", msg_id, data_len);
    
    // Handle messages from ac_panel (AC Control GUI)
    if (msg_id == 0xAC1) {  // AC status ID
        hvac_data.ac_on = msg_data[0];
        hvac_data.fan_speed = msg_data[1];
        // mode is in msg_data[2] but not used by hvac model
        
        LOG_INF("Received AC status - Power: %d, Fan: %d",
                hvac_data.ac_on,
                hvac_data.fan_speed);
    }
    else if (msg_id == 0xAC2) {  // Power status ID
        hvac_data.ac_on = msg_data[0];
        
        LOG_INF("Received AC power - State: %d",
                hvac_data.ac_on);
    }
    else if (msg_id == 0x123) {  // Legacy AC control message
        hvac_data.ac_on = msg_data[0];
        hvac_data.target_temp = (float)msg_data[1] / 2.0f;
        hvac_data.fan_speed = msg_data[2];
        
        LOG_INF("Received legacy AC control - Power: %d, Target: %.1f°C, Fan: %d",
                hvac_data.ac_on,
                (double)hvac_data.target_temp,
                hvac_data.fan_speed);
    }
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
        
        LOG_INF("AC calculation: diff=%.2f, power=%.2f, flow=%.4f, change=%.4f°C",
                (double)temp_diff, (double)cooling_power, (double)heat_flow, (double)cabin_temp_change);
        
        hvac_data.cabin_temp += cabin_temp_change;
        
        // Reduced external heat influence when AC is on (AC recirculates internal air)
        // Modern cars with AC on reduce outside air influence significantly
        float external_factor = 0.003f; // Further reduced external influence when AC is on
        float external_influence = (hvac_data.external_temp - hvac_data.cabin_temp) * external_factor;
        hvac_data.cabin_temp += external_influence;
        
        LOG_INF("External influence: %.4f°C", (double)external_influence);
    } else {
        // When AC is off, cabin temperature slowly approaches external temperature
        // Higher rate when AC is off (windows might be open, normal air exchange)
        float temp_change = (hvac_data.external_temp - hvac_data.cabin_temp) * 0.03f;
        hvac_data.cabin_temp += temp_change;
        LOG_INF("AC off: cabin temp changing by %.4f°C toward external", (double)temp_change);
    }
    
    // Send temperature update via TCP (legacy format)
    uint8_t data[8] = {
        (uint8_t)(hvac_data.cabin_temp * 2),    // Current temp * 2
        (uint8_t)(hvac_data.external_temp * 2), // External temp * 2
        0, 0, 0, 0, 0, 0  // Reserved
    };
    
    // Send legacy format for backward compatibility
    send_can_message(0x125, data, sizeof(data));
    
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
    int ret;

    // Initialize hvac data
    memset(&hvac_data, 0, sizeof(hvac_data));
    hvac_data.cabin_temp = AMBIENT_TEMP;
    hvac_data.target_temp = AMBIENT_TEMP;
    hvac_data.fan_speed = 1;
    hvac_data.ac_on = false;
    hvac_data.external_temp = AMBIENT_TEMP + 5.0f;  // Slightly warmer outside

    // Initialize network
    ret = ac_net_init(&hvac_data.net, hvac_stack,
                      K_THREAD_STACK_SIZEOF(hvac_stack),
                      handle_network_message);
    if (ret < 0) {
        LOG_ERR("Failed to initialize network: %d", ret);
        return;
    }

    // Start network
    ret = ac_net_start(&hvac_data.net, CONFIG_HVAC_PORT, CONFIG_NET_CONFIG_PEER_IPV4_ADDR);
    if (ret < 0) {
        LOG_ERR("Failed to start network: %d", ret);
        return;
    }

    // Initialize work queue for temperature calculation
    k_work_init_delayable(&temp_calc_work, calculate_temperature);
    k_work_schedule(&temp_calc_work, K_MSEC(1000));
}

void stop_hvac(void)
{
    ac_net_stop(&hvac_data.net);
    k_work_cancel_delayable(&temp_calc_work);
}

int main(void)
{
    LOG_INF("AC ECU Application");

    start_ac_ecu();

    return 0;
} 