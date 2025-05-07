#!/bin/bash

# Current script directory (so we can find files relative to this script)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
ZEPHYR_APPS_DIR="$SCRIPT_DIR/zephyr-apps"

# --- Configuration: Apps to Launch ---
# Add or remove application names from this list to control what gets launched
# SIL-Kit registry and adapter are always launched
APPS_TO_LAUNCH=(
    # "sil_kit_registry" # Always launched
    # "sil_kit_adapter" # Always launched
    "hvac"
    "telematics"
    "lighting"
    # "bridge" # Bridge is typically disabled if panels use SIL-Kit directly
    "ac_panel"
    "lighting_panel"
)

# --- Helper Function to Check if App Should Launch ---
should_launch() {
    local app_name="$1"
    local list="${APPS_TO_LAUNCH[@]}"
    if [[ " $list " =~ " $app_name " ]]; then
        return 0 # True, should launch
    else
        return 1 # False, should not launch
    fi
}

# Virtual environment path
VENV_HOME="/home/frank/venvs/vv" # Adjust if needed
ZEPHYR_HOME="/home/frank/projects/zephyr_project" # Adjust if needed

# --- Helper Function to Find Zeth Conf and Name ---
find_zeth_config() {
    local app_name=$1
    local app_config_dir="$ZEPHYR_APPS_DIR/$app_name"
    local conf_path=""
    local iface_name=""

    if [ -f "$app_config_dir/zeth.conf" ]; then
        conf_path="$app_config_dir/zeth.conf"
        iface_name="zeth"
    else
        for i in {0..9}; do
            if [ -f "$app_config_dir/zeth${i}.conf" ]; then
                conf_path="$app_config_dir/zeth${i}.conf"
                iface_name="zeth${i}"
                break
            fi
        done
    fi
    # Return space-separated path and name
    echo "$conf_path $iface_name"
}


# Detect the terminal emulator to use (with proper flags for detached operation)
if command -v wt.exe &> /dev/null; then
    TERMINAL="wt.exe -w 0 new-tab --disable-application-title --"
elif command -v gnome-terminal &> /dev/null; then
    TERMINAL="gnome-terminal --"
elif command -v xterm &> /dev/null; then
    TERMINAL="xterm -hold -e"
elif command -v konsole &> /dev/null; then
    TERMINAL="konsole --separate --noclose -e"
else
    echo "No supported terminal emulator found. Please install Windows Terminal, gnome-terminal, xterm, or konsole."
    exit 1
fi

# Kill any existing processes
echo "Cleaning up existing processes..."
pkill -f "sil-kit-registry"
pkill -f "sil-kit-adapter-vcan"
pkill -f "ac_panel.py"
pkill -f "lighting_panel.py"
pkill -f "zephyr-apps/.*/build/zephyr/zephyr.exe" # More specific pkill for zephyr apps
pkill -f "bridge.py" # Assuming bridge.py is the bridge process
pkill -f "ac-sim-tap.sh"
sleep 2

# Setup vcan0 interface if it doesn't exist
echo "Checking vcan0 interface..."
if ! ip link show vcan0 &> /dev/null; then
    echo "Setting up vcan0 interface..."
    sudo modprobe vcan
    sudo ip link add dev vcan0 type vcan
    sudo ip link set up vcan0
    echo "vcan0 interface created and enabled"
else
    echo "vcan0 interface already exists"
fi

# --- Optional: Add Build Step Here ---
# echo "Building applications..."
# west build -b native_sim $ZEPHYR_APPS_DIR/hvac -d $SCRIPT_DIR/build/hvac
# west build -b native_sim $ZEPHYR_APPS_DIR/telematics -d $SCRIPT_DIR/build/telematics
# west build -b native_sim $ZEPHYR_APPS_DIR/lighting -d $SCRIPT_DIR/build/lighting -- -DDTC_OVERLAY_FILE=boards/native_sim.overlay
# --- End Optional Build Step ---


# --- Launch Components ---

