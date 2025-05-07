/*
 * Copyright (c) 2024
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/net/socket.h>
#include <zephyr/drivers/can.h>
#include <string.h>
#include <signal.h>
#include <errno.h>

#include "telematics.h"
#include "telematics_config.h"
#include "can_ids.h"

LOG_MODULE_REGISTER(telematics, LOG_LEVEL_DBG);

/* Global telematics data */
static struct telematics_data telematics_data;

/* Message queues */
K_MSGQ_DEFINE(can_tx_queue, sizeof(struct telematics_msg), CAN_TX_QUEUE_SIZE, 4);
K_MSGQ_DEFINE(tcp_tx_queue, sizeof(struct telematics_msg), TCP_TX_QUEUE_SIZE, 4);

/* Thread stacks */
static K_THREAD_STACK_DEFINE(tcp_accept_rx_stack, TCP_THREAD_STACK_SIZE);
static K_THREAD_STACK_DEFINE(tcp_tx_stack, TCP_THREAD_STACK_SIZE);
static K_THREAD_STACK_DEFINE(can_tx_stack, CAN_THREAD_STACK_SIZE);

/* Flag to indicate shutdown requested */
static volatile sig_atomic_t running = 1;

/* Signal handler */
static void signal_handler(int sig)
{
    LOG_INF("Signal %d received, shutting down...", sig);
    running = 0;
    if (telematics_data.tcp_connected && telematics_data.tcp_socket >= 0) {
        telematics_data.tcp_connected = false;
        shutdown(telematics_data.tcp_socket, SHUT_RDWR);
        close(telematics_data.tcp_socket);
        telematics_data.tcp_socket = -1;
    }
    if (telematics_data.server_socket >= 0) {
        shutdown(telematics_data.server_socket, SHUT_RD);
        close(telematics_data.server_socket);
        telematics_data.server_socket = -1;
    }
}

/* Validate CAN IDs against allowed lists */
bool is_can_id_allowed(uint32_t can_id, bool is_can_to_internet)
{
    static const uint32_t internet_to_can_ids[] = ALLOWED_INTERNET_TO_CAN_IDS;
    static const uint32_t can_to_internet_ids[] = ALLOWED_CAN_TO_INTERNET_IDS;
    
    const uint32_t *allowed_ids;
    size_t num_ids;
    
    if (is_can_to_internet) {
        allowed_ids = can_to_internet_ids;
        num_ids = sizeof(can_to_internet_ids) / sizeof(can_to_internet_ids[0]);
    } else {
        allowed_ids = internet_to_can_ids;
        num_ids = sizeof(internet_to_can_ids) / sizeof(internet_to_can_ids[0]);
    }
    
    for (size_t i = 0; i < num_ids; i++) {
        if (can_id == allowed_ids[i]) {
            return true;
        }
    }
    
    return false;
}

/* === TCP TX Thread === */
static void tcp_tx_thread_func(void *arg1, void *arg2, void *arg3)
{
    ARG_UNUSED(arg1);
    ARG_UNUSED(arg2);
    ARG_UNUSED(arg3);

    struct telematics_msg outgoing_msg;
    LOG_INF("TCP TX thread started for client socket %d", telematics_data.tcp_socket);

    while (telematics_data.tcp_connected) {
        if (k_msgq_get(telematics_data.tcp_tx_queue, &outgoing_msg, K_FOREVER) == 0) {
            if (!telematics_data.tcp_connected || telematics_data.tcp_socket < 0) {
                 LOG_WRN("TCP TX: Woke up but client disconnected. Discarding ID 0x%x", outgoing_msg.can_id);
                 continue;
            }

            uint8_t tx_buffer[5 + 8];
            tx_buffer[0] = (outgoing_msg.can_id >> 24) & 0xFF;
            tx_buffer[1] = (outgoing_msg.can_id >> 16) & 0xFF;
            tx_buffer[2] = (outgoing_msg.can_id >> 8) & 0xFF;
            tx_buffer[3] = outgoing_msg.can_id & 0xFF;
            tx_buffer[4] = outgoing_msg.dlc;
            
            if (outgoing_msg.dlc > 0 && outgoing_msg.dlc <= 8) {
                memcpy(&tx_buffer[5], outgoing_msg.data, outgoing_msg.dlc);
            }
            
            int bytes_to_send = 5 + outgoing_msg.dlc;
            int total_sent = 0;

            while (total_sent < bytes_to_send) {
                if (telematics_data.tcp_socket < 0) {
                     LOG_WRN("TCP TX: Socket closed before send could complete. Exiting TX thread.");
                     goto tx_thread_exit;
                }

                 int bytes_sent = send(telematics_data.tcp_socket, 
                                       tx_buffer + total_sent, 
                                       bytes_to_send - total_sent, 
                                       0);
                
                if (bytes_sent <= 0) {
                    if (bytes_sent == 0) {
                         LOG_WRN("TCP TX: send() returned 0 (connection closed by peer?). Exiting TX thread.");
                    } else {
                        LOG_ERR("TCP TX: send() failed with error %d. Exiting TX thread.", errno);
                    }
                    goto tx_thread_exit;
                }
                total_sent += bytes_sent;
            }
            LOG_DBG("Forwarded CAN ID 0x%x (DLC: %d) to TCP client (socket %d)", 
                    outgoing_msg.can_id, outgoing_msg.dlc, telematics_data.tcp_socket);
        } else {
             LOG_WRN("TCP TX: k_msgq_get failed unexpectedly. Exiting.");
             goto tx_thread_exit;
        }
    }

tx_thread_exit:
    if (!telematics_data.tcp_connected) {
        LOG_INF("TCP TX thread exiting because client disconnected (socket %d).", telematics_data.tcp_socket);
    } else {
        LOG_INF("TCP TX thread exiting for other reason (socket %d).", telematics_data.tcp_socket);
    }
    telematics_data.tcp_tx_thread_id = NULL;
}

