#!/usr/bin/env python3
"""
Simple test script to send a single CAN frame with 2 bytes of data using SilKit.
This helps test flags and basic frame configurations.
"""
import ctypes
from ctypes import c_void_p, c_char_p, c_uint32, c_uint8, c_uint64, POINTER, Structure, c_int8
import time

# Load SIL-Kit shared library
silkit = ctypes.CDLL("/home/frank/projects/sil-kit/build/Release/libSilKit.so")

# Define necessary structures
class CanFrame(Structure):
    _fields_ = [
        ("id", c_uint32),
        ("flags", c_uint32),
        ("dlc", c_uint8),
        ("data", c_uint8 * 8)  # Using 8 bytes array for standard CAN
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

def main():
    # Initialize SIL-Kit
    registry_uri = b"silkit://localhost:8500"
    participant_name = b"CAN_Test_Sender"
    can_channel_name = b"CAN1"
    
    print("\n=== CAN Frame Test Sender ===")
    
    # Create participant configuration
    participant_config = c_void_p()
    config_str = b"{}"  # Empty JSON configuration
    err = silkit.SilKit_ParticipantConfiguration_FromString(
        ctypes.byref(participant_config),
        config_str
    )
    if err != 0:
        print(f"Error: Failed to create participant configuration: {err}")
        return
    print("Participant configuration created")
    
    # Create participant
    participant = c_void_p()
    err = silkit.SilKit_Participant_Create(
        ctypes.byref(participant),
        participant_config,
        participant_name,
        registry_uri
    )
    if err != 0:
        print(f"Error: Failed to create participant: {err}")
        silkit.SilKit_ParticipantConfiguration_Destroy(participant_config)
        return
    print("Participant created")
    
    # Create CAN controller
    can_controller = c_void_p()
    err = silkit.SilKit_CanController_Create(
        ctypes.byref(can_controller),
        participant,
        can_channel_name
    )
    if err != 0:
        print(f"Error: Failed to create CAN controller: {err}")
        silkit.SilKit_Participant_Destroy(participant)
        silkit.SilKit_ParticipantConfiguration_Destroy(participant_config)
        return
    print("CAN controller created")
    
    # Setup CAN controller - THIS IS NEW
    # Try to set up the controller for both Classic CAN and CAN FD
    # SilKit_CanController_Setup might not be the exact function name
    # You would need to check SilKit documentation
    try:
        if hasattr(silkit, 'SilKit_CanController_Start'):
            print("Calling SilKit_CanController_Start...")
            err = silkit.SilKit_CanController_Start(can_controller)
            if err != 0:
                print(f"Warning: SilKit_CanController_Start returned error: {err}")
    except Exception as e:
        print(f"Warning: Exception during CAN controller setup: {e}")
    
    # Create lifecycle configuration
    lifecycle_config = SilKit_LifecycleConfiguration()
    lifecycle_config.structHeader.version = ((83 << 56) | (75 << 48) | (7 << 40) | (2 << 32) | (1 << 24))  # SK_ID_MAKE(Participant, SilKit_LifecycleConfiguration)
    lifecycle_config.operationMode = 20  # SilKit_OperationMode_Autonomous
    
    # Create lifecycle service
    lifecycle_service = c_void_p()
    result = silkit.SilKit_LifecycleService_Create(
        ctypes.byref(lifecycle_service),
        participant,
        ctypes.byref(lifecycle_config)
    )
    if result != 0:
        print(f"Error: Failed to create lifecycle service: {result}")
        silkit.SilKit_CanController_Destroy(can_controller)
        silkit.SilKit_Participant_Destroy(participant)
        silkit.SilKit_ParticipantConfiguration_Destroy(participant_config)
        return
    print("Lifecycle service created")
    
    # Start lifecycle
    result = silkit.SilKit_LifecycleService_StartLifecycle(lifecycle_service)
    if result != 0:
        print(f"Error: Failed to start lifecycle: {result}")
        silkit.SilKit_LifecycleService_Destroy(lifecycle_service)
        silkit.SilKit_CanController_Destroy(can_controller)
        silkit.SilKit_Participant_Destroy(participant)
        silkit.SilKit_ParticipantConfiguration_Destroy(participant_config)
        return
    print("Lifecycle started")
    
    # Create and send CAN message with 2 bytes [10, 20]
    print("\n=== Sending CAN Frame Tests ===")
    
    # Try multiple flag combinations to see what works
    flag_values = [0, 1, 2, 4, 8, 16, 32, 64, 128]
    
    for flag_value in flag_values:
        # Create frame with current flag value
        frame = CanFrame()
        frame.id = 0x123  # A standard 11-bit CAN ID
        frame.flags = flag_value
        frame.dlc = 2  # 2 bytes
        
        # Prepare 2-byte data [10, 20]
        data_buffer = bytearray(8)  # 8-byte buffer (zero-initialized)
        data_buffer[0] = 10
        data_buffer[1] = 20
        
        # Assign to frame data
        frame.data = (c_uint8 * 8)(*data_buffer)
        
        print(f"\nTest with flags=0x{flag_value:x}, dlc=2, data=[10, 20]")
        err = silkit.SilKit_CanController_SendFrame(
            can_controller,
            ctypes.byref(frame)
        )
        print(f"Result: {'Success' if err == 0 else f'Error {err}'}")
        
        # Wait a short while to ensure message is processed
        time.sleep(0.2)
    
    # Cleanup
    print("\n=== Cleaning Up ===")
    silkit.SilKit_LifecycleService_Stop(lifecycle_service)
    silkit.SilKit_LifecycleService_Destroy(lifecycle_service)
    silkit.SilKit_CanController_Destroy(can_controller)
    silkit.SilKit_Participant_Destroy(participant)
    silkit.SilKit_ParticipantConfiguration_Destroy(participant_config)
    print("Cleanup complete")

if __name__ == "__main__":
    main() 