# Start SIL-Kit registry (Always launched)
echo "Opening terminal for SIL-Kit registry..."
$TERMINAL wsl bash -c " \
    echo 'Starting SIL-Kit registry...' && \
    sil-kit-registry --registry-configuration $SCRIPT_DIR/silkit_config.yaml && \
    echo 'SIL-Kit registry stopped. Press Enter to close' && \
    read" &
sleep 2 # Wait for registry

# Start SIL-Kit CAN adapter (Always launched)
echo "Opening terminal for SIL-Kit CAN adapter... (Connects to vcan0)"
$TERMINAL wsl bash -c " \
    echo 'Starting SIL-Kit CAN adapter...' && \
    sil-kit-adapter-vcan --configuration $SCRIPT_DIR/silkit_config.yaml \
        --registry-uri silkit://localhost:8500 --can-name vcan0 && \
    echo 'SIL-Kit CAN adapter stopped. Press Enter to close' && \
    read" &
sleep 2 # Wait for adapter


# --- HVAC Setup and Launch if needed ---
if should_launch "hvac"; then
    echo "Processing HVAC application..."
    read hvac_zeth_conf hvac_zeth_iface <<< $(find_zeth_config "hvac")
    hvac_launch_cmd="cd $ZEPHYR_APPS_DIR/hvac && sudo ./build/zephyr/zephyr.exe"
    hvac_eth_arg=""

    if [ ! -z "$hvac_zeth_conf" ]; then
        echo "Found HVAC network config: $hvac_zeth_conf, interface: $hvac_zeth_iface"
        echo "Setting up TAP interface for HVAC..."
        # Run synchronously to ensure setup before launch
        if sudo $ZEPHYR_APPS_DIR/ac-sim-tap.sh hvac; then
            echo "HVAC TAP setup successful."
            hvac_eth_arg="--eth-if=$hvac_zeth_iface"
            hvac_launch_cmd="$hvac_launch_cmd $hvac_eth_arg"
        else
            echo "Error: Failed to set up TAP interface for HVAC. Continuing without network."
        fi
        sleep 1 # Give time for interface to settle
    else
        echo "No zeth*.conf found for HVAC. Skipping TAP setup."
    fi

    echo "Opening terminal for HVAC application..."
    $TERMINAL wsl bash -c " \
        echo 'Starting HVAC application...' && \
        $hvac_launch_cmd && \
        echo 'HVAC application stopped. Press Enter to close' && \
        read" &

    sleep 2 # Give time for HVAC app to start
else
    echo "Skipping HVAC launch."
fi

# --- Telematics Setup and Launch if needed ---
if should_launch "telematics"; then
    echo "Processing Telematics application..."
    read telematics_zeth_conf telematics_zeth_iface <<< $(find_zeth_config "telematics")
    telematics_launch_cmd="cd $ZEPHYR_APPS_DIR/telematics && sudo ./build/zephyr/zephyr.exe"
    telematics_eth_arg=""

    if [ ! -z "$telematics_zeth_conf" ]; then
        echo "Found Telematics network config: $telematics_zeth_conf, interface: $telematics_zeth_iface"
        echo "Setting up TAP interface for Telematics..."
        if sudo $ZEPHYR_APPS_DIR/ac-sim-tap.sh telematics; then
             echo "Telematics TAP setup successful."
             telematics_eth_arg="--eth-if=$telematics_zeth_iface"
             telematics_launch_cmd="$telematics_launch_cmd $telematics_eth_arg"
        else
             echo "Error: Failed to set up TAP interface for Telematics. Continuing without network."
        fi
        sleep 1 # Give time for interface to settle
    else
        echo "No zeth*.conf found for Telematics. Skipping TAP setup."
    fi

    echo "Opening terminal for Telematics application..."
    $TERMINAL wsl bash -c " \
        echo 'Starting Telematics application...' && \
        $telematics_launch_cmd && \
        echo 'Telematics application stopped. Press Enter to close' && \
        read" &

    sleep 2 # Give time for Telematics app to start