/* === TCP Accept & RX Thread === */
static void tcp_accept_rx_thread(void *arg1, void *arg2, void *arg3)
{
    ARG_UNUSED(arg1);
    ARG_UNUSED(arg2);
    ARG_UNUSED(arg3);
    
    struct sockaddr_in server_addr;
    int server_socket = -1; 
    int ret;
    
    telematics_data.server_socket = -1; 

    /* Create TCP server socket */
    server_socket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (server_socket < 0) {
        LOG_ERR("Failed to create TCP server socket: %d", errno);
        return;
    }
    telematics_data.server_socket = server_socket; 
    LOG_INF("TCP server socket created (fd=%d)", server_socket);

    int optval = 1;
    setsockopt(server_socket, SOL_SOCKET, SO_REUSEADDR, &optval, sizeof(optval));
    
    /* Configure server address */
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(TCP_SERVER_PORT);
    
    /* Bind socket */
    ret = bind(server_socket, (struct sockaddr *)&server_addr, sizeof(server_addr));
    if (ret < 0) {
        LOG_ERR("Failed to bind TCP server socket %d: %d", server_socket, errno);
        goto cleanup_server;
    }
    
    /* Listen for connections */
    ret = listen(server_socket, TCP_MAX_CONNECTIONS);
    if (ret < 0) {
        LOG_ERR("Failed to listen on TCP server socket %d: %d", server_socket, errno);
        goto cleanup_server;
    }
    
    LOG_INF("TCP server listening on port %d (socket %d)", TCP_SERVER_PORT, server_socket);
    
    while (running) {
        struct sockaddr_in client_addr;
        socklen_t client_addr_len = sizeof(client_addr);
        int client_socket = -1;
        
        telematics_data.tcp_socket = -1;
        telematics_data.tcp_connected = false;
        telematics_data.tcp_tx_thread_id = NULL;

        LOG_INF("Waiting to accept TCP connection on socket %d...", server_socket);
        client_socket = accept(server_socket, 
                                   (struct sockaddr *)&client_addr,
                                   &client_addr_len);
                                  
        if (!running) {
             LOG_INF("Shutdown requested while accepting. Exiting Accept/RX thread.");
             if (client_socket >= 0) close(client_socket);
             break; 
        }

        if (client_socket < 0) {
            LOG_ERR("Failed to accept TCP connection: %d", errno);
            k_sleep(K_SECONDS(1)); 
            continue;
        }
        
        telematics_data.tcp_socket = client_socket;
        telematics_data.tcp_connected = true; 
        LOG_INF("TCP client connected (socket %d)", telematics_data.tcp_socket);

        LOG_DBG("Purging tcp_tx_queue before starting TX thread...");
        struct telematics_msg old_msg;
        int purge_count = 0;
        while (k_msgq_get(telematics_data.tcp_tx_queue, &old_msg, K_NO_WAIT) == 0) {
             purge_count++;
        }
        LOG_DBG("Purged %d stale messages.", purge_count);

        telematics_data.tcp_tx_thread_id = k_thread_create(&telematics_data.tcp_tx_thread,
                                                      tcp_tx_stack,
                                                      K_THREAD_STACK_SIZEOF(tcp_tx_stack),
                                                      tcp_tx_thread_func,
                                                      NULL, NULL, NULL,
                                                      TCP_THREAD_PRIORITY, 
                                                      0, K_NO_WAIT);
                                                      
        if (telematics_data.tcp_tx_thread_id == NULL) {
             LOG_ERR("Failed to create TCP TX thread!");
             close(telematics_data.tcp_socket); 
             telematics_data.tcp_socket = -1;
             telematics_data.tcp_connected = false;
             continue;
        }
        k_thread_name_set(telematics_data.tcp_tx_thread_id, "tcp_tx");
        LOG_INF("TCP TX thread created (TID: %p)", telematics_data.tcp_tx_thread_id);

        while (running && telematics_data.tcp_connected) {
            struct telematics_msg msg;
            uint8_t rx_buffer[TCP_RX_BUFFER_SIZE];
            int bytes_received;
            
            bytes_received = recv(telematics_data.tcp_socket, rx_buffer, 
                                sizeof(rx_buffer), 0);
            
            if (!running && bytes_received <= 0) {
                 LOG_INF("Shutdown occurred during recv.");
                 break;
            }

            if (bytes_received <= 0) {
                if (bytes_received == 0) {
                    LOG_INF("TCP client (socket %d) disconnected gracefully.", telematics_data.tcp_socket);
                } else { 
                    LOG_ERR("TCP recv error on socket %d: %d. Assuming disconnect.", telematics_data.tcp_socket, errno);
                }
                break;
            }
            
            int processed_len = 0;
            while (processed_len < bytes_received) {
                 int remaining_len = bytes_received - processed_len;
                 if (remaining_len < 5) {
                      LOG_WRN("Partial TCP header received (%d bytes), waiting for more.", remaining_len);
                      break;
                 }

                 msg.can_id = (rx_buffer[processed_len + 0] << 24) | (rx_buffer[processed_len + 1] << 16) |
                              (rx_buffer[processed_len + 2] << 8)  | rx_buffer[processed_len + 3];
                 msg.dlc = rx_buffer[processed_len + 4];

                 if (msg.dlc > 8) {
                     LOG_ERR("Invalid CAN DLC %d received from TCP on socket %d. Skipping frame.", 
                             msg.dlc, telematics_data.tcp_socket);
                     processed_len = bytes_received;
                     break; 
                 }

                 int expected_frame_len = 5 + msg.dlc;
                 if (remaining_len < expected_frame_len) {
                      LOG_WRN("Partial TCP frame payload received for ID 0x%x. Expected %d bytes, got %d remaining. Waiting for more.", 
                              msg.can_id, expected_frame_len, remaining_len);
                      processed_len = bytes_received;
                      break;
                 }

                 memcpy(msg.data, &rx_buffer[processed_len + 5], msg.dlc);
                 processed_len += expected_frame_len;

                 LOG_DBG("TCP RX: ID=0x%x, DLC=%d (from socket %d)", msg.can_id, msg.dlc, telematics_data.tcp_socket);

                 if (is_can_id_allowed(msg.can_id, false)) { 
                     if (k_msgq_put(telematics_data.can_tx_queue, &msg, K_MSEC(10)) != 0) {
                         LOG_ERR("CAN TX queue full for message ID 0x%x from TCP. Discarding.", msg.can_id);
                     } else {
                         LOG_DBG("Msg ID 0x%x queued for CAN TX.", msg.can_id);
                     }
                 } else {
                     LOG_WRN("Received unauthorized CAN ID 0x%x from TCP for CAN tx", msg.can_id);
                 }
            }

        }
        
        LOG_INF("TCP client (socket %d) RX loop exited.", client_socket);
        bool was_connected = telematics_data.tcp_connected;
        telematics_data.tcp_connected = false;
        
        if (telematics_data.tcp_socket >= 0) {
             LOG_INF("Closing client socket %d.", telematics_data.tcp_socket);
             close(telematics_data.tcp_socket);
             telematics_data.tcp_socket = -1;
        }
        
        if (telematics_data.tcp_tx_thread_id != NULL) {
             LOG_DBG("Waiting briefly for TCP TX thread %p to exit...", telematics_data.tcp_tx_thread_id);
             k_sleep(K_MSEC(50)); 
             telematics_data.tcp_tx_thread_id = NULL; 
        } else if (was_connected) {
             LOG_WRN("Client disconnected, but TX thread ID was already NULL.");
        }
        LOG_INF("Finished cleanup for client socket %d.", client_socket);

    }
    
cleanup_server:
    LOG_INF("TCP Accept/RX thread cleaning up server socket %d.", server_socket);
    if (server_socket >= 0) {
        close(server_socket);
    }
    telematics_data.server_socket = -1;
    LOG_INF("TCP Accept/RX thread exiting.");
}

