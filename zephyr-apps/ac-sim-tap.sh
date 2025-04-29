#!/bin/bash

# Store original user's home directory before sudo
if [ -z "$SUDO_USER" ]; then
    USER_HOME=$HOME
else
    USER_HOME=$(getent passwd $SUDO_USER | cut -d: -f6)
fi

# Check if running as root
if [ `id -u` != 0 ]; then
    echo "This script must be run as root!"
    sudo -E $0 $@
    exit
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NET_TOOLS_DIR="$USER_HOME/projects/zephyr_project/tools/net-tools"

# Check if net-tools directory exists
if [ ! -d "$NET_TOOLS_DIR" ]; then
    echo "Error: net-tools directory not found at $NET_TOOLS_DIR"
    echo "Please make sure Zephyr project is installed and net-tools are available"
    exit 1
fi

# Check if net-setup.sh exists
if [ ! -f "$NET_TOOLS_DIR/net-setup.sh" ]; then
    echo "Error: net-setup.sh not found in $NET_TOOLS_DIR"
    echo "Please make sure Zephyr project is installed and net-tools are available"
    exit 1
fi

# Define paths to individual conf files
CONF_FILE_ZETH0="$SCRIPT_DIR/ac_control/zeth0.conf"
CONF_FILE_ZETH1="$SCRIPT_DIR/hvac/zeth1.conf"

# Function to clean up interfaces on Ctrl+C
cleanup() {
    echo "Cleaning up interfaces..."
    ip link set zeth1 down 2>/dev/null
    ip tuntap del zeth1 mode tap 2>/dev/null
    exit
}

# Set up cleanup on script exit
trap cleanup INT TERM

echo "Setting up AC simulator TAP interface (zeth1 only)..."

# Create second interface (zeth1)
if ! $NET_TOOLS_DIR/net-setup.sh --config "$CONF_FILE_ZETH1" --iface zeth1 start; then
    echo "Error: Failed to create TAP interface zeth1"
    exit 1
fi

echo "TAP interface zeth1 is ready:"
ip addr show zeth1

echo
echo "Press Ctrl+C to cleanup and exit"

# Wait until Ctrl+C
while true; do
    sleep 1
done 