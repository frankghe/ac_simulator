import tkinter as tk
from tkinter import ttk
import json
import ctypes
from ctypes import c_void_p, c_char_p, c_uint32, c_uint8, c_uint64, POINTER, Structure, c_int, c_int8, byref
import threading
import time

# Load SIL-Kit shared library
silkit = ctypes.CDLL('/home/frank/projects/sil-kit/build/Release/libSilKit.so')

# Define SIL-Kit constants
SILKIT_DIRECTION_RX = 1
SILKIT_OPERATIONMODE_AUTONOMOUS = 20

# Define SIL-Kit structs
class CanFrame(Structure):
    _fields_ = [
        ("id", c_uint32),
        ("flags", c_uint32),
        ("dlc", c_uint8),
        ("data", c_uint8 * 8)
    ]

class SilKit_StructHeader(Structure):
    _fields_ = [
        ("version", c_uint64),
        ("_reserved", c_uint64 * 3)
    ]

class SilKit_LifecycleConfiguration(Structure):
    _fields_ = [
        ("structHeader", SilKit_StructHeader),
        ("operationMode", c_int8)
    ]

# Define CAN frame handler callback type
CAN_FRAME_HANDLER = ctypes.CFUNCTYPE(None, c_void_p, POINTER(CanFrame), c_void_p)

class ACControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AC Control System")
        
        # Initialize SIL-Kit
        self.participant = None
        self.can_controller = None
        self.lifecycle_service = None
        self.handler_id = None
        self.participant_config = None
        self.setup_silkit()
        
        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Temperature display
        ttk.Label(main_frame, text="Current Temperature:").grid(row=0, column=0, sticky=tk.W)
        self.temp_label = ttk.Label(main_frame, text="0.0°C")
        self.temp_label.grid(row=0, column=1, sticky=tk.W)
        
        # AC Status
        ttk.Label(main_frame, text="AC Status:").grid(row=1, column=0, sticky=tk.W)
        self.status_label = ttk.Label(main_frame, text="Off")
        self.status_label.grid(row=1, column=1, sticky=tk.W)
        
        # Temperature setpoint
        ttk.Label(main_frame, text="Setpoint:").grid(row=2, column=0, sticky=tk.W)
        self.setpoint_var = tk.DoubleVar(value=22.0)
        self.setpoint_entry = ttk.Entry(main_frame, textvariable=self.setpoint_var)
        self.setpoint_entry.grid(row=2, column=1, sticky=tk.W)
        
        # Update button
        self.update_btn = ttk.Button(main_frame, text="Update Setpoint", command=self.update_setpoint)
        self.update_btn.grid(row=3, column=0, columnspan=2, pady=5)
        
        # Start the SIL-Kit lifecycle
        self.start_lifecycle()
        
        # Start the temperature update thread
        self.running = True
        self.update_thread = threading.Thread(target=self.update_temperature)
        self.update_thread.daemon = True
        self.update_thread.start()

    def setup_silkit(self):
        # Create participant configuration
        self.participant_config = c_void_p()
        result = silkit.SilKit_ParticipantConfiguration_FromString(byref(self.participant_config), b"{}")
        if result != 0:
            raise RuntimeError(f"Failed to create participant configuration: {result}")

        # Create participant
        self.participant = c_void_p()
        result = silkit.SilKit_Participant_Create(
            byref(self.participant),
            b"ac_control_gui",
            b"silkit://localhost:8500",
            self.participant_config
        )
        if result != 0:
            raise RuntimeError(f"Failed to create participant: {result}")

        # Create CAN controller
        self.can_controller = c_void_p()
        result = silkit.SilKit_CanController_Create(
            byref(self.can_controller),
            self.participant,
            b"CAN1"
        )
        if result != 0:
            raise RuntimeError(f"Failed to create CAN controller: {result}")

        # Create lifecycle configuration
        lifecycle_config = SilKit_LifecycleConfiguration()
        lifecycle_config.structHeader.version = ((83 << 56) | (75 << 48) | (7 << 40) | (2 << 32) | (1 << 24))  # SK_ID_MAKE(Participant, SilKit_LifecycleConfiguration)
        lifecycle_config.operationMode = SILKIT_OPERATIONMODE_AUTONOMOUS

        # Create lifecycle service
        self.lifecycle_service = c_void_p()
        result = silkit.SilKit_LifecycleService_Create(
            byref(self.lifecycle_service),
            self.participant,
            byref(lifecycle_config)
        )
        if result != 0:
            raise RuntimeError(f"Failed to create lifecycle service: {result}")

        # Register CAN frame handler
        self.handler_id = c_uint32()
        result = silkit.SilKit_CanController_AddFrameHandler(
            self.can_controller,
            None,
            CAN_FRAME_HANDLER(self.handle_can_frame),
            SILKIT_DIRECTION_RX,
            byref(self.handler_id)
        )
        if result != 0:
            raise RuntimeError(f"Failed to add CAN handler: {result}")

    def start_lifecycle(self):
        result = silkit.SilKit_LifecycleService_StartLifecycle(self.lifecycle_service)
        if result != 0:
            raise RuntimeError(f"Failed to start lifecycle: {result}")

    def handle_can_frame(self, controller, frame, user_data):
        # Process temperature data (ID 0x100)
        if frame.contents.id == 0x100:
            temp_bytes = bytes(frame.contents.data[:4])
            temperature = int.from_bytes(temp_bytes, byteorder='little', signed=True) / 10.0
            self.temp_label.config(text=f"{temperature}°C")
        
        # Process AC status (ID 0x200)
        elif frame.contents.id == 0x200:
            status = frame.contents.data[0]
            status_text = "On" if status == 1 else "Off"
            self.status_label.config(text=status_text)

    def update_setpoint(self):
        setpoint = self.setpoint_var.get()
        # Convert setpoint to bytes (multiply by 10 to keep one decimal place)
        setpoint_int = int(setpoint * 10)
        setpoint_bytes = setpoint_int.to_bytes(4, byteorder='little', signed=True)
        
        # Create CAN frame
        frame = CanFrame()
        frame.id = 0x300  # Setpoint message ID
        frame.dlc = 4
        frame.flags = 0
        for i, b in enumerate(setpoint_bytes):
            frame.data[i] = b
        
        # Send CAN frame
        result = silkit.SilKit_CanController_SendFrame(self.can_controller, byref(frame))
        if result != 0:
            print(f"Failed to send setpoint: {result}")

    def update_temperature(self):
        while self.running:
            time.sleep(0.1)  # Small delay to prevent high CPU usage
            self.root.update_idletasks()

    def cleanup(self):
        self.running = False
        if self.handler_id is not None:
            silkit.SilKit_CanController_RemoveFrameHandler(self.can_controller, self.handler_id)
        if self.lifecycle_service is not None:
            silkit.SilKit_LifecycleService_Stop(self.lifecycle_service)
            silkit.SilKit_LifecycleService_Destroy(self.lifecycle_service)
        if self.can_controller is not None:
            silkit.SilKit_CanController_Destroy(self.can_controller)
        if self.participant is not None:
            silkit.SilKit_Participant_Destroy(self.participant)
        if self.participant_config is not None:
            silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)

if __name__ == "__main__":
    root = tk.Tk()
    app = ACControlGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.cleanup)
    root.mainloop() 