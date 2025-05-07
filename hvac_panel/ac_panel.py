#!/usr/bin/env python3
import sys
import ctypes
from ctypes import (c_void_p, c_char_p, c_uint32, c_uint8, c_uint64, c_uint16,
                   POINTER, Structure, c_int, c_int8, byref, c_size_t, cast,
                   memset, sizeof)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QHBoxLayout, QPushButton, QLabel, QLCDNumber)
from PyQt6.QtCore import Qt, QTimer
import time

# Load SIL-Kit shared library
silkit = ctypes.CDLL('/home/frank/projects/sil-kit/build/Release/libSilKit.so')

# Keep a global reference to the callback pointer to prevent garbage collection
_global_frame_handler_ptr = None

# Define SIL-Kit constants
SILKIT_DIRECTION_RX = 2  # Receive direction (SilKit_Direction_Receive)
SILKIT_OPERATIONMODE_AUTONOMOUS = 20  # Autonomous mode
SILKIT_OPERATIONMODE_COORDINATED = 1  # Coordinated mode

# Define CAN frame flags
SILKIT_CANFRAMEFLAG_IDE = 1 << 9  # Identifier Extension
SILKIT_CANFRAMEFLAG_RTR = 1 << 4  # Remote Transmission Request

# Define SIL-Kit structs
class SilKit_StructHeader(Structure):
    _fields_ = [
        ("version", c_uint64),
        ("_reserved", c_uint64 * 3)
    ]

class SilKit_ByteVector(Structure):
    _fields_ = [
        ("data", POINTER(c_uint8)),
        ("size", c_size_t)
    ]

class CanFrame(Structure):
    _fields_ = [
        ("structHeader", SilKit_StructHeader),
        ("id", c_uint32),
        ("flags", c_uint32),
        ("dlc", c_uint16),
        ("sdt", c_uint8),
        ("vcid", c_uint8),
        ("af", c_uint32),
        ("data", SilKit_ByteVector)
    ]

# Add CanFrameEvent definition
class CanFrameEvent(Structure):
    _fields_ = [
        ("structHeader", SilKit_StructHeader),
        ("timestamp", c_uint64),
        ("frame", POINTER(CanFrame)),
        ("direction", c_uint32),
        ("userContext", c_void_p)
    ]

class SilKit_LifecycleConfiguration(Structure):
    _fields_ = [
        ("structHeader", SilKit_StructHeader),
        ("operationMode", c_uint32)
    ]

# Define CAN frame handler callback type
FrameHandlerType = ctypes.CFUNCTYPE(None, c_void_p, c_void_p, POINTER(CanFrameEvent))

# Define function signatures
silkit.SilKit_ParticipantConfiguration_FromString.argtypes = [POINTER(c_void_p), c_char_p]
silkit.SilKit_ParticipantConfiguration_FromString.restype = c_int

silkit.SilKit_Participant_Create.argtypes = [POINTER(c_void_p), c_void_p, c_char_p, c_char_p]
silkit.SilKit_Participant_Create.restype = c_int

silkit.SilKit_LifecycleService_Create.argtypes = [POINTER(c_void_p), c_void_p, POINTER(SilKit_LifecycleConfiguration)]
silkit.SilKit_LifecycleService_Create.restype = c_int

silkit.SilKit_LifecycleService_StartLifecycle.argtypes = [c_void_p]
silkit.SilKit_LifecycleService_StartLifecycle.restype = c_int

silkit.SilKit_CanController_Create.argtypes = [POINTER(c_void_p), c_void_p, c_char_p, c_char_p]
silkit.SilKit_CanController_Create.restype = c_int

silkit.SilKit_CanController_Start.argtypes = [c_void_p]
silkit.SilKit_CanController_Start.restype = c_int

silkit.SilKit_CanController_AddFrameHandler.argtypes = [c_void_p, c_void_p, FrameHandlerType, c_uint32, POINTER(c_uint32)]
silkit.SilKit_CanController_AddFrameHandler.restype = c_int

silkit.SilKit_CanController_SendFrame.argtypes = [c_void_p, POINTER(CanFrame), c_void_p]
silkit.SilKit_CanController_SendFrame.restype = c_int

silkit.SilKit_CanController_SetBaudRate.argtypes = [c_void_p, c_uint32, c_uint32, c_uint32]
silkit.SilKit_CanController_SetBaudRate.restype = c_int

silkit.SilKit_CanController_RemoveFrameHandler.argtypes = [c_void_p, c_uint32]
silkit.SilKit_CanController_RemoveFrameHandler.restype = c_int

silkit.SilKit_CanController_Stop.argtypes = [c_void_p]
silkit.SilKit_CanController_Stop.restype = c_int

silkit.SilKit_LifecycleService_Stop.argtypes = [c_void_p, c_char_p]
silkit.SilKit_LifecycleService_Stop.restype = c_int

# Define SIL-Kit struct initialization
def SilKit_Struct_Init(struct_type, struct_instance):
    memset(byref(struct_instance), 0, sizeof(struct_instance))
    if struct_type == CanFrame:
        struct_instance.structHeader.version = ((83 << 56) | (75 << 48) | (1 << 40) | (1 << 32) | (1 << 24))
    elif struct_type == SilKit_LifecycleConfiguration:
        struct_instance.structHeader.version = ((83 << 56) | (75 << 48) | (7 << 40) | (2 << 32) | (1 << 24))

# Utility function to print CAN frame details (similar to C version)
def print_can_frame(frame):
    if not frame:
        print("CAN Frame is NULL")
        return
    
    print("CAN Frame details:")
    print(f"  ID: 0x{frame.id:x}")
    print(f"  Flags: 0x{frame.flags:x}")
    print(f"  DLC: {frame.dlc}")
    
    if frame.data.data and frame.data.size > 0:
        data_array = [frame.data.data[i] for i in range(frame.data.size)]
        print(f"  Data size: {frame.data.size}")
        print(f"  Data: {data_array}")
    else:
        print("  Data: NULL")

class ACPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vehicle AC Control Panel")
        self.setFixedSize(400, 400) # Increased height for new label + external temp

        # SIL-Kit setup variables
        self.registry_uri = b"silkit://localhost:8500"
        self.participant_name = f"AC_Panel_{int(time.time())}".encode('utf-8')
        self.can_network_name = b"CAN1"
        
        # CAN IDs (should match can_ids.h and hvac app)
        self.HVAC_POWER_CMD_ID = 0xAC2  # ID to send AC ON/OFF command
        self.HVAC_STATUS_ID_FROM_ECU = 0x125 # ID from HVAC with actual status
        self.AC_STATE_BYTE_IDX_IN_STATUS = 2 # Index of AC state in 0x125

        print(f"AC Panel initializing with name {self.participant_name.decode()}")
        
        # Initialize state
        self.cabin_temp = 22.0
        self.requested_temp = 19.0
        self.external_temp = 27.0 # Ensure this is initialized
        self.fan_speed = 1
        # self.power = False # This will now be self.actual_ac_power_state
        self.actual_ac_power_state = False # Stores the true state from HVAC
        self.last_requested_power_state = False # To toggle ON/OFF requests
        self.mode = 'auto'
        
        # Initialize SIL-Kit
        self.initialize_silkit()
        
        # Initialize UI
        self.initialize_ui()
        
        print("AC Panel initialized successfully")

    def initialize_silkit(self):
        print("Creating participant configuration...")
        # Create participant configuration
        self.participant_config = c_void_p()
        result = silkit.SilKit_ParticipantConfiguration_FromString(byref(self.participant_config), b"{}")
        if result != 0:
            raise RuntimeError(f"Failed to create participant configuration: {result}")
        print("Participant configuration created.")

        # Create participant
        print("Creating participant...")
        self.participant = c_void_p()
        result = silkit.SilKit_Participant_Create(
            byref(self.participant),
            self.participant_config,
            self.participant_name,
            self.registry_uri
        )
        if result != 0:
            silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)
            raise RuntimeError(f"Failed to create participant: {result}")
        print("Participant created.")

        # Create lifecycle configuration
        print("Creating lifecycle configuration...")
        lifecycle_config = SilKit_LifecycleConfiguration()
        SilKit_Struct_Init(SilKit_LifecycleConfiguration, lifecycle_config)
        lifecycle_config.operationMode = SILKIT_OPERATIONMODE_AUTONOMOUS

        # Create lifecycle service
        print("Creating lifecycle service...")
        self.lifecycle_service = c_void_p()
        result = silkit.SilKit_LifecycleService_Create(
            byref(self.lifecycle_service),
            self.participant,
            byref(lifecycle_config)
        )
        if result != 0:
            silkit.SilKit_Participant_Destroy(self.participant)
            silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)
            raise RuntimeError(f"Failed to create lifecycle service: {result}")
        print("Lifecycle service created.")
        
        # Create CAN controller
        print(f"Creating CAN controller on network {self.can_network_name.decode()}...")
        self.can_controller = c_void_p()
        result = silkit.SilKit_CanController_Create(
            byref(self.can_controller),
            self.participant,
            b"CanController1",
            self.can_network_name
        )
        if result != 0:
            silkit.SilKit_Participant_Destroy(self.participant)
            silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)
            raise RuntimeError(f"Failed to create CAN controller: {result}")
        print("CAN controller created.")

        # Set CAN baud rate (500 kbps)
        print("Setting CAN baud rate...")
        result = silkit.SilKit_CanController_SetBaudRate(self.can_controller, 500000, 0, 0)
        if result != 0:
            silkit.SilKit_Participant_Destroy(self.participant)
            silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)
            raise RuntimeError(f"Failed to set CAN baud rate: {result}")
        print("CAN baud rate set.")

        # Add CAN frame handler
        print("Adding CAN frame handler...")
        self.handler_id = c_uint32()
        global _global_frame_handler_ptr
        self.frame_handler_callback = FrameHandlerType(self.handle_can_frame)
        _global_frame_handler_ptr = self.frame_handler_callback

        result = silkit.SilKit_CanController_AddFrameHandler(
            self.can_controller,
            None,  # context
            self.frame_handler_callback,
            SILKIT_DIRECTION_RX,
            byref(self.handler_id)
        )
        if result != 0:
            silkit.SilKit_Participant_Destroy(self.participant)
            silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)
            raise RuntimeError(f"Failed to add CAN handler: {result}")
        print(f"CAN frame handler added with ID: {self.handler_id.value}")

        # Start CAN controller
        print("Starting CAN controller...")
        result = silkit.SilKit_CanController_Start(self.can_controller)
        if result != 0:
            silkit.SilKit_Participant_Destroy(self.participant)
            silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)
            raise RuntimeError(f"Failed to start CAN controller: {result}")
        print("CAN controller started.")
        
        # Start lifecycle
        print("Starting lifecycle...")
        result = silkit.SilKit_LifecycleService_StartLifecycle(self.lifecycle_service)
        if result != 0:
            silkit.SilKit_Participant_Destroy(self.participant)
            silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)
            raise RuntimeError(f"Failed to start lifecycle: {result}")
        print("Lifecycle started.")

    def initialize_ui(self):
        # Create main widget and layout
        main_widget = QWidget(self)
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Power Button
        self.power_button = QPushButton("Toggle AC Power")
        # self.power_button.setCheckable(True) # No longer checkable
        # self.power_button.toggled.connect(self.toggle_power) # Connect to a new simplified method
        self.power_button.clicked.connect(self.request_ac_power_toggle) # New method
        layout.addWidget(self.power_button)

        # AC Status Label (New)
        self.ac_status_label = QLabel("AC Status: Unknown")
        self.ac_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.ac_status_label.font()
        font.setPointSize(14)
        self.ac_status_label.setFont(font)
        layout.addWidget(self.ac_status_label)
        self.update_ac_status_display() # Initialize display

        # Cabin Temperature Display
        self.cabin_temp_display = QLCDNumber(self)
        self.cabin_temp_display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        self.cabin_temp_display.setDigitCount(4)
        self.cabin_temp_display.display(f"{self.cabin_temp:.1f}")
        layout.addWidget(QLabel("Cabin Temperature (°C):"))
        layout.addWidget(self.cabin_temp_display)

        # External Temperature Display (New)
        self.external_temp_display = QLCDNumber(self)
        self.external_temp_display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        self.external_temp_display.setDigitCount(4)
        self.external_temp_display.display(f"{self.external_temp:.1f}") # Initialize with default
        layout.addWidget(QLabel("External Temperature (°C):"))
        layout.addWidget(self.external_temp_display)

        # Requested Temperature Controls
        temp_control_layout = QHBoxLayout()
        self.decrease_temp_button = QPushButton("-")
        self.decrease_temp_button.clicked.connect(self.decrease_temp)
        self.requested_temp_display = QLCDNumber(self)
        self.requested_temp_display.setSegmentStyle(QLCDNumber.SegmentStyle.Flat)
        self.requested_temp_display.setDigitCount(4)
        self.requested_temp_display.display(f"{self.requested_temp:.1f}")
        self.increase_temp_button = QPushButton("+")
        self.increase_temp_button.clicked.connect(self.increase_temp)
        temp_control_layout.addWidget(self.decrease_temp_button)
        temp_control_layout.addWidget(self.requested_temp_display)
        temp_control_layout.addWidget(self.increase_temp_button)
        layout.addWidget(QLabel("Requested Temperature (°C):"))
        layout.addLayout(temp_control_layout)

        # Fan Speed Controls
        fan_control_layout = QHBoxLayout()
        self.decrease_fan_button = QPushButton("-")
        self.decrease_fan_button.clicked.connect(self.decrease_fan)
        self.fan_speed_display = QLabel(f"Fan: {self.fan_speed}")
        self.fan_speed_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.increase_fan_button = QPushButton("+")
        self.increase_fan_button.clicked.connect(self.increase_fan)
        fan_control_layout.addWidget(self.decrease_fan_button)
        fan_control_layout.addWidget(self.fan_speed_display)
        fan_control_layout.addWidget(self.increase_fan_button)
        layout.addWidget(QLabel("Fan Speed:"))
        layout.addLayout(fan_control_layout)

        # Update display for fan speed
        self.update_fan_display()

    def update_ac_status_display(self):
        status_text = "AC Status: ON" if self.actual_ac_power_state else "AC Status: OFF"
        self.ac_status_label.setText(status_text)
        # Optionally change color too
        if self.actual_ac_power_state:
            self.ac_status_label.setStyleSheet("QLabel { color : green; }")
        else:
            self.ac_status_label.setStyleSheet("QLabel { color : red; }")

    def update_cabin_temp_display(self):
        self.cabin_temp_display.display(f"{self.cabin_temp:.1f}")

    def update_external_temp_display(self): # New method
        self.external_temp_display.display(f"{self.external_temp:.1f}")

    def update_requested_temp_display(self):
        self.requested_temp_display.display(f"{self.requested_temp:.1f}")

    def update_fan_display(self):
        self.fan_speed_display.setText(f"Fan: {self.fan_speed}")

    def request_ac_power_toggle(self):
        # Determine the new state to request (opposite of actual) and update last_requested_power_state.
        self.last_requested_power_state = not self.actual_ac_power_state
        requested_state_byte = int(self.last_requested_power_state) # True -> 1, False -> 0

        print(f"Power button clicked. Requesting AC to be {'ON' if self.last_requested_power_state else 'OFF'} (Actual was: {self.actual_ac_power_state})")
        
        # Prepare CAN frame data for HVAC_POWER_CMD_ID (0xAC2)
        # Assuming data format is [state_byte]
        can_data_payload = bytes([requested_state_byte])
        
        frame = CanFrame()
        SilKit_Struct_Init(CanFrame, frame)
        frame.id = self.HVAC_POWER_CMD_ID 
        frame.flags = 0 # Standard ID, Data frame
        frame.dlc = len(can_data_payload)
        
        # Create a temporary ctypes buffer for the data payload
        # and assign it to the SilKit_ByteVector
        temp_data_buffer = (c_uint8 * len(can_data_payload))(*can_data_payload)
        frame.data.data = cast(temp_data_buffer, POINTER(c_uint8))
        frame.data.size = len(can_data_payload)

        print(f"Sending CAN Command - ID: 0x{frame.id:X}, DLC: {frame.dlc}, Data: {list(can_data_payload)}")
        # print_can_frame(frame) # For more detailed debug if needed

        result = silkit.SilKit_CanController_SendFrame(self.can_controller, byref(frame), None)
        if result != 0:
            print(f"Error sending AC Power command: {result}")
        else:
            print("AC Power command sent successfully.")

    def handle_can_frame(self, context, controller, frame_event):
        # This function is called from a SIL-Kit internal thread.
        # Be careful with GUI updates from here; consider using Qt signals if issues arise.
        if not frame_event or not frame_event.contents.frame:
            print("Received NULL frame_event or frame in handle_can_frame")
            return

        received_frame = frame_event.contents.frame.contents
        can_id = received_frame.id
        dlc = received_frame.dlc
        
        # Ensure data is accessible
        if received_frame.data.data and dlc > 0 and dlc <= 8:
            data_bytes = bytes(received_frame.data.data[0:dlc])
        else:
            data_bytes = b''

        # print(f"Panel RX - ID: 0x{can_id:X}, DLC: {dlc}, Data: {list(data_bytes)}") # Debug all received frames

        if can_id == self.HVAC_STATUS_ID_FROM_ECU: # 0x125
            if dlc > self.AC_STATE_BYTE_IDX_IN_STATUS: # data[2] for 0x125 (and implies data[0], data[1] exist)
                new_ac_state_byte = data_bytes[self.AC_STATE_BYTE_IDX_IN_STATUS]
                self.actual_ac_power_state = (new_ac_state_byte == 1)
                
                # Update cabin temperature from data[0]
                if dlc > 0: # Should always be true if dlc > AC_STATE_BYTE_IDX_IN_STATUS (2)
                    self.cabin_temp = float(data_bytes[0]) / 2.0
                
                # Update external temperature from data[1]
                if dlc > 1: # Check if data[1] is available
                    self.external_temp = float(data_bytes[1]) / 2.0

                # Update fan speed from data[3]
                if dlc > 3:
                     self.fan_speed = data_bytes[3]

                print(f"Received HVAC Status (0x{can_id:X}): Actual AC Power={self.actual_ac_power_state}, CabinTemp={self.cabin_temp:.1f}, ExternalTemp={self.external_temp:.1f}, FanSpeed={self.fan_speed}")
                
                # IMPORTANT: GUI updates should be done safely, e.g., via signals or QTimer.singleShot
                # For simplicity here, direct update, but watch for threading issues.
                QTimer.singleShot(0, self.update_ac_status_display)
                QTimer.singleShot(0, self.update_cabin_temp_display)
                QTimer.singleShot(0, self.update_external_temp_display) # Add call to update external temp display
                QTimer.singleShot(0, self.update_fan_display)
            else:
                print(f"Received HVAC Status (0x{can_id:X}) but DLC {dlc} is too short for all expected data fields.")
        # Add handling for other CAN IDs if necessary

    def send_temperature_message(self):
        # This will send the self.requested_temp
        # This message ID and format need to be defined by the HVAC system.
        # For now, let's assume it sends HVAC_AC_STATUS_ID (0xAC1) with power, fan, temp_req.
        # This assumption might be wrong based on HVAC ECU's can_receiver_thread.
        # HVAC expects HVAC_AC_STATUS_ID to contain: data[0]=power, data[1]=fan, (data[2]=mode)
        # It seems HVAC_CONTROL_ID (0x123) is for: data[0]=power, data[1]=target_temp*2, data[2]=fan
        # Let's use HVAC_CONTROL_ID (0x123) to send requested temperature
        # This requires knowing the current power and fan state to send them too.

        # For this example, we'll re-purpose the old send_can_message structure
        # but this should ideally be a specific function like request_ac_power_toggle
        
        # To set temperature, we might need to send a different CAN ID or ensure
        # the HVAC app can parse it from a general control message.
        # The current HVAC app uses HVAC_CONTROL_ID (0x123) for this.
        # data: [ac_on, target_temp*2, fan_speed]
        
        # We will use self.actual_ac_power_state for the ac_on part
        # to reflect the true known state of the AC system.
        ac_on_byte = 1 if self.actual_ac_power_state else 0
        temp_byte = int(self.requested_temp * 2) # As per HVAC_CONTROL_ID format
        fan_byte = self.fan_speed

        can_data_payload = bytes([ac_on_byte, temp_byte, fan_byte])
        msg_id = 0x123 # HVAC_CONTROL_ID

        frame = CanFrame()
        SilKit_Struct_Init(CanFrame, frame)
        frame.id = msg_id
        frame.flags = 0 # Standard ID, Data frame
        frame.dlc = len(can_data_payload)
        
        temp_data_buffer = (c_uint8 * len(can_data_payload))(*can_data_payload)
        frame.data.data = cast(temp_data_buffer, POINTER(c_uint8))
        frame.data.size = len(can_data_payload)

        print(f"Sending Temp/Control Command - ID: 0x{frame.id:X}, DLC: {frame.dlc}, Data: {list(can_data_payload)}")
        result = silkit.SilKit_CanController_SendFrame(self.can_controller, byref(frame), None)
        if result != 0:
            print(f"Error sending Temp/Control command: {result}")
        else:
            print("Temp/Control command sent successfully.")

    def increase_temp(self):
        self.requested_temp = min(30.0, self.requested_temp + 0.5)
        self.update_requested_temp_display()
        self.send_temperature_message() # Send updated requested temp

    def decrease_temp(self):
        self.requested_temp = max(15.0, self.requested_temp - 0.5)
        self.update_requested_temp_display()
        self.send_temperature_message() # Send updated requested temp

    def increase_fan(self):
        self.fan_speed = min(5, self.fan_speed + 1)
        self.update_fan_display()
        self.send_temperature_message() # Fan speed is part of HVAC_CONTROL_ID

    def decrease_fan(self):
        self.fan_speed = max(1, self.fan_speed - 1)
        self.update_fan_display()
        self.send_temperature_message() # Fan speed is part of HVAC_CONTROL_ID

    def closeEvent(self, event):
        print("Closing AC Panel...")
        if hasattr(self, 'can_controller') and self.can_controller:
            print("Stopping CAN controller...")
            silkit.SilKit_CanController_Stop(self.can_controller)
        if hasattr(self, 'lifecycle_service') and self.lifecycle_service:
            print("Stopping lifecycle service...")
            silkit.SilKit_LifecycleService_Stop(self.lifecycle_service, b"ACPanel_Shutdown")
        # No direct destroy for controller, participant manages it.
        if hasattr(self, 'participant') and self.participant:
            print("Destroying participant...")
            # SilKit_Participant_Destroy(self.participant) # This can cause issues if lifecycle not fully stopped
        if hasattr(self, 'participant_config') and self.participant_config:
            # SilKit_ParticipantConfiguration_Destroy(self.participant_config)
            pass # Usually configuration is destroyed when participant is.
        print("AC Panel cleanup finished.")
        super().closeEvent(event)

    # Dummy process_silkit_events, SIL Kit does its own event processing
    def process_silkit_events(self):
        pass

def main():
    app = QApplication(sys.argv)
    window = ACPanel()
    window.show()
    sys.exit(app.exec())
    
if __name__ == '__main__':
    main() 