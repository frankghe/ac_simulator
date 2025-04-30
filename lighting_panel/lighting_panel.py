#!/usr/bin/env python3
import sys
import ctypes
from ctypes import (c_void_p, c_char_p, c_uint32, c_uint8, c_uint64, c_uint16,
                   POINTER, Structure, c_int, c_int8, byref, c_size_t, cast,
                   memset, sizeof)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QHBoxLayout, QGroupBox, QRadioButton, QLabel,
                            QButtonGroup)
from PyQt6.QtCore import Qt, QTimer
import time
import os
import logging
from enum import Enum
from datetime import datetime, timedelta

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

silkit.SilKit_ParticipantConfiguration_FromFile.argtypes = [POINTER(c_void_p), c_char_p]
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

# CAN message IDs
LIGHTING_CONTROL_ID = 0x110
LIGHTING_STATUS_ID = 0x111

# Lighting states
LIGHT_OFF = 0
LIGHT_ON = 1
BLINKER_LEFT = 2
BLINKER_RIGHT = 3
HAZARD_LIGHTS = 4

class PendingState(Enum):
    NONE = 0
    PENDING = 1
    TIMEOUT = 2

class LightingPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lighting Control Panel")
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('LightingPanel')
        
        # SIL-Kit setup variables
        self.registry_uri = b"silkit://localhost:8500"
        self.participant_name = f"Lighting_Panel_{int(time.time())}".encode('utf-8')
        self.can_network_name = b"CAN1"
        
        self.logger.info(f"Lighting Panel initializing with name {self.participant_name.decode()}")
        
        # Initialize state
        self.headlight_state = LIGHT_OFF
        self.blinker_state = LIGHT_OFF
        self.hazard_state = LIGHT_OFF
        
        # Initialize pending states
        self.pending_headlight = PendingState.NONE
        self.pending_blinker = PendingState.NONE
        self.pending_hazard = PendingState.NONE
        
        # Initialize timeout tracking
        self.pending_timeout = timedelta(seconds=1)  # 1 second timeout
        self.pending_timestamps = {
            'headlight': None,
            'blinker': None,
            'hazard': None
        }
        
        # Track last sent state
        self.last_sent_state = {
            'headlight': LIGHT_OFF,
            'blinker': LIGHT_OFF,
            'hazard': LIGHT_OFF
        }
        
        # Initialize SIL-Kit
        self.initialize_silkit()
        
        # Create GUI
        self.create_gui()
        
        # Set up periodic CAN message timer
        self.can_timer = QTimer()
        self.can_timer.timeout.connect(self.send_periodic_update)
        self.can_timer.start(2000)  # Send every 2 second
        
        # Set up timeout check timer
        self.timeout_timer = QTimer()
        self.timeout_timer.timeout.connect(self.check_pending_timeouts)
        self.timeout_timer.start(100)  # Check every 100ms
        
        self.logger.info("Lighting Panel initialized successfully")

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

        # Start lifecycle service
        print("Starting lifecycle service...")
        result = silkit.SilKit_LifecycleService_StartLifecycle(self.lifecycle_service)
        if result != 0:
            silkit.SilKit_Participant_Destroy(self.participant)
            silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)
            raise RuntimeError(f"Failed to start lifecycle service: {result}")
        print("Lifecycle service started.")

    def create_gui(self):
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Create two main sections
        control_group = QGroupBox("Lighting Control")
        status_group = QGroupBox("Lighting Status")
        
        # Control section layout
        control_layout = QVBoxLayout()
        
        # Headlights control
        headlight_group = QGroupBox("Headlights")
        headlight_layout = QHBoxLayout()
        
        self.headlight_group = QButtonGroup()
        self.headlight_off = QRadioButton("Off")
        self.headlight_on = QRadioButton("On")
        self.headlight_group.addButton(self.headlight_off, LIGHT_OFF)
        self.headlight_group.addButton(self.headlight_on, LIGHT_ON)
        self.headlight_off.setChecked(True)
        
        headlight_layout.addWidget(self.headlight_off)
        headlight_layout.addWidget(self.headlight_on)
        headlight_group.setLayout(headlight_layout)
        control_layout.addWidget(headlight_group)
        
        # Blinkers control
        blinker_group = QGroupBox("Blinkers")
        blinker_layout = QHBoxLayout()
        
        self.blinker_group = QButtonGroup()
        self.blinker_off = QRadioButton("Off")
        self.blinker_left = QRadioButton("Left")
        self.blinker_right = QRadioButton("Right")
        self.blinker_group.addButton(self.blinker_off, LIGHT_OFF)
        self.blinker_group.addButton(self.blinker_left, BLINKER_LEFT)
        self.blinker_group.addButton(self.blinker_right, BLINKER_RIGHT)
        self.blinker_off.setChecked(True)
        
        blinker_layout.addWidget(self.blinker_off)
        blinker_layout.addWidget(self.blinker_left)
        blinker_layout.addWidget(self.blinker_right)
        blinker_group.setLayout(blinker_layout)
        control_layout.addWidget(blinker_group)
        
        # Hazard lights control
        hazard_group = QGroupBox("Hazard Lights")
        hazard_layout = QHBoxLayout()
        
        self.hazard_group = QButtonGroup()
        self.hazard_off = QRadioButton("Off")
        self.hazard_on = QRadioButton("On")
        self.hazard_group.addButton(self.hazard_off, LIGHT_OFF)
        self.hazard_group.addButton(self.hazard_on, HAZARD_LIGHTS)
        self.hazard_off.setChecked(True)
        
        hazard_layout.addWidget(self.hazard_off)
        hazard_layout.addWidget(self.hazard_on)
        hazard_group.setLayout(hazard_layout)
        control_layout.addWidget(hazard_group)
        
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        # Status section layout
        status_layout = QVBoxLayout()
        
        # Headlights status
        headlight_status = QHBoxLayout()
        headlight_status.addWidget(QLabel("Headlights:"))
        self.headlight_status = QLabel("OFF")
        self.headlight_status.setStyleSheet("QLabel { color: red; }")
        headlight_status.addWidget(self.headlight_status)
        headlight_status.addStretch()
        status_layout.addLayout(headlight_status)
        
        # Blinkers status
        blinker_status = QHBoxLayout()
        blinker_status.addWidget(QLabel("Blinkers:"))
        self.blinker_status = QLabel("OFF")
        self.blinker_status.setStyleSheet("QLabel { color: red; }")
        blinker_status.addWidget(self.blinker_status)
        blinker_status.addStretch()
        status_layout.addLayout(blinker_status)
        
        # Hazard lights status
        hazard_status = QHBoxLayout()
        hazard_status.addWidget(QLabel("Hazard Lights:"))
        self.hazard_status = QLabel("OFF")
        self.hazard_status.setStyleSheet("QLabel { color: red; }")
        hazard_status.addWidget(self.hazard_status)
        hazard_status.addStretch()
        status_layout.addLayout(hazard_status)
        
        # Add a visual indicator for blinkers
        self.blinker_indicator = QLabel()
        self.blinker_indicator.setFixedSize(50, 50)
        self.blinker_indicator.setStyleSheet("""
            QLabel {
                background-color: red;
                border-radius: 25px;
                border: 2px solid black;
            }
        """)
        self.blinker_indicator.hide()
        status_layout.addWidget(self.blinker_indicator, alignment=Qt.AlignmentFlag.AlignCenter)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # Connect signals
        self.headlight_group.buttonClicked.connect(self.on_headlight_change)
        self.blinker_group.buttonClicked.connect(self.on_blinker_change)
        self.hazard_group.buttonClicked.connect(self.on_hazard_change)
        
        # Set up blinker animation timer
        self.blinker_timer = QTimer()
        self.blinker_timer.timeout.connect(self.update_blinker_indicator)
        self.blinker_timer.start(500)  # 500ms interval for blinking

    def check_pending_timeouts(self):
        current_time = datetime.now()
        
        # Check headlight timeout
        if (self.pending_headlight == PendingState.PENDING and 
            self.pending_timestamps['headlight'] and 
            current_time - self.pending_timestamps['headlight'] > self.pending_timeout):
            self.logger.warning("Headlight change timeout")
            self.pending_headlight = PendingState.TIMEOUT
            self.update_gui()
            
        # Check blinker timeout
        if (self.pending_blinker == PendingState.PENDING and 
            self.pending_timestamps['blinker'] and 
            current_time - self.pending_timestamps['blinker'] > self.pending_timeout):
            self.logger.warning("Blinker change timeout")
            self.pending_blinker = PendingState.TIMEOUT
            self.update_gui()
            
        # Check hazard timeout
        if (self.pending_hazard == PendingState.PENDING and 
            self.pending_timestamps['hazard'] and 
            current_time - self.pending_timestamps['hazard'] > self.pending_timeout):
            self.logger.warning("Hazard change timeout")
            self.pending_hazard = PendingState.TIMEOUT
            self.update_gui()

    def update_blinker_indicator(self):
        # Only show blinking indicator if the state is confirmed (not pending)
        if self.pending_blinker == PendingState.NONE and self.pending_hazard == PendingState.NONE:
            if self.hazard_state:
                # Hazard lights override blinkers
                self.blinker_indicator.setVisible(not self.blinker_indicator.isVisible())
            elif self.blinker_state == BLINKER_LEFT:
                # Left blinker
                self.blinker_indicator.setVisible(not self.blinker_indicator.isVisible())
            elif self.blinker_state == BLINKER_RIGHT:
                # Right blinker
                self.blinker_indicator.setVisible(not self.blinker_indicator.isVisible())
            else:
                # No blinking state active
                self.blinker_indicator.hide()
        else:
            # Hide indicator if state is pending
            self.blinker_indicator.hide()

    def update_gui(self):
        # Update radio buttons and status labels
        if self.pending_headlight == PendingState.PENDING:
            self.headlight_status.setText("PENDING")
            self.headlight_status.setStyleSheet("QLabel { color: orange; }")
        elif self.pending_headlight == PendingState.TIMEOUT:
            self.headlight_status.setText("TIMEOUT")
            self.headlight_status.setStyleSheet("QLabel { color: red; }")
        else:
            if self.headlight_state == LIGHT_ON:
                self.headlight_on.setChecked(True)
                self.headlight_status.setText("ON")
                self.headlight_status.setStyleSheet("QLabel { color: green; }")
            else:
                self.headlight_off.setChecked(True)
                self.headlight_status.setText("OFF")
                self.headlight_status.setStyleSheet("QLabel { color: red; }")
        
        if self.pending_blinker == PendingState.PENDING:
            self.blinker_status.setText("PENDING")
            self.blinker_status.setStyleSheet("QLabel { color: orange; }")
        elif self.pending_blinker == PendingState.TIMEOUT:
            self.blinker_status.setText("TIMEOUT")
            self.blinker_status.setStyleSheet("QLabel { color: red; }")
        else:
            if self.blinker_state == BLINKER_LEFT:
                self.blinker_left.setChecked(True)
                self.blinker_status.setText("LEFT")
                self.blinker_status.setStyleSheet("QLabel { color: orange; }")
            elif self.blinker_state == BLINKER_RIGHT:
                self.blinker_right.setChecked(True)
                self.blinker_status.setText("RIGHT")
                self.blinker_status.setStyleSheet("QLabel { color: orange; }")
            else:
                self.blinker_off.setChecked(True)
                self.blinker_status.setText("OFF")
                self.blinker_status.setStyleSheet("QLabel { color: red; }")
        
        if self.pending_hazard == PendingState.PENDING:
            self.hazard_status.setText("PENDING")
            self.hazard_status.setStyleSheet("QLabel { color: orange; }")
        elif self.pending_hazard == PendingState.TIMEOUT:
            self.hazard_status.setText("TIMEOUT")
            self.hazard_status.setStyleSheet("QLabel { color: red; }")
        else:
            if self.hazard_state == HAZARD_LIGHTS:
                self.hazard_on.setChecked(True)
                self.hazard_status.setText("ON")
                self.hazard_status.setStyleSheet("QLabel { color: orange; }")
            else:
                self.hazard_off.setChecked(True)
                self.hazard_status.setText("OFF")
                self.hazard_status.setStyleSheet("QLabel { color: red; }")

    def handle_can_frame(self, context, controller, frame_event):
        if not frame_event or not frame_event.contents.frame:
            return
        
        frame = frame_event.contents.frame.contents
        if frame.id == LIGHTING_STATUS_ID:
            # Update state from received message
            data = [frame.data.data[i] for i in range(frame.data.size)]
            if len(data) >= 3:
                # Clear pending and timeout states
                if self.pending_headlight != PendingState.NONE:
                    self.pending_headlight = PendingState.NONE
                    self.pending_timestamps['headlight'] = None
                
                if self.pending_blinker != PendingState.NONE:
                    self.pending_blinker = PendingState.NONE
                    self.pending_timestamps['blinker'] = None
                
                if self.pending_hazard != PendingState.NONE:
                    self.pending_hazard = PendingState.NONE
                    self.pending_timestamps['hazard'] = None
                
                # Update states to match ECU
                self.headlight_state = data[0]
                self.blinker_state = data[1]
                self.hazard_state = data[2]
                
                self.logger.info(f"Received status update: headlight={data[0]}, blinker={data[1]}, hazard={data[2]}")
                
                # Update GUI
                self.update_gui()

    def send_periodic_update(self):
        """Send periodic update if state has changed or if there are pending changes"""
        self.logger.info("Periodic update check")
        self.logger.info(f"Current state: headlight={self.headlight_state}, blinker={self.blinker_state}, hazard={self.hazard_state}")
        self.logger.info(f"Last sent state: headlight={self.last_sent_state['headlight']}, blinker={self.last_sent_state['blinker']}, hazard={self.last_sent_state['hazard']}")
        self.logger.info(f"Pending states: headlight={self.pending_headlight}, blinker={self.pending_blinker}, hazard={self.pending_hazard}")
        
        if (self.headlight_state != self.last_sent_state['headlight'] or
            self.blinker_state != self.last_sent_state['blinker'] or
            self.hazard_state != self.last_sent_state['hazard'] or
            self.pending_headlight == PendingState.PENDING or
            self.pending_blinker == PendingState.PENDING or
            self.pending_hazard == PendingState.PENDING):
            
            self.logger.info("State change detected, sending update")
            if self.send_control_message():
                self.last_sent_state = {
                    'headlight': self.headlight_state,
                    'blinker': self.blinker_state,
                    'hazard': self.hazard_state
                }
                self.logger.info("Periodic update sent successfully")
        else:
            self.logger.info("No state change, skipping update")

    def send_control_message(self):
        # Create and initialize CAN frame
        frame = CanFrame()
        SilKit_Struct_Init(CanFrame, frame)
        
        # Set frame properties
        frame.id = LIGHTING_CONTROL_ID
        frame.flags = 0
        frame.dlc = 3
        
        # Create data array
        data = (c_uint8 * 3)(self.headlight_state, self.blinker_state, self.hazard_state)
        frame.data.data = cast(data, POINTER(c_uint8))
        frame.data.size = 3
        
        # Send frame
        result = silkit.SilKit_CanController_SendFrame(self.can_controller, byref(frame), None)
        if result != 0:
            self.logger.error(f"Failed to send CAN frame: {result}")
            return False
        
        self.logger.info(f"Sent control message: headlight={self.headlight_state}, blinker={self.blinker_state}, hazard={self.hazard_state}")
        return True

    def on_headlight_change(self, button):
        new_state = self.headlight_group.id(button)
        if new_state != self.headlight_state:
            self.headlight_state = new_state
            self.pending_headlight = PendingState.PENDING
            self.pending_timestamps['headlight'] = datetime.now()
            if self.send_control_message():
                self.update_gui()

    def on_blinker_change(self, button):
        new_state = self.blinker_group.id(button)
        if new_state != self.blinker_state:
            self.blinker_state = new_state
            self.pending_blinker = PendingState.PENDING
            self.pending_timestamps['blinker'] = datetime.now()
            if self.send_control_message():
                self.update_gui()

    def on_hazard_change(self, button):
        new_state = self.hazard_group.id(button)
        if new_state != self.hazard_state:
            self.hazard_state = new_state
            self.pending_hazard = PendingState.PENDING
            self.pending_timestamps['hazard'] = datetime.now()
            if self.send_control_message():
                self.update_gui()

    def closeEvent(self, event):
        # Stop timers
        self.can_timer.stop()
        self.timeout_timer.stop()
        
        # Stop CAN controller
        silkit.SilKit_CanController_Stop(self.can_controller)
        
        # Remove frame handler
        silkit.SilKit_CanController_RemoveFrameHandler(self.can_controller, self.handler_id)
        
        # Stop lifecycle service
        silkit.SilKit_LifecycleService_Stop(self.lifecycle_service, b"")
        
        # Clean up resources
        silkit.SilKit_Participant_Destroy(self.participant)
        silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)
        
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = LightingPanel()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 