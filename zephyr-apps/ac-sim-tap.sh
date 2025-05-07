#!/bin/bash

# Script to set up or tear down TAP interface based on a specific Zephyr app's configuration

# Function to print usage
usage() {
    echo "Usage: $0 <app_name> [start|stop|--wait]"
    echo "  <app_name>: Name of the Zephyr application (e.g., telematics, hvac)"
    echo "  start     : (Default) Set up the interface and exit."
    echo "  stop      : Tear down the interface associated with the app."
    echo "  --wait    : Set up the interface and wait indefinitely (for standalone use)."
    exit 1
}

# --- Argument Parsing ---
APP_NAME=""
COMMAND="start" # Default command
WAIT_FLAG=false

while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        start)
        COMMAND="start"
        shift
        ;;
        stop)
        COMMAND="stop"
        shift
        ;;
        --wait)
        WAIT_FLAG=true
        COMMAND="start" # --wait implies start
        shift
        ;;
        -h|--help)
        usage
        ;;
        *)
        if [ -z "$APP_NAME" ]; then APP_NAME="$1"; else echo "Error: Unknown argument: $1"; usage; fi
        shift
        ;;
    esac
done

if [ -z "$APP_NAME" ]; then echo "Error: Application name not provided."; usage; fi
# --- End Argument Parsing ---

# Store original user's home directory before sudo
if [ -z "$SUDO_USER" ]; then USER_HOME=$HOME; else USER_HOME=$(getent passwd $SUDO_USER | cut -d: -f6); fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_CONFIG_DIR="$SCRIPT_DIR/$APP_NAME"
NET_TOOLS_DIR="$USER_HOME/projects/zephyr_project/tools/net-tools" # Adjust if your path differs

# --- Dynamically find zethX.conf and Interface Name ---
find_zeth_info() {
    local conf_path=""
    local iface_name=""
    # Prefer zeth.conf if it exists
    if [ -f "$APP_CONFIG_DIR/zeth.conf" ]; then
        conf_path="$APP_CONFIG_DIR/zeth.conf"
        iface_name="zeth"
    else
        # Check zeth0 through zeth9
        for i in {0..9}; do
            if [ -f "$APP_CONFIG_DIR/zeth${i}.conf" ]; then
                conf_path="$APP_CONFIG_DIR/zeth${i}.conf"
                iface_name="zeth${i}"
                break
            fi
        done
    fi
    # Try to infer name if conf not found (needed for stop command)
    if [ -z "$iface_name" ]; then
         if [[ "$APP_NAME" == "hvac" ]]; then iface_name="zeth0";
         elif [[ "$APP_NAME" == "telematics" ]]; then iface_name="zeth1"; # Example, adjust as needed
         fi
         # Add more inferences if needed
    fi
    echo "$conf_path $iface_name"
}

read ZETH_CONF_PATH ZETH_IFACE_NAME <<< $(find_zeth_info)

if [ -z "$ZETH_IFACE_NAME" ]; then
    echo "Error: Could not determine interface name for $APP_NAME."
    exit 1
fi
# Config path is only strictly required for the start command
if [ -z "$ZETH_CONF_PATH" ] && [ "$COMMAND" = "start" ]; then
     echo "Error: Could not find zeth config file for $APP_NAME in $APP_CONFIG_DIR."
     exit 1
fi
# --- End Find --- 

# Function to clean up interface
cleanup() {
    echo "Cleaning up interface $ZETH_IFACE_NAME for $APP_NAME..."
    if [ -f "$NET_TOOLS_DIR/net-setup.sh" ]; then
         # Use config path if available, otherwise net-setup might still work with just iface name
         # Redirect stderr to /dev/null to avoid error messages if interface doesn't exist
         $NET_TOOLS_DIR/net-setup.sh --config "$ZETH_CONF_PATH" --iface "$ZETH_IFACE_NAME" stop 2>/dev/null || \
         ( echo "net-setup stop failed/unavailable, attempting manual cleanup..."; \
           ip link set $ZETH_IFACE_NAME down 2>/dev/null; \
           ip tuntap del $ZETH_IFACE_NAME mode tap 2>/dev/null )
    else
        echo "net-setup.sh not found, attempting manual cleanup..."
        ip link set $ZETH_IFACE_NAME down 2>/dev/null
        ip tuntap del $ZETH_IFACE_NAME mode tap 2>/dev/null
    fi
    echo "Cleanup attempt finished for $ZETH_IFACE_NAME."
}

# --- Main Logic --- 
run_as_root() {
    # Setup trap only needed when starting and waiting for interruption
    if [ "$COMMAND" = "start" ] && [ "$WAIT_FLAG" = true ]; then
        trap cleanup INT TERM
        echo "Trap handler set for INT/TERM."
    fi

    # Execute command
    case $COMMAND in
        start)
            echo "Found Zephyr network config: $ZETH_CONF_PATH"
            echo "Setting up TAP interface $ZETH_IFACE_NAME for application $APP_NAME..."
            # Check if net-setup.sh exists before trying to use it
            if [ ! -f "$NET_TOOLS_DIR/net-setup.sh" ]; then
                echo "Error: net-setup.sh not found at $NET_TOOLS_DIR"
                exit 1
            fi
            if ! $NET_TOOLS_DIR/net-setup.sh --config "$ZETH_CONF_PATH" --iface "$ZETH_IFACE_NAME" start; then
                echo "Error: net-setup.sh failed to create TAP interface $ZETH_IFACE_NAME using $ZETH_CONF_PATH"
                exit 1 # Exit without cleanup, interface likely doesn't exist or failed setup
            fi
            echo "TAP interface $ZETH_IFACE_NAME should be ready:"
            ip -brief link show $ZETH_IFACE_NAME # More concise output
            ip -4 -brief addr show $ZETH_IFACE_NAME
            echo "Network setup complete for $APP_NAME."

            if [ "$WAIT_FLAG" = true ]; then
                echo "Run the Zephyr application separately."
                echo "Script is waiting. Press Ctrl+C to cleanup network interface and exit."
                # Infinite loop to wait for Ctrl+C, trap will handle cleanup
                while true; do sleep 86400; done # Sleep long duration to avoid busy-wait
            else
                echo "Exiting script (use --wait to keep interface up standalone)."
                # Normal exit. NO trap is set for EXIT, so cleanup doesn't run here.
            fi
            ;;
        stop)
            echo "Executing cleanup for $APP_NAME (interface $ZETH_IFACE_NAME)..."
            cleanup
            ;;
    esac
}

# Check if running as root and execute main logic
if [ `id -u` != 0 ]; then
    # Construct command with necessary flags preserved
    sudo_cmd="sudo -E $0 $APP_NAME $COMMAND"
    if [ "$WAIT_FLAG" = true ]; then sudo_cmd="$sudo_cmd --wait"; fi
    echo "This script must be run as root! Re-running with: $sudo_cmd"
    # Use eval carefully, ensure variables don't contain malicious content (seems safe here)
    eval $sudo_cmd
    exit $?
else
    # Already root, execute the main logic
    run_as_root
fi 