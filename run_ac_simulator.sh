#!/bin/bash

# Current script directory (so we can find files relative to this script)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Virtual environment path
VENV_HOME="/home/frank/venvs/vv"
ZEPHYR_HOME="/home/frank/projects/zephyr_project"

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
pkill -f "zephyr.exe"
pkill -f "gateway.py"
pkill -f "ac-sim-tap.sh"
sleep 2

# Start SIL-Kit registry in its own terminal
echo "Opening terminal for SIL-Kit registry..."
$TERMINAL wsl bash -c "\
    echo 'Starting SIL-Kit registry...' && \
    sil-kit-registry --registry-configuration $SCRIPT_DIR/silkit_config.yaml && \
    echo 'SIL-Kit registry stopped. Press Enter to close' && \
    read" &

# Wait for registry to start
sleep 2

# Start SIL-Kit CAN adapter in its own terminal
echo "Opening terminal for SIL-Kit CAN adapter..."
$TERMINAL wsl bash -c "\
    echo 'Starting SIL-Kit CAN adapter...' && \
    sil-kit-adapter-vcan --configuration $SCRIPT_DIR/silkit_config.yaml \
        --registry-uri silkit://localhost:8500 --can-name vcan0 && \
    echo 'SIL-Kit CAN adapter stopped. Press Enter to close' && \
    read" &

# Wait for adapter to start
sleep 2

# First terminal: Setup TAP interfaces (with sudo)
echo "Opening terminal for TAP interface setup..."
$TERMINAL wsl bash -c "\
    echo 'Setting up TAP interfaces...' && \
    sudo bash $SCRIPT_DIR/zephyr-apps/ac-sim-tap.sh && \
    echo 'TAP interfaces set up. Press Enter to close' && \
    read" &

# Wait for TAP setup to complete
sleep 3

# Second terminal: run HVAC
echo "Opening terminal for HVAC application..."
$TERMINAL wsl bash -c "\
    cd $SCRIPT_DIR/zephyr-apps/hvac && \
    echo 'Starting HVAC application...' && \
    sudo ./build/zephyr/zephyr.exe && \
    echo 'HVAC application stopped. Press Enter to close' && \
    read" &

# Terminal: run LIGTHING
# Build command:  west build -b native_sim --pristine -- -DDTC_OVERLAY_FILE=boards/native_sim.overlay
echo "Opening terminal for LIGHTING application..."
$TERMINAL wsl bash -c "\
    cd $SCRIPT_DIR/zephyr-apps/lighting && \
    echo 'Starting LIGHTING application...' && \
    ./build/zephyr/zephyr.exe && \
    echo 'LIGHTING application stopped. Press Enter to close' && \
    read" &

# Give time for the HVAC app to start
sleep 3

# Third terminal: Run bridge
echo "Opening terminal for bridge..."
$TERMINAL wsl bash -c "\
    cd $SCRIPT_DIR/bridge && \
    echo 'Starting Bridge...' && \
    source $VENV_HOME/bin/activate && \
    python3 bridge.py && \
    echo 'Bridge stopped. Press Enter to close' && \
    read" &

# Give time for the bridge to start
sleep 2

# Fourth terminal: Run AC panel GUI
echo "Opening terminal for AC Panel GUI..."
$TERMINAL wsl bash -c "\
    cd $SCRIPT_DIR/hvac_panel && \
    echo 'Starting AC Panel GUI...' && \
    source $VENV_HOME/bin/activate && \
    python3 ac_panel.py && \
    echo 'AC Panel GUI stopped. Press Enter to close' && \
    read" &

# Fifth terminal: Run Lighting panel GUI
echo "Opening terminal for Lighting Panel GUI..."
$TERMINAL wsl bash -c "\
    cd $SCRIPT_DIR/lighting_panel && \
    echo 'Starting Lighting Panel GUI...' && \
    source $VENV_HOME/bin/activate && \
    python3 lighting_panel.py && \
    echo 'Lighting Panel GUI stopped. Press Enter to close' && \
    read" &

echo "All components started in separate terminals."
echo "To stop the simulation, close all terminal windows."

# Wait for user input to stop
echo "Press Enter to stop all processes..."
read

# Kill all processes
echo "Stopping all processes..."
pkill -f "sil-kit-registry"
pkill -f "sil-kit-adapter-vcan"
pkill -f "ac_panel.py"
pkill -f "lighting_panel.py"
pkill -f "zephyr.exe"
pkill -f "gateway.py"
pkill -f "ac-sim-tap.sh" 