else
    echo "Skipping Telematics launch."
fi


# --- Lighting Launch if needed ---
if should_launch "lighting"; then
    echo "Opening terminal for LIGHTING application..."
    $TERMINAL wsl bash -c " \
        cd $ZEPHYR_APPS_DIR/lighting && \
        echo 'Starting LIGHTING application...' && \
        ./build/zephyr/zephyr.exe && \
        echo 'LIGHTING application stopped. Press Enter to close' && \
        read" &

    sleep 2 # Give time for Lighting to start
else
    echo "Skipping Lighting launch."
fi


# --- Bridge Launch (already disabled, but now conditional too) ---
if should_launch "bridge"; then
    if false; then # Original disabling block
        echo "Opening terminal for Bridge..."
        $TERMINAL wsl bash -c " \
            cd $SCRIPT_DIR/bridge && \
            echo 'Starting Bridge...' && \
            source $VENV_HOME/bin/activate && \
            python3 bridge.py && \
            echo 'Bridge stopped. Press Enter to close' && \
            read" &

        sleep 2 # Give time for Bridge to start
    fi
else
    if [ -f "$SCRIPT_DIR/bridge/bridge.py" ]; then # Only print skip if bridge code exists
      echo "Skipping Bridge launch."
    fi
fi

# --- GUI Panels Launch if needed ---
if should_launch "ac_panel"; then
    echo "Opening terminal for AC Panel GUI..."
    $TERMINAL wsl bash -c " \
        cd $SCRIPT_DIR/hvac_panel && \
        echo 'Starting AC Panel GUI...' && \
        source $VENV_HOME/bin/activate && \
        python3 ac_panel.py && \
        echo 'AC Panel GUI stopped. Press Enter to close' && \
        read" &
else
    echo "Skipping AC Panel launch."
fi

if should_launch "lighting_panel"; then
    echo "Opening terminal for Lighting Panel GUI..."
    $TERMINAL wsl bash -c " \
        cd $SCRIPT_DIR/lighting_panel && \
        echo 'Starting Lighting Panel GUI...' && \
        source $VENV_HOME/bin/activate && \
        python3 lighting_panel.py && \
        echo 'Lighting Panel GUI stopped. Press Enter to close' && \
        read" &
else
    echo "Skipping Lighting Panel launch."
fi

echo ""
echo "----------------------------------------------"
echo "Configured components started."
echo "To stop the simulation, close all terminal windows manually, or press Enter here."
echo "----------------------------------------------"

# Wait for user input to stop
read -p "Press Enter to stop all processes..."

# Kill all processes
echo "Stopping all processes..."
pkill -f "sil-kit-registry"
pkill -f "sil-kit-adapter-vcan"
pkill -f "ac_panel.py"
pkill -f "lighting_panel.py"
# Use a more specific pattern if possible, but this should catch the zephyr apps
pkill -f "zephyr-apps/.*/build/zephyr/zephyr.exe"
pkill -f "bridge.py"
pkill -f "ac-sim-tap.sh" # Kill any lingering setup scripts if they somehow didn't exit
sleep 1 # Give processes time to exit before cleanup

# Cleanup TAP interfaces explicitly using ac-sim-tap.sh stop
echo "Cleaning up network interfaces..."
if should_launch "hvac"; then
    # Check if the interface was likely created before trying to stop
    if ip link show $(find_zeth_config "hvac" | cut -d' ' -f2) &> /dev/null; then
       sudo $ZEPHYR_APPS_DIR/ac-sim-tap.sh hvac stop
    fi
fi
if should_launch "telematics"; then
    # Check if the interface was likely created before trying to stop
    if ip link show $(find_zeth_config "telematics" | cut -d' ' -f2) &> /dev/null; then
       sudo $ZEPHYR_APPS_DIR/ac-sim-tap.sh telematics stop
    fi
fi
# Add similar blocks if other apps use ac-sim-tap.sh

echo "Cleanup complete." 