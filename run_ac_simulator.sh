#!/bin/bash

# Current script directory (so we can find files relative to this script)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Detect the terminal emulator to use (with proper flags for detached operation)
if command -v gnome-terminal &> /dev/null; then
    TERMINAL="gnome-terminal --"
elif command -v xterm &> /dev/null; then
    TERMINAL="xterm -hold -e"
elif command -v konsole &> /dev/null; then
    TERMINAL="konsole --separate --noclose -e"
elif command -v wsl.exe &> /dev/null; then
    # WSL detection
    TERMINAL="wsl.exe -e"
else
    echo "No supported terminal emulator found. Please install gnome-terminal, xterm, or konsole."
    exit 1
fi

# First terminal: Setup TAP interfaces (with sudo)
echo "Opening terminal for TAP interface setup..."
$TERMINAL bash -c "echo 'Setting up TAP interfaces...'; sudo bash $SCRIPT_DIR/zephyr-apps/ac-sim-tap.sh; echo 'TAP interfaces set up. Press Enter to close this window.'; read" &

# Wait for TAP setup to complete
sleep 3

# Second terminal: Build and run HVAC
echo "Opening terminal for HVAC application..."
$TERMINAL bash -c "cd $SCRIPT_DIR && \
    echo 'Building HVAC application...' && \
    west build -p -b native_sim zephyr-apps/hvac -- -DCONF_FILE=prj.conf && \
    echo 'Starting HVAC application...' && \
    cd $SCRIPT_DIR/build/zephyr && \
    ./zephyr.exe; echo 'HVAC application stopped. Press Enter to close this window.'; read" &

# Give time for the HVAC app to start
sleep 3

# Third terminal: Run bridge/gateway
echo "Opening terminal for Gateway..."
$TERMINAL bash -c "cd $SCRIPT_DIR/bridge && \
    echo 'Starting Gateway...' && \
    python3 gateway.py; echo 'Gateway stopped. Press Enter to close this window.'; read" &

# Give time for the bridge to start
sleep 2

# Fourth terminal: Run AC panel GUI
echo "Opening terminal for AC Panel GUI..."
$TERMINAL bash -c "cd $SCRIPT_DIR/hvac && \
    echo 'Starting AC Panel GUI...' && \
    python3 ac_panel.py; echo 'AC Panel GUI stopped. Press Enter to close this window.'; read" &

echo "All components started in separate terminals."
echo "To stop the simulation, close all terminal windows."

# Don't exit this script immediately
echo "Press Ctrl+C to exit this main script."
# Wait indefinitely
tail -f /dev/null 