/* === CAN Receiver Callback === */
static void can_receiver_thread(const struct device *dev, struct can_frame *frame, void *user_data)
{
    ARG_UNUSED(dev);
    ARG_UNUSED(user_data);
    
    struct telematics_msg msg;
    
    if (!telematics_data.tcp_connected || telematics_data.tcp_tx_thread_id == NULL) {
        return;
    }

    if (is_can_id_allowed(frame->id, true)) {
        msg.can_id = frame->id;
        msg.dlc = frame->dlc;
        memcpy(msg.data, frame->data, frame->dlc);
        msg.is_can_to_internet = true;
        
        if (k_msgq_put(telematics_data.tcp_tx_queue, &msg, K_NO_WAIT) != 0) {
            LOG_ERR("TCP TX queue full (client connected - slow client/network?)"); 
        } else {
            LOG_DBG("CAN ID 0x%x (DLC %d) queued for TCP TX.", msg.can_id, msg.dlc);
        }
    }
}

/* CAN standard ID mask definition (already present) */
#ifndef CAN_STD_ID_MASK
#define CAN_STD_ID_MASK     0x7FF
#endif

/* === CAN TX Thread === */
static void can_tx_thread_func(void *arg1, void *arg2, void *arg3)
{
    ARG_UNUSED(arg1);
    ARG_UNUSED(arg2);
    ARG_UNUSED(arg3);
    
    struct telematics_msg msg;
    struct can_frame frame;
    int ret;
    
    LOG_INF("CAN TX thread started");

    while (1) { 
        if (k_msgq_get(telematics_data.can_tx_queue, &msg, K_FOREVER) == 0) {
            if (!running) break;

            LOG_DBG("Dequeued for CAN TX: ID=0x%x, DLC=%d", msg.can_id, msg.dlc);
            
            memset(&frame, 0, sizeof(frame));
            frame.dlc = msg.dlc > 8 ? 8 : msg.dlc;
            memcpy(frame.data, msg.data, frame.dlc);

            if ((msg.can_id & ~0x7FFU) != 0) {
                frame.id = msg.can_id; 
                frame.flags = CAN_FRAME_IDE; 
            } else {
                frame.id = msg.can_id;
                frame.flags = 0;
            }
            
            ret = can_send(telematics_data.can_dev, &frame, K_MSEC(100), NULL, NULL);
            if (ret != 0) {
                LOG_ERR("Failed to send CAN frame ID 0x%x (err %d)", frame.id, ret);
            } else {
                LOG_DBG("Successfully sent CAN frame ID 0x%x", frame.id);
            }
        } else {
            LOG_WRN("CAN TX thread: k_msgq_get failed. Exiting.");
            break;
        }
    }
    LOG_INF("CAN TX thread exiting");
    telematics_data.can_tx_thread_id = NULL;
}

