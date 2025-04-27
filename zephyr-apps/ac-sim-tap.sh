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
# Define paths to individual conf files
CONF_FILE_ZETH0="$SCRIPT_DIR/ac_control/zeth0.conf"
CONF_FILE_ZETH1="$SCRIPT_DIR/hvac/zeth1.conf"

# Function to clean up interfaces on Ctrl+C
cleanup() {
    echo "Cleaning up interfaces..."
    # Stop interfaces individually
    # ip link set zeth0 down 2>/dev/null # Comment out zeth0 cleanup
    ip link set zeth1 down 2>/dev/null
    # ip tuntap del zeth0 mode tap 2>/dev/null # Comment out zeth0 cleanup
    ip tuntap del zeth1 mode tap 2>/dev/null
    # Optional: Call net-setup stop if needed, but direct commands are simpler here
    # $NET_TOOLS_DIR/net-setup.sh --config "$CONF_FILE_ZETH0" --iface zeth0 stop
    # $NET_TOOLS_DIR/net-setup.sh --config "$CONF_FILE_ZETH1" --iface zeth1 stop
    exit
}

# Set up cleanup on script exit
trap cleanup INT TERM

echo "Setting up AC simulator TAP interface (zeth1 only)..."

# Comment out first interface creation
# # Create first interface (zeth0)
# $NET_TOOLS_DIR/net-setup.sh --config "$CONF_FILE_ZETH0" --iface zeth0 start

# Create second interface (zeth1)
$NET_TOOLS_DIR/net-setup.sh --config "$CONF_FILE_ZETH1" --iface zeth1 start

echo "TAP interface zeth1 is ready:"
# ip addr show zeth0 # Comment out zeth0 display
# echo
ip addr show zeth1

echo
echo "Press Ctrl+C to cleanup and exit"

# Wait until Ctrl+C
while true; do
    sleep 1
done 