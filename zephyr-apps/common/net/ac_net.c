#include "ac_net.h"
#include <zephyr/net/socket.h>
#include <zephyr/net/net_ip.h>
#include <zephyr/net/net_mgmt.h>
#include <zephyr/net/conn_mgr_monitor.h>
#include <errno.h>
#include <string.h>

LOG_MODULE_REGISTER(ac_net, CONFIG_AC_NET_LOG_LEVEL);

/* Forward declarations */
static int setup_socket(struct ac_net_data *data, uint16_t port, const char *peer_addr);

/* Internal network thread function */
static void ac_net_thread(void *p1, void *p2, void *p3)
{
    struct ac_net_data *data = (struct ac_net_data *)p1;
    int ret;

    ARG_UNUSED(p2);
    ARG_UNUSED(p3);

    while (1) {
        if (!data->connected || data->sock < 0) {
            k_msleep(1000);
            continue;
        }
        ret = recv(data->sock, data->recv_buffer, sizeof(data->recv_buffer) - 1, 0);
        if (ret == 0) {
            LOG_WRN("Peer closed connection gracefully (recv=0)");
            // Option 1: Close and clean up (current behavior)
            // Option 2: Just mark disconnected, do not close
            // Option 3: Wait for reconnect logic

            close(data->sock);
            data->sock = -1;
            data->connected = false;
            continue;
        }

        if (ret < 0) {
            LOG_ERR("recv error: %d (%s)", errno, strerror(errno));

            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                // Non-blocking socket: no data available yet
                continue;
            }

            // Other errors = real disconnect
            close(data->sock);
            data->sock = -1;
            data->connected = false;
            continue;
        }
        data->recv_buffer[ret] = '\0';
        atomic_add(&data->bytes_received, ret);
        data->counter++;

        if (data->msg_handler) {
            data->msg_handler(data->recv_buffer, ret);
        }
    }
}

/* Network event handler */
static void ac_net_event_handler(struct net_mgmt_event_callback *cb,
                               uint32_t mgmt_event, struct net_if *iface)
{
    struct ac_net_data *data = CONTAINER_OF(cb, struct ac_net_data, mgmt_cb);

    ARG_UNUSED(iface);

    if ((mgmt_event & AC_NET_EVENT_MASK) != mgmt_event) {
        return;
    }

    if (mgmt_event == NET_EVENT_L4_CONNECTED) {
        LOG_INF("Network connected");
        
        // Wait a bit to ensure network stack is ready
        k_msleep(100);
        
        LOG_INF("Setting up socket...");
        int ret = setup_socket(data, data->port, data->peer_addr);
        if (ret < 0) {
            LOG_ERR("Failed to setup socket after network connection: %d (%s)", 
                   ret, strerror(-ret));
            return;
        }
        data->connected = true;
        k_sem_give(&data->run_sem);
        return;
    }

    if (mgmt_event == NET_EVENT_L4_DISCONNECTED) {
        if (data->connected == false) {
            LOG_INF("Waiting network to be connected");
        } else {
            LOG_INF("Network disconnected");
            if (data->sock >= 0) {
                close(data->sock);
                data->sock = -1;
            }
            data->connected = false;
        }
        k_sem_reset(&data->run_sem);
        return;
    }
}

int ac_net_init(struct ac_net_data *data, k_thread_stack_t *stack,
                size_t stack_size, void (*msg_handler)(const char*, size_t))
{
    if (!data || !stack) {
        return -EINVAL;
    }

    memset(data, 0, sizeof(*data));
    data->sock = -1;
    data->stack = stack;
    data->stack_size = stack_size;
    data->msg_handler = msg_handler;
    data->bytes_received = ATOMIC_INIT(0);
    k_sem_init(&data->run_sem, 0, 1);

    /* Initialize network management callback */
    net_mgmt_init_event_callback(&data->mgmt_cb, ac_net_event_handler,
                                AC_NET_EVENT_MASK);
    net_mgmt_add_event_callback(&data->mgmt_cb);

    return 0;
}

static int setup_socket(struct ac_net_data *data, uint16_t port, const char *peer_addr)
{
    struct sockaddr_in addr;
    int ret;

    LOG_INF("Creating socket...");
    data->sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (data->sock < 0) {
        LOG_ERR("Failed to create socket: %d (%s)", errno, strerror(errno));
        return -errno;
    }

    /* Set socket options */
    int optval = 1;
    ret = setsockopt(data->sock, SOL_SOCKET, SO_REUSEADDR, &optval, sizeof(optval));
    if (ret < 0) {
        LOG_ERR("Failed to set SO_REUSEADDR: %d (%s)", errno, strerror(errno));
        close(data->sock);
        data->sock = -1;
        return -errno;
    }

    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    
    LOG_INF("Connecting to %s:%d...", peer_addr, port);
    ret = inet_pton(AF_INET, peer_addr, &addr.sin_addr);
    if (ret <= 0) {
        LOG_ERR("Invalid address: %s", peer_addr);
        close(data->sock);
        data->sock = -1;
        return -EINVAL;
    }

    ret = connect(data->sock, (struct sockaddr *)&addr, sizeof(addr));
    if (ret < 0) {
        LOG_ERR("Failed to connect: %d (%s)", errno, strerror(errno));
        close(data->sock);
        data->sock = -1;
        return -errno;
    }

    LOG_INF("Connected to %s:%d", peer_addr, port);
    return 0;
}

int ac_net_start(struct ac_net_data *data, uint16_t port, const char *peer_addr)
{
    if (!data || !peer_addr) {
        return -EINVAL;
    }

    data->port = port;
    strncpy(data->peer_addr, peer_addr, sizeof(data->peer_addr) - 1);
    data->peer_addr[sizeof(data->peer_addr) - 1] = '\0';

    /* Start thread */
    k_thread_create(&data->thread, data->stack,
                   data->stack_size,
                   ac_net_thread, data, NULL, NULL,
                   5, 0, K_NO_WAIT);
    k_thread_name_set(&data->thread, "ac_net_thread");

    /* Wait for network interface to be up */
    struct net_if *iface = net_if_get_default();
    LOG_INF("Waiting for interface to be up...");
    while (!net_if_is_up(iface)) {
        k_sleep(K_MSEC(100));
    }

    LOG_INF("Interface is up, setting up socket...");
    int ret = setup_socket(data, port, peer_addr);
    if (ret < 0) {
        return ret;
    }

    data->connected = true;
    return 0;
}

void ac_net_stop(struct ac_net_data *data)
{
    if (!data) {
        return;
    }

    if (data->sock >= 0) {
        close(data->sock);
        data->sock = -1;
    }
    data->connected = false;
}

int ac_net_send(struct ac_net_data *data, const void *buffer, size_t len)
{
    if (!data || !buffer || data->sock < 0) {
        return -EINVAL;
    }

    return send(data->sock, buffer, len, 0);
} 