/* === CAN Setup === */
static void setup_can(void)
{
    telematics_data.can_dev = device_get_binding("my_can");
    if (!telematics_data.can_dev) {
        LOG_ERR("Failed to get CAN device binding");
        return;
    }
    
    if (!device_is_ready(telematics_data.can_dev)) {
        LOG_ERR("CAN device is not ready");
        return;
    }
    
    int ret = can_start(telematics_data.can_dev);
    if (ret != 0) {
        LOG_ERR("Failed to start CAN device (err %d)", ret);
        return;
    }
    
    struct can_filter std_filter = {
        .id = 0,
        .mask = 0,
        .flags = 0
    };
    
    LOG_INF("Attaching CAN RX filter for all standard messages.");
    ret = can_add_rx_filter(telematics_data.can_dev, can_receiver_thread, NULL, &std_filter);
    if (ret < 0) {
        LOG_ERR("Failed to add standard CAN RX filter (err %d)", ret);
    }

    struct can_filter ext_filter = {
        .id = 0,
        .mask = 0,
        .flags = CAN_FILTER_IDE
    };

    LOG_INF("Attaching CAN RX filter for all extended messages.");
    ret = can_add_rx_filter(telematics_data.can_dev, can_receiver_thread, NULL, &ext_filter);
    if (ret < 0) {
        LOG_ERR("Failed to add extended CAN RX filter (err %d)", ret);
    }
    
    LOG_INF("CAN setup complete, listening for all messages via two filters.");
}

/* === Start / Stop === */
void start_telematics(void)
{
    memset(&telematics_data, 0, sizeof(telematics_data));
    telematics_data.initialized = true;
    telematics_data.tcp_socket = -1; 
    telematics_data.server_socket = -1;
    
    telematics_data.can_tx_queue = &can_tx_queue;
    telematics_data.tcp_tx_queue = &tcp_tx_queue;
    
    setup_can();
    
    telematics_data.tcp_accept_rx_thread_id = k_thread_create(
                                                  &telematics_data.tcp_accept_rx_thread,
                                                  tcp_accept_rx_stack,
                                                  K_THREAD_STACK_SIZEOF(tcp_accept_rx_stack),
                                                  tcp_accept_rx_thread, 
                                                  NULL, NULL, NULL,
                                                  TCP_THREAD_PRIORITY,
                                                  0, K_NO_WAIT);
     if (telematics_data.tcp_accept_rx_thread_id == NULL) {
         LOG_ERR("Failed to create TCP Accept/RX thread!");
         return;
     }
     k_thread_name_set(telematics_data.tcp_accept_rx_thread_id, "tcp_accept_rx");
     LOG_INF("TCP Accept/RX thread created (TID: %p)", telematics_data.tcp_accept_rx_thread_id);
     
    telematics_data.can_tx_thread_id = k_thread_create(
                                                &telematics_data.can_tx_thread,
                                                can_tx_stack,
                                                K_THREAD_STACK_SIZEOF(can_tx_stack),
                                                can_tx_thread_func,
                                                NULL, NULL, NULL,
                                                CAN_THREAD_PRIORITY,
                                                0, K_NO_WAIT);
    if (telematics_data.can_tx_thread_id == NULL) {
         LOG_ERR("Failed to create CAN TX thread!");
         if (telematics_data.tcp_accept_rx_thread_id) {
             k_thread_abort(telematics_data.tcp_accept_rx_thread_id);
         }
         return;
     }
     k_thread_name_set(telematics_data.can_tx_thread_id, "can_tx");
     LOG_INF("CAN TX thread created (TID: %p)", telematics_data.can_tx_thread_id);
    
    LOG_INF("Telematics gateway started with separate TCP RX/TX threads");
}

void stop_telematics(void)
{
    LOG_INF("Stopping telematics gateway (called from main)...");
    if (!telematics_data.initialized) return;

    running = 0;

    if (telematics_data.tcp_socket >= 0) {
         LOG_INF("stop_telematics: Closing active TCP client socket %d.", telematics_data.tcp_socket);
         shutdown(telematics_data.tcp_socket, SHUT_RDWR);
         close(telematics_data.tcp_socket);
         telematics_data.tcp_socket = -1;
    }
    telematics_data.tcp_connected = false; 

    if (telematics_data.server_socket >= 0) {
        LOG_INF("stop_telematics: Closing TCP server socket %d.", telematics_data.server_socket);
        shutdown(telematics_data.server_socket, SHUT_RD);
        close(telematics_data.server_socket);
        telematics_data.server_socket = -1;
    }

    LOG_DBG("Purging message queues...");
    if(telematics_data.tcp_tx_queue) k_msgq_purge(telematics_data.tcp_tx_queue);
    if(telematics_data.can_tx_queue) k_msgq_purge(telematics_data.can_tx_queue);

    k_sleep(K_MSEC(100)); 

    if (telematics_data.can_dev && device_is_ready(telematics_data.can_dev)) { 
        LOG_INF("stop_telematics: Stopping CAN device.");
        can_stop(telematics_data.can_dev);
    }
    
    telematics_data.initialized = false;
    LOG_INF("Telematics gateway stop sequence complete.");
}

/* === Main === */
int main(void)
{
    LOG_INF("Telematics Gateway Application - Separate TCP RX/TX Threads");
    
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    start_telematics();
    
    while (running) {
        k_sleep(K_SECONDS(1)); 
    }
    
    if (telematics_data.initialized) { 
       stop_telematics(); 
    }
    
    LOG_INF("Telematics main thread finished.");
    return 0;
}