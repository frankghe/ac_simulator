#!/bin/bash

# Exit on error
set -e

source ~/venvs/vv/bin/activate

# Function to build a Zephyr application
build_app() {
    local app_name=$1
    local board=$2
    echo "Building $app_name for board $board..."
    
    cd zephyr-apps/$app_name
    
    # Initialize build directory if it doesn't exist
    if [ ! -d "build" ]; then
        mkdir build
    fi
    
    # Configure and build
    west build -p auto -b $board
        
    echo "$app_name build complete"
    cd ../..
}

# Check if board is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <board_name>"
    echo "Example: $0 native_sim"
    exit 1
fi

BOARD=$1

# Make sure we're in the Zephyr environment
if [ -z "$ZEPHYR_BASE" ]; then
    echo "Error: Zephyr environment not set. Please source zephyr-env.sh first."
    exit 1
fi

echo "Building all Zephyr applications for board: $BOARD"

# Find all directories in zephyr-apps that contain a CMakeLists.txt file
for app_dir in zephyr-apps/*/; do
    if [ -f "${app_dir}CMakeLists.txt" ]; then
        app_name=$(basename "$app_dir")
        echo "Found Zephyr application: $app_name"
        build_app "$app_name" "$BOARD"
    fi
done

echo "All applications built successfully!" 