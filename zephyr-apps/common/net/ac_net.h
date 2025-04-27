#ifndef AC_NET_H
#define AC_NET_H

#include <zephyr/kernel.h>
#include <zephyr/net/socket.h>
#include <zephyr/net/net_ip.h>
#include <zephyr/net/net_mgmt.h>
#include <zephyr/net/net_event.h>
#include <zephyr/logging/log.h>

/* Network events we're interested in */
#define AC_NET_EVENT_MASK (NET_EVENT_L4_CONNECTED | NET_EVENT_L4_DISCONNECTED)

/* Common network data structure */
struct ac_net_data {
    int sock;                    /* Socket file descriptor */
    char recv_buffer[256];       /* Buffer for received data */
    atomic_t bytes_received;     /* Number of bytes received */
    uint32_t counter;           /* Message counter */
    bool connected;             /* Connection status */
    struct k_sem run_sem;       /* Semaphore for thread control */
    struct net_mgmt_event_callback mgmt_cb;  /* Network management callback */
    struct k_thread thread;     /* Network thread */
    k_thread_stack_t *stack;    /* Thread stack */
    size_t stack_size;          /* Stack size */
    void (*msg_handler)(const char *msg, size_t len);  /* Message handler callback */
    uint16_t port;             /* Port number for connection */
    char peer_addr[NET_IPV4_ADDR_LEN];  /* Peer address string */
};

/**
 * @brief Initialize network data structure
 *
 * @param data Pointer to ac_net_data structure
 * @param stack Pointer to thread stack
 * @param stack_size Size of thread stack
 * @param msg_handler Callback function for handling received messages
 * @return int 0 on success, negative error code on failure
 */
int ac_net_init(struct ac_net_data *data, k_thread_stack_t *stack, 
                size_t stack_size, void (*msg_handler)(const char*, size_t));

/**
 * @brief Start network operations
 *
 * @param data Pointer to ac_net_data structure
 * @param port Port number to connect to
 * @param peer_addr Peer IPv4 address to connect to
 * @return int 0 on success, negative error code on failure
 */
int ac_net_start(struct ac_net_data *data, uint16_t port, const char *peer_addr);

/**
 * @brief Stop network operations
 *
 * @param data Pointer to ac_net_data structure
 */
void ac_net_stop(struct ac_net_data *data);

/**
 * @brief Send data over the network
 *
 * @param data Pointer to ac_net_data structure
 * @param buffer Data to send
 * @param len Length of data
 * @return int Number of bytes sent on success, negative error code on failure
 */
int ac_net_send(struct ac_net_data *data, const void *buffer, size_t len);

#endif /* AC_NET_H */ 