import ctypes
from ctypes import (c_void_p, c_char_p, c_uint32, c_uint8, c_uint64, c_uint16,
                   POINTER, Structure, c_int, c_size_t, cast, memset, sizeof, byref)
import argparse
import time

# Load SIL-Kit shared library
silkit = ctypes.CDLL('/home/frank/projects/sil-kit/build/Release/libSilKit.so')

# Keep a global reference to the callback pointer to prevent garbage collection
_global_frame_handler_ptr = None

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

# Define the callback function type FIRST
# Correct signature: void(void* context, SilKit_CanController* controller, SilKit_CanFrameEvent* frameEvent)
FrameHandlerType = ctypes.CFUNCTYPE(None, c_void_p, c_void_p, POINTER(CanFrameEvent))

# Define SIL-Kit constants
SILKIT_CANFRAMEFLAG_IDE = 1 << 9  # Identifier Extension
SILKIT_OPERATIONMODE_AUTONOMOUS = 0
SILKIT_OPERATIONMODE_COORDINATED = 1

# Define function signatures
silkit.SilKit_ParticipantConfiguration_FromString.argtypes = [POINTER(c_void_p), c_char_p]
silkit.SilKit_ParticipantConfiguration_FromString.restype = c_int

silkit.SilKit_Participant_Create.argtypes = [POINTER(c_void_p), c_void_p, c_char_p, c_char_p]
silkit.SilKit_Participant_Create.restype = c_int

silkit.SilKit_CanController_Create.argtypes = [POINTER(c_void_p), c_void_p, c_char_p, c_char_p]
silkit.SilKit_CanController_Create.restype = c_int

silkit.SilKit_CanController_Start.argtypes = [c_void_p]
silkit.SilKit_CanController_Start.restype = c_int

silkit.SilKit_CanController_SendFrame.argtypes = [c_void_p, POINTER(CanFrame), c_void_p]
silkit.SilKit_CanController_SendFrame.restype = c_int

silkit.SilKit_CanController_SetBaudRate.argtypes = [c_void_p, c_uint32, c_uint32, c_uint32]
silkit.SilKit_CanController_SetBaudRate.restype = c_int

silkit.SilKit_CanController_AddFrameHandler.argtypes = [c_void_p, c_void_p, FrameHandlerType, c_uint32, POINTER(c_uint32)]
silkit.SilKit_CanController_AddFrameHandler.restype = c_int

silkit.SilKit_LifecycleService_Create.argtypes = [POINTER(c_void_p), c_void_p, POINTER(SilKit_LifecycleConfiguration)]
silkit.SilKit_LifecycleService_Create.restype = c_int

# Define SIL-Kit macros
def SilKit_Struct_Init(struct_type, struct_instance):
    memset(byref(struct_instance), 0, sizeof(struct_instance))
    if struct_type == CanFrame:
        struct_instance.structHeader.version = ((83 << 56) | (75 << 48) | (1 << 40) | (1 << 32) | (1 << 24))  # SK_ID_MAKE(Can, SilKit_CanFrame)
    elif struct_type == SilKit_LifecycleConfiguration:
        struct_instance.structHeader.version = ((83 << 56) | (75 << 48) | (7 << 40) | (2 << 32) | (1 << 24))  # SK_ID_MAKE(Participant, SilKit_LifecycleConfiguration)

# Function to receive a CAN frame
def receive_can_frame(can_controller):
    global _global_frame_handler_ptr # Declare we are using the global variable

    # Create a frame handler callback function
    def frame_handler(context, controller, frame_event):
        # Access the CanFrame via the pointer
        # Add a check for null pointer before accessing contents
        if not frame_event:
            print("Error: Received null frame_event pointer.")
            return
        if not frame_event.contents.frame:
            print("Error: Received null frame pointer within frame_event.")
            return

        frame = frame_event.contents.frame.contents
        print(f"\nReceived CAN frame:")
        print(f"ID: {frame.id}")
        print(f"Flags: {frame.flags}")
        print(f"DLC: {frame.dlc}")
        # Access data through the pointer structure
        data_size = frame.data.size
        if frame.data.data and data_size > 0:
            print(f"Data: {[frame.data.data[i] for i in range(data_size)]}")
        else:
            print("Data: (empty or null)")
        print(f"Timestamp: {frame_event.contents.timestamp}")
        print(f"Direction: {frame_event.contents.direction}")

    # Create a function pointer for the frame handler
    # The callback signature expected by C: void(void* context, SilKit_CanController* controller, SilKit_CanFrameEvent* frameEvent)
    # Our Python callback definition matches this order now.
    frame_handler_ptr = FrameHandlerType(frame_handler)

    # Store the pointer in a global variable to prevent garbage collection
    _global_frame_handler_ptr = frame_handler_ptr

    # Add frame handler to CAN controller
    handler_id = c_uint32()
    result = silkit.SilKit_CanController_AddFrameHandler(
        can_controller,
        None,  # No user context needed
        frame_handler_ptr,
        2,     # Direction RX (2 for receive)
        byref(handler_id)
    )
    if result != 0:
        print(f"Failed to add frame handler: {result}")
        return

    print(f"Frame handler added successfully with ID: {handler_id.value}")
    print("Waiting for CAN frames...")

    # Keep the program running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping receiver...")

# Main function to handle command-line arguments
def main():
    parser = argparse.ArgumentParser(description="Test sending or receiving CAN frames.")
    parser.add_argument("--mode", choices=["send", "receive"], required=True, help="Mode to run: send or receive")
    args = parser.parse_args()

    # Initialize SIL-Kit
    registry_uri = b"silkit://localhost:8500"
    participant_name = f"Test_Participant_{int(time.time())}".encode('utf-8')  # Unique participant name
    can_channel_name = b"CAN1"
    can_network_name = b"CAN1"  # Network name should match channel name

    print(f"Starting {args.mode} mode with participant name: {participant_name}")
    print(f"Using channel: {can_channel_name}, network: {can_network_name}")

    # Create participant configuration
    participant_config = c_void_p()
    result = silkit.SilKit_ParticipantConfiguration_FromString(byref(participant_config), b"{}")
    if result != 0:
        print(f"Failed to create participant configuration: {result}")
        return

    # Create participant
    participant = c_void_p()
    result = silkit.SilKit_Participant_Create(
        byref(participant),
        participant_config,
        participant_name,
        registry_uri
    )
    if result != 0:
        print(f"Failed to create participant: {result}")
        return
    print("Participant created successfully")

    # Create lifecycle configuration
    lifecycle_config = SilKit_LifecycleConfiguration()
    SilKit_Struct_Init(SilKit_LifecycleConfiguration, lifecycle_config)
    lifecycle_config.operationMode = SILKIT_OPERATIONMODE_COORDINATED  # Use coordinated mode like in the C++ example

    # Create lifecycle service
    lifecycle_service = c_void_p()
    result = silkit.SilKit_LifecycleService_Create(
        byref(lifecycle_service),
        participant,
        byref(lifecycle_config)
    )
    if result != 0:
        print(f"Failed to create lifecycle service: {result}")
        return
    print("Lifecycle service created successfully")

    # Create CAN controller
    can_controller = c_void_p()
    result = silkit.SilKit_CanController_Create(
        byref(can_controller),
        participant,
        can_channel_name,
        can_network_name
    )
    if result != 0:
        print(f"Failed to create CAN controller: {result}")
        return
    print("CAN controller created successfully")

    # Set CAN baud rate (500 kbps)
    result = silkit.SilKit_CanController_SetBaudRate(can_controller, 500000, 0, 0)
    if result != 0:
        print(f"Failed to set CAN baud rate: {result}")
        return
    print("CAN baud rate set successfully")

    # Start CAN controller
    result = silkit.SilKit_CanController_Start(can_controller)
    if result != 0:
        print(f"Failed to start CAN controller: {result}")
        return
    print("CAN controller started successfully")

    if args.mode == "send":
        print("Starting sender mode...")
        test_send_can_frame(can_controller)
    elif args.mode == "receive":
        print("Starting receiver mode...")
        receive_can_frame(can_controller)

def test_send_can_frame(can_controller):
    try:
        while True:
            # Create and initialize CAN frame
            frame = CanFrame()
            SilKit_Struct_Init(CanFrame, frame)

            # Set CAN frame fields
            frame.id = 0x123  # Example CAN ID
            frame.flags = SILKIT_CANFRAMEFLAG_IDE  # Use extended ID format
            frame.dlc = 8  # Data length code

            # Pack data into CAN message
            data = bytearray(8)
            data[0] = 1  # Example data
            data[1] = 22  # Example data
            data_buffer = (c_uint8 * 8)(*data)
            frame.data.data = cast(data_buffer, POINTER(c_uint8))
            frame.data.size = 8

            # Debugging: Print frame and data buffer contents
            print(f"CAN Frame ID: {frame.id}")
            print(f"CAN Frame Flags: {frame.flags}")
            print(f"CAN Frame DLC: {frame.dlc}")
            print(f"CAN Frame Data: {[data_buffer[i] for i in range(frame.data.size)]}")

            # Send frame
            print("Sending CAN frame...")
            result = silkit.SilKit_CanController_SendFrame(can_controller, byref(frame), None)
            if result != 0:
                print(f"Failed to send CAN frame: {result}")

            time.sleep(2)  # Wait for 2 seconds
    except KeyboardInterrupt:
        print("Stopped sending CAN frames.")

if __name__ == '__main__':
    main() 