# Vehicle AC Simulator

This project implements a virtual vehicle air conditioning system simulator with the following components:

1. AC Panel (Python/PyQt6) - Simulates the vehicle's AC control panel interface
2. HVAC (Zephyr) - Implements the ECU controlling the AC system
3. Lighting (Zephyr) - Implements the ECU controlling vehicle lighting systems
4. Bridge (Python) - Provides Ethernet-to-CAN gateway functionality

All components communicate via a virtual CAN network using SIL-Kit, with the Bridge providing connectivity between Ethernet and CAN networks.

## Project Structure

```ac-simulator/
├── gui/               # Python AC Panel application
│   └── ac_panel.py    # AC panel user interface
├── zephyr-apps/       # Zephyr applications
│   ├── hvac/          # HVAC ECU implementation 
│   └── common/        # Shared code for Zephyr apps
├── bridge/            # Ethernet-to-CAN gateway
│   └── bridge.py     # Bridge implementation
└── can_config/        # SIL Kit CAN configuration
```

## Requirements

- Python 3.8+ with venv
- PyQt6
- Vector SIL Kit Python bindings
- Zephyr RTOS with SIL Kit integration
- Vector SIL Kit

## CAN Message Protocol

The system uses the following CAN messages:

1. AC Control Message (0x123)
   - Byte 0: Power state (0/1)
   - Byte 1: Target temperature * 2 (for 0.5°C resolution)
   - Byte 2: Fan speed (1-5)
   - Bytes 3-7: Reserved

2. Thermal Model Status (0x125)
   - Byte 0: Cabin temperature * 2
   - Byte 1: External temperature * 2
   - Bytes 2-7: Reserved

3. AC Status Message (0xAC1)
   - Byte 0: Power state (0/1)
   - Byte 1: Fan speed (1-5)
   - Byte 2: Mode (0=auto, 1=cool, 2=heat)
   - Bytes 3-7: Reserved

4. AC Power Status (0xAC2)
   - Byte 0: Power state (0/1)
   - Bytes 1-7: Reserved

5. Lighting Control Message (0xB10)
   - Byte 0: Headlight state (0=off, 1=on)
   - Byte 1: Blinker state (0=off, 2=left, 3=right)
   - Byte 2: Hazard light state (0=off, 1=on)
   - Bytes 3-7: Reserved

6. Lighting Status Message (0xB11)
   - Byte 0: Headlight state
   - Byte 1: Blinker state
   - Byte 2: Hazard light state
   - Bytes 3-7: Reserved

Note: The original AC Status Message (0x124) from previous versions is no longer used in the current implementation.

## Setup Instructions

1. Set up TAP interfaces for Zephyr networking and virtual CAN:
   ```bash
   sudo ./zephyr-apps/ac-sim-tap.sh
   ```

2. Build and run the HVAC application:
   ```bash
   west build -p -b native_sim zephyr-apps/hvac -- -DCONF_FILE=prj.conf
   cd build/zephyr
   ./zephyr.exe
   ```

3. Build and run the Lighting ECU application:
   ```bash
   west build -p -b native_sim zephyr-apps/lighting -- -DCONF_FILE=prj.conf
   cd build/zephyr
   ./zephyr.exe
   ```

4. Run the Bridge/Gateway:
   ```bash
   cd bridge
   python gateway.py
   ```

5. Run the AC Panel:
   ```bash
   cd gui
   python ac_panel.py
   ```

Alternatively, you can use the run_ac_simulator.sh script to start all components at once:
```bash
./run_ac_simulator.sh
```

## Temperature Model

The HVAC model simulates the vehicle cabin temperature based on:
- AC power state
- Target temperature
- Fan speed
- External temperature
- Thermal mass of the cabin
- Heat transfer coefficient

The model updates every second to provide realistic temperature changes.

## Lighting Control Model

The Lighting ECU simulates vehicle lighting systems:
- Headlights (on/off)
- Turn signals/blinkers (left/right)
- Hazard lights

The blinkers and hazard lights automatically flash at 500ms intervals when activated.

## SIL-Kit Configuration

The simulation uses a virtual CAN network configured in `can_config/silkit_config.yaml`. The network setup includes:
- Three participants: AC_Panel, Lighting and HVAC
- One CAN network (VehicleCAN) at 500 kbps
- All participants communicate through the SIL-Kit Registry

## Network Architecture

The system uses a hybrid communication approach:
- AC Panel communicates with the HVAC ECU through the Bridge over SIL-Kit virtual CAN
- The Bridge component provides Ethernet-to-CAN conversion for TCP/IP based communication
- HVAC ECU communicates with the Bridge over TCP/IP (via simulated Ethernet)

This setup allows for realistic network simulation, including the use of different network types found in modern vehicles.