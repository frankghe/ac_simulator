#!/usr/bin/env python3
import ctypes
from ctypes import (c_void_p, c_char_p, c_uint32, c_uint8, c_uint64, c_uint16,
                   POINTER, Structure, c_int, c_int8, byref, c_size_t, cast,
                   memset, sizeof)
import signal
import time

# Load SIL-Kit shared library
silkit = ctypes.CDLL("/home/frank/projects/sil-kit/build/Release/libSilKit.so")

# Define SIL-Kit constants
SILKIT_DIRECTION_ANY = 3  # Receive AND transmit

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

silkit.SilKit_LifecycleService_Stop.argtypes = [c_void_p, c_char_p]
silkit.SilKit_LifecycleService_Stop.restype = c_int

silkit.SilKit_Participant_Destroy.argtypes = [c_void_p]
silkit.SilKit_Participant_Destroy.restype = None

silkit.SilKit_ParticipantConfiguration_Destroy.argtypes = [c_void_p]
silkit.SilKit_ParticipantConfiguration_Destroy.restype = None

# Global variable to control the main loop
running = True

def signal_handler(sig, frame):
    global running
    print("\nShutting down...")
    running = False

# Function to print CAN frame details
def print_can_frame(frame, direction):
    if not frame:
        print("CAN Frame is NULL")
        return
    
    direction_str = "TX" if direction == 1 else "RX" if direction == 2 else "??"
    
    print(f"CAN Frame ({direction_str}):")
    print(f"  ID: 0x{frame.id:x}")
    print(f"  Flags: 0x{frame.flags:x}")
    print(f"  DLC: {frame.dlc}")
    
    if frame.data.data and frame.data.size > 0:
        data_array = [frame.data.data[i] for i in range(frame.data.size)]
        print(f"  Data size: {frame.data.size}")
        print(f"  Data: {data_array}")
    else:
        print("  Data: NULL")
    print("------")

# Get user-friendly error description
def get_error_string(error_code):
    error_strings = {
        0: "SUCCESS",
        1: "UNSPECIFIEDERROR",
        2: "NOTSUPPORTED",
        3: "NOTIMPLEMENTED",
        4: "BADPARAMETER",
        5: "BUFFERTOOSMALL",
        6: "TIMEOUT",
        7: "UNSUPPORTEDSERVICE",
        8: "WRONGSTATE",
        9: "TYPECONVERSIONERROR",
        10: "CONFIGURATIONERROR",
        11: "PROTOCOLERROR",
        12: "ASSERTIONERROR",
        13: "EXTENSIONERROR",
        14: "LOGICERROR",
        15: "LENGTHERROR",
        16: "OUTOFRANGEERROR"
    }
    return error_strings.get(error_code, f"UNKNOWN_ERROR({error_code})")

class CANMonitor:
    def __init__(self):
        self.registry_uri = b"silkit://localhost:8500"
        self.participant_name = b"CAN_Monitor"
        
        print(f"Connecting to SilKit registry at {self.registry_uri.decode()}")
        
        # Create participant configuration
        self.participant_config = c_void_p()
        result = silkit.SilKit_ParticipantConfiguration_FromString(byref(self.participant_config), b"{}")
        if result != 0:
            raise RuntimeError(f"Failed to create participant configuration: {get_error_string(result)}")
        print("Participant configuration created")
        
        # Create participant
        self.participant = c_void_p()
        result = silkit.SilKit_Participant_Create(
            byref(self.participant),
            self.participant_config,
            self.participant_name,
            self.registry_uri
        )
        if result != 0:
            silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)
            raise RuntimeError(f"Failed to create participant: {get_error_string(result)}")
        print("Participant created")
        
        # Create separate controllers for different known networks
        self.controllers = []
        self.handler_ids = []
        
        # Monitor different CAN networks
        self.networks = [b"CAN1", b"ANY_CAN_NETWORK"]
        
        for i, network in enumerate(self.networks):
            # Create controller for this network
            controller = c_void_p()
            controller_name = f"Monitor{i}".encode('utf-8')
            result = silkit.SilKit_CanController_Create(
                byref(controller),
                self.participant,
                controller_name,
                network
            )
            if result != 0:
                print(f"Warning: Failed to create CAN controller for {network.decode()}: {get_error_string(result)}")
                continue
                
            print(f"Created CAN controller for network: {network.decode()}")
            self.controllers.append(controller)
            
            # Register callback for this controller
            self.setup_can_handler(controller, network)
            
            # Start the controller
            result = silkit.SilKit_CanController_Start(controller)
            if result != 0:
                print(f"Warning: Failed to start CAN controller for {network.decode()}: {get_error_string(result)}")
                continue
                
            print(f"Started CAN controller for {network.decode()}")
        
        # Create lifecycle configuration
        lifecycle_config = SilKit_LifecycleConfiguration()
        memset(byref(lifecycle_config), 0, sizeof(lifecycle_config))
        lifecycle_config.structHeader.version = ((83 << 56) | (75 << 48) | (7 << 40) | (2 << 32) | (1 << 24))
        lifecycle_config.operationMode = 20  # SilKit_OperationMode_Autonomous
        
        # Create lifecycle service
        self.lifecycle_service = c_void_p()
        result = silkit.SilKit_LifecycleService_Create(
            byref(self.lifecycle_service),
            self.participant,
            byref(lifecycle_config)
        )
        if result != 0:
            silkit.SilKit_Participant_Destroy(self.participant)
            silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)
            raise RuntimeError(f"Failed to create lifecycle service: {get_error_string(result)}")
        print("Lifecycle service created")
        
        # Start lifecycle
        result = silkit.SilKit_LifecycleService_StartLifecycle(self.lifecycle_service)
        if result != 0:
            print(f"Warning: Failed to start lifecycle: {get_error_string(result)}")
        else:
            print("Lifecycle started")
        
        print(f"\n✅ Monitoring CAN traffic on networks: {', '.join([n.decode() for n in self.networks])}")
        print("Press Ctrl+C to stop monitoring\n")
        
    def setup_can_handler(self, controller, network):
        # We need to create a unique handler for each controller
        # and store it to prevent garbage collection
        
        # Create a closure that captures self and network name
        def create_handler(self_ref, network_name):
            @ctypes.CFUNCTYPE(None, c_void_p, c_void_p, POINTER(CanFrameEvent))
            def frame_handler(context, controller, frame_event):
                if not frame_event:
                    return
                if not frame_event.contents.frame:
                    return
                    
                print(f"\nNetwork: {network_name.decode()}")
                print_can_frame(frame_event.contents.frame.contents, frame_event.contents.direction)
            
            return frame_handler
            
        handler = create_handler(self, network)
        
        # Store the handler to prevent garbage collection
        # We need to store it in an instance variable so it persists
        if not hasattr(self, 'frame_handlers'):
            self.frame_handlers = []
        self.frame_handlers.append(handler)
        
        # Register the handler
        handler_id = c_uint32()
        result = silkit.SilKit_CanController_AddFrameHandler(
            controller,
            None,
            handler,
            SILKIT_DIRECTION_ANY,  # Monitor both RX and TX
            byref(handler_id)
        )
        if result != 0:
            print(f"Warning: Failed to add frame handler for {network.decode()}: {get_error_string(result)}")
        else:
            print(f"Added frame handler for {network.decode()}")
            self.handler_ids.append(handler_id)
    
    def cleanup(self):
        print("Cleaning up resources...")
        
        # Stop lifecycle service
        if hasattr(self, 'lifecycle_service') and self.lifecycle_service:
            silkit.SilKit_LifecycleService_Stop(self.lifecycle_service, b"Normal shutdown")
            print("Lifecycle stopped")
        
        # Destroy participant
        if hasattr(self, 'participant') and self.participant:
            silkit.SilKit_Participant_Destroy(self.participant)
            print("Participant destroyed")
        
        # Destroy configuration
        if hasattr(self, 'participant_config') and self.participant_config:
            silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)
            print("Configuration destroyed")

def main():
    # Set up signal handler for clean shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    monitor = None
    try:
        # Create and initialize the CAN monitor
        monitor = CANMonitor()
        
        # Main loop - just wait for frames
        global running
        while running:
            time.sleep(0.1)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if monitor:
            monitor.cleanup()
        print("Done.")

if __name__ == "__main__":
    main() 