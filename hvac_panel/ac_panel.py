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
        self.setFixedSize(400, 300)

        # SIL-Kit setup variables
        self.registry_uri = b"silkit://localhost:8500"
        self.participant_name = f"AC_Panel_{int(time.time())}".encode('utf-8')
        self.can_network_name = b"CAN1"
        
        print(f"AC Panel initializing with name {self.participant_name.decode()}")
        
        # Initialize state
        self.cabin_temp = 22.0  # Actual cabin temperature from HVAC model
        self.requested_temp = 19.0  # Cooler default requested temperature to ensure cooling when AC is on
        self.external_temp = 27.0
        self.fan_speed = 1
        self.power = False
        self.mode = 'auto'  # Default mode
        
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
        lifecycle_config.operationMode = SILKIT_OPERATIONMODE_AUTONOMOUS  # Using autonomous mode just like the C example

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

        # Add CAN frame handler - using the class method directly
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
        
        # Start the lifecycle - after starting the controller like in the C example
        print("Starting lifecycle...")
        result = silkit.SilKit_LifecycleService_StartLifecycle(self.lifecycle_service)
        if result != 0:
            print(f"Warning: Failed to start lifecycle service: {result}")
        else:
            print("Lifecycle started successfully.")
        
        print("SIL-Kit initialization complete.")

    def initialize_ui(self):
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Actual Cabin Temperature displays
        temp_layout = QHBoxLayout()
        temp_label = QLabel("Cabin Temperature:")
        self.temp_display = QLCDNumber()
        self.temp_display.setSegmentStyle(QLCDNumber.SegmentStyle.Filled)
        self.temp_display.display(22.0)  # Default temperature
        temp_layout.addWidget(temp_label)
        temp_layout.addWidget(self.temp_display)
        layout.addLayout(temp_layout)
        
        # Requested Temperature display
        req_temp_layout = QHBoxLayout()
        req_temp_label = QLabel("Requested Temperature:")
        self.req_temp_display = QLCDNumber()
        self.req_temp_display.setSegmentStyle(QLCDNumber.SegmentStyle.Filled)
        self.req_temp_display.display(self.requested_temp)  # Use the instance variable
        req_temp_layout.addWidget(req_temp_label)
        req_temp_layout.addWidget(self.req_temp_display)
        layout.addLayout(req_temp_layout)
        
        # External temperature display
        ext_temp_layout = QHBoxLayout()
        ext_temp_label = QLabel("External Temperature:")
        self.ext_temp_display = QLCDNumber()
        self.ext_temp_display.setSegmentStyle(QLCDNumber.SegmentStyle.Filled)
        self.ext_temp_display.display(27.0)  # Default external temperature
        ext_temp_layout.addWidget(ext_temp_label)
        ext_temp_layout.addWidget(self.ext_temp_display)
        layout.addLayout(ext_temp_layout)
        
        # Status indicator for temperature source
        self.temp_source_label = QLabel("Temperature: Manual Control")
        layout.addWidget(self.temp_source_label)
        
        # Temperature controls
        temp_control = QHBoxLayout()
        self.temp_up = QPushButton("▲")
        self.temp_down = QPushButton("▼")
        temp_control.addWidget(self.temp_down)
        temp_control.addWidget(self.temp_up)
        layout.addLayout(temp_control)
        
        # Fan speed control
        fan_layout = QHBoxLayout()
        fan_label = QLabel("Fan Speed:")
        self.fan_display = QLCDNumber()
        self.fan_display.setSegmentStyle(QLCDNumber.SegmentStyle.Filled)
        self.fan_display.display(1)
        fan_layout.addWidget(fan_label)
        fan_layout.addWidget(self.fan_display)
        layout.addLayout(fan_layout)
        
        # Fan controls
        fan_control = QHBoxLayout()
        self.fan_up = QPushButton("+")
        self.fan_down = QPushButton("-")
        fan_control.addWidget(self.fan_down)
        fan_control.addWidget(self.fan_up)
        layout.addLayout(fan_control)
        
        # AC power button
        self.power_button = QPushButton("Power")
        self.power_button.setCheckable(True)
        layout.addWidget(self.power_button)
        
        # Connect signals
        self.temp_up.clicked.connect(self.increase_temp)
        self.temp_down.clicked.connect(self.decrease_temp)
        self.fan_up.clicked.connect(self.increase_fan)
        self.fan_down.clicked.connect(self.decrease_fan)
        self.power_button.toggled.connect(self.toggle_power)
        
        # Setup periodic CAN message timer
        self.can_timer = QTimer()
        self.can_timer.timeout.connect(self.send_can_message)
        self.can_timer.start(5000)  # Send messages every 5000ms
        
        # Send initial message to update the HVAC model with starting values
        self.send_can_message()
        self.send_temperature_message()
        
        # Setup timer for SilKit event processing
        self.event_timer = QTimer()
        self.event_timer.timeout.connect(self.process_silkit_events)
        self.event_timer.start(100)  # Process events every 10ms
            
    def handle_can_frame(self, context, controller, frame_event):
        print("CAN frame handler called!")
        if not frame_event:
            print("Error: Received null frame_event pointer")
            return
        if not frame_event.contents.frame:
            print("Error: Received null frame pointer within frame_event")
            return
        
        # Print the frame details for debugging
        print("Received CAN frame:")
        print_can_frame(frame_event.contents.frame.contents)
        
        frame = frame_event.contents.frame.contents
        data_size = frame.data.size
        
        if frame.data.data and data_size > 0:
            received_data = [frame.data.data[i] for i in range(data_size)]
            
            # Handle Temperature Update Message (ID 0x125)
            if frame.id == 0x125 and data_size >= 2:
                # Cabin temperature is in the first byte, divided by 2 to get actual value
                cabin_temp = received_data[0] / 2.0
                # External temperature is in the second byte, divided by 2
                external_temp = received_data[1] / 2.0
                
                print(f"Updating temperatures: Cabin={cabin_temp:.1f}°C, External={external_temp:.1f}°C")
                
                # Update temperature displays
                self.cabin_temp = cabin_temp
                self.temp_display.display(cabin_temp)
                self.ext_temp_display.display(external_temp)
                
                # Update temperature source label
                self.temp_source_label.setText(f"Temperature: HVAC Model (Cabin: {cabin_temp:.1f}°C, Ext: {external_temp:.1f}°C)")
            
            # Also check for HVAC application's messages with ID 0x123
            elif frame.id == 0x123 and data_size >= 2:
                cabin_temp = received_data[0] / 2.0 if data_size > 0 else 0
                external_temp = received_data[1] / 2.0 if data_size > 1 else 0
                
                print(f"Updating temperatures from ID 0x123: Cabin={cabin_temp:.1f}°C, External={external_temp:.1f}°C")
                
                # Update temperature displays
                self.cabin_temp = cabin_temp
                self.temp_display.display(cabin_temp)
                self.ext_temp_display.display(external_temp)
                
                # Update temperature source label
                self.temp_source_label.setText(f"Temperature: HVAC Model (ID 0x123) (Cabin: {cabin_temp:.1f}°C, Ext: {external_temp:.1f}°C)")

    def send_can_message(self):
        # Create and initialize CAN frame
        frame = CanFrame()
        SilKit_Struct_Init(CanFrame, frame)

        # Set CAN frame fields
        frame.id = 0xAC1  # AC status ID
        frame.flags = 0
        frame.dlc = 3

        # Prepare data
        power_byte = 1 if self.power else 0
        fan_byte = self.fan_speed & 0xFF
        mode_byte = 0  # default 'auto'
        if self.mode == 'cool':
            mode_byte = 1
        elif self.mode == 'heat':
            mode_byte = 2

        data = bytearray([power_byte, fan_byte, mode_byte])
        data_len = len(data)
        frame.dlc = data_len

        # Assign data using cast and SilKit_ByteVector structure
        data_buffer = (c_uint8 * data_len)(*data)
        frame.data.data = cast(data_buffer, POINTER(c_uint8))
        frame.data.size = data_len

        # Send frame
        result = silkit.SilKit_CanController_SendFrame(self.can_controller, byref(frame), None)
        if result != 0:
            print(f"Warning: Failed to send CAN frame: {result}")
            
        # Send temperature setting message (ID 0x123)
        self.send_temperature_message()
            
    def send_temperature_message(self):
        # Create and initialize CAN frame for temperature setting
        frame = CanFrame()
        SilKit_Struct_Init(CanFrame, frame)
        
        # Set CAN frame fields
        frame.id = 0x123  # Temperature control ID
        frame.flags = 0
        frame.dlc = 3
        
        # Prepare data
        power_byte = 1 if self.power else 0
        # Convert temperature to 0.5°C resolution byte (multiply by 2)
        temp_byte = int(self.requested_temp * 2) & 0xFF
        fan_byte = self.fan_speed & 0xFF
        
        data = bytearray([power_byte, temp_byte, fan_byte])
        data_len = len(data)
        frame.dlc = data_len
        
        # Assign data using cast and SilKit_ByteVector structure
        data_buffer = (c_uint8 * data_len)(*data)
        frame.data.data = cast(data_buffer, POINTER(c_uint8))
        frame.data.size = data_len
        
        # Send frame
        result = silkit.SilKit_CanController_SendFrame(self.can_controller, byref(frame), None)
        if result != 0:
            print(f"Warning: Failed to send temperature CAN frame: {result}")
        else:
            print(f"Temperature CAN frame sent: Power={power_byte}, Temp={self.requested_temp}°C, Fan={fan_byte}")

    def increase_temp(self):
        if self.requested_temp < 30:
            self.requested_temp += 0.5
            self.req_temp_display.display(self.requested_temp)
            self.temp_source_label.setText(f"Temperature: Manual Control (Requested: {self.requested_temp:.1f}°C)")
            # Send an immediate update
            self.send_temperature_message()
            
    def decrease_temp(self):
        if self.requested_temp > 16:
            self.requested_temp -= 0.5
            self.req_temp_display.display(self.requested_temp)
            self.temp_source_label.setText(f"Temperature: Manual Control (Requested: {self.requested_temp:.1f}°C)")
            # Send an immediate update
            self.send_temperature_message()
            
    def increase_fan(self):
        if self.fan_speed < 5:
            self.fan_speed += 1
            self.fan_display.display(self.fan_speed)
            
    def decrease_fan(self):
        if self.fan_speed > 1:
            self.fan_speed -= 1
            self.fan_display.display(self.fan_speed)
            
    def toggle_power(self, state):
        # Update the power state
        self.power = state
        
        # Create and send a CAN message immediately to update power status
        print(f"Power state changed to: {'ON' if state else 'OFF'}, sending immediate CAN message")
        
        # Create a dedicated CAN frame for power status change
        frame = CanFrame()
        SilKit_Struct_Init(CanFrame, frame)
        
        # Set CAN frame fields - use a different ID for power-specific messages
        frame.id = 0xAC2  # Special ID for power status
        frame.flags = 0
        frame.dlc = 1
        
        # Include only the power status in this dedicated message
        power_byte = 1 if self.power else 0
        data = bytearray([power_byte])
        data_len = len(data)
        
        # Assign data using cast and SilKit_ByteVector structure
        data_buffer = (c_uint8 * data_len)(*data)
        frame.data.data = cast(data_buffer, POINTER(c_uint8))
        frame.data.size = data_len
        
        # Send the frame
        result = silkit.SilKit_CanController_SendFrame(self.can_controller, byref(frame), None)
        if result != 0:
            print(f"Warning: Failed to send power status CAN frame: {result}")
        else:
            print(f"Power status CAN frame sent successfully: {'ON' if state else 'OFF'}")
        
        # Also send a regular status update
        self.send_can_message()
        
        # Also send a temperature update
        self.send_temperature_message()
        
    def closeEvent(self, event):
        print("Shutting down AC Panel...")
        # Clean shutdown of SIL-Kit
        self.can_timer.stop()
        self.event_timer.stop()
        
        if hasattr(self, 'lifecycle_service') and self.lifecycle_service:
            print("Stopping lifecycle service...")
            silkit.SilKit_LifecycleService_Stop(self.lifecycle_service, b"Normal shutdown")
        
        if hasattr(self, 'handler_id') and self.can_controller:
            print("Removing CAN handler...")
            silkit.SilKit_CanController_RemoveFrameHandler(self.can_controller, self.handler_id)
            
        if hasattr(self, 'can_controller') and self.can_controller:
            print("Stopping CAN controller...")
            silkit.SilKit_CanController_Stop(self.can_controller)
            
        if hasattr(self, 'participant') and self.participant:
            print("Destroying participant...")
            silkit.SilKit_Participant_Destroy(self.participant)
            
        if hasattr(self, 'participant_config') and self.participant_config:
            print("Destroying participant configuration...")
            silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)
            
        print("Shutdown complete.")
        event.accept()
        
    def process_silkit_events(self):
        # This is a periodic callback that allows SilKit to process events
        # Nothing to do here as SilKit handles events in its own thread
        pass

def main():
    app = QApplication(sys.argv)
    window = ACPanel()
    window.show()
    sys.exit(app.exec())
    
if __name__ == '__main__':
    main() 