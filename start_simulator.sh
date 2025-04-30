#!/bin/bash

# Set SIL Kit configuration
export SILKIT_CONFIGURATION="$(pwd)/silkit_config.yaml"

# Start SIL Kit registry
sil-kit-registry &
REGISTRY_PID=$!

# Wait for registry to start
sleep 2

# Start the lighting panel
python3 lighting_panel/lighting_panel.py &
PANEL_PID=$!

# Wait for user to press Ctrl+C
echo "Simulator started. Press Ctrl+C to stop."
trap "kill $REGISTRY_PID $PANEL_PID; exit" INT
wait 