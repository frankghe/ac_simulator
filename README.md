# Vehicle AC Simulator

This project implements a virtual vehicle air conditioning system simulator with the following components:

1. GUI Panel (Python/PyQt6)
2. AC Control Unit (Zephyr)
3. Thermal Model (Zephyr)

All components communicate via SIL-Kit's virtual CAN network.

## Project Structure

```
ac-simulator/
├── gui/               # Python GUI application
├── zephyr-apps/      # Zephyr applications
│   ├── ac_control/   # AC Control Unit
│   └── thermal/      # Thermal Model
└── can_config/       # SIL Kit CAN configuration
```

## Requirements

- Python 3.8+ with venv
- PyQt6
- Vector SIL Kit Python bindings
- Zephyr RTOS with SIL Kit integration
- Vector SIL Kit

## CAN Message Protocol

### Messages

1. AC Control Message (0x123)
   - Byte 0: Power state (0/1)
   - Byte 1: Target temperature * 2 (for 0.5°C resolution)
   - Byte 2: Fan speed (1-5)
   - Bytes 3-7: Reserved

2. AC Status Message (0x124)
   - Byte 0: Current temperature * 2
   - Byte 1: Reserved

3. Thermal Model Status (0x125)
   - Byte 0: Cabin temperature * 2
   - Byte 1: External temperature * 2
   - Bytes 2-3: Reserved

## Setup Instructions

1. Start the SIL-Kit Registry:
   ```bash
   silkit-registry --uri silkit://localhost:8500
   ```

2. Build and run Zephyr applications:
   ```bash
   # Build AC Control Unit
   cd zephyr-apps/ac_control
   west build -b [your_board] -- -DCONFIG_SILKIT=y
   west flash

   # Build Thermal Model
   cd ../thermal
   west build -b [your_board] -- -DCONFIG_SILKIT=y
   west flash
   ```

3. Run the GUI:
   ```bash
   source ~/venvs/vv/bin/activate
   cd gui
   python ac_panel.py
   ```

## Temperature Model

The thermal model simulates the vehicle cabin temperature based on:
- AC power state
- Target temperature
- Fan speed
- External temperature
- Thermal mass of the cabin
- Heat transfer coefficient

The model updates every 100ms to provide realistic temperature changes.

## SIL-Kit Configuration

The simulation uses a virtual CAN network configured in `can_config/silkit_config.yaml`. The network setup includes:
- Three participants: AC_Panel, AC_Control, and Thermal_Model
- One CAN network (VehicleCAN) at 500 kbps
- All participants communicate through the SIL-Kit Registry

To run with a different configuration:
1. Modify the `silkit_config.yaml` file
2. Update the registry URI in the Python GUI and Zephyr applications if changed
3. Restart all components 