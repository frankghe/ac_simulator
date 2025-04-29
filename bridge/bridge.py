#!/usr/bin/env python3
import asyncio
import struct
import json
import ctypes
from ctypes import c_void_p, c_char_p, c_uint32, c_uint8, c_uint64, POINTER, Structure, c_int, c_int8, byref, cast, memset, sizeof

# Load SIL-Kit shared library
silkit = ctypes.CDLL("/home/frank/projects/sil-kit/build/Release/libSilKit.so")

# Define necessary structures and types in the correct order
class SilKit_StructHeader(Structure):
    _fields_ = [
        ("version", c_uint64),
        ("_reserved", c_uint64 * 3)
    ]

# Define ByteVector structure for data handling
class SilKit_ByteVector(Structure):
    _fields_ = [
        ("data", POINTER(c_uint8)),
        ("size", c_uint64)
    ]

class CanFrame(Structure):
    _fields_ = [
        ("structHeader", SilKit_StructHeader),
        ("id", c_uint32),
        ("flags", c_uint32),
        ("dlc", c_uint8),
        ("sdt", c_uint8),
        ("vcid", c_uint8),
        ("af", c_uint32),
        ("data", SilKit_ByteVector)
    ]

# Define the SilKit_CanFrameEvent structure
class SilKit_CanFrameEvent(Structure):
    _fields_ = [
        ("structHeader", SilKit_StructHeader),
        ("timestamp", c_uint64),  # SilKit_NanosecondsTime
        ("frame", POINTER(CanFrame)),  # Pointer to the CAN frame
        ("direction", c_int),  # SilKit_Direction
        ("userContext", c_void_p)  # Optional user context
    ]

class SilKit_LifecycleConfiguration(Structure):
    _fields_ = [
        ("structHeader", SilKit_StructHeader),
        ("operationMode", c_int8)
    ]

class SilKitBridge:
    def __init__(self):
        # Initialize SIL-Kit
        self.registry_uri = b"silkit://localhost:8500"
        self.participant_name = b"CAN_Bridge"
        self.can_channel_name = b"CAN1"
        
        print(f"Initializing SilKit bridge with participant name: {self.participant_name.decode()}")
        
        # Create participant configuration
        self.participant_config = c_void_p()
        config_str = b"{}"  # Empty JSON configuration
        err = silkit.SilKit_ParticipantConfiguration_FromString(
            ctypes.byref(self.participant_config),
            config_str
        )
        if err != 0:
            raise RuntimeError(f"Failed to create participant configuration: {err}")
        print("Participant configuration created")
        
        # Create participant
        self.participant = c_void_p()
        err = silkit.SilKit_Participant_Create(
            ctypes.byref(self.participant),
            self.participant_config,
            self.participant_name,
            self.registry_uri
        )
        if err != 0:
            raise RuntimeError(f"Failed to create participant: {err}")
        print("Participant created")
        
        # Create lifecycle configuration - create first but start after controller
        lifecycle_config = SilKit_LifecycleConfiguration()
        memset(byref(lifecycle_config), 0, sizeof(lifecycle_config))
        lifecycle_config.structHeader.version = ((83 << 56) | (75 << 48) | (7 << 40) | (2 << 32) | (1 << 24))
        lifecycle_config.operationMode = 20  # SilKit_OperationMode_Autonomous
        
        # Create lifecycle service
        self.lifecycle_service = c_void_p()
        result = silkit.SilKit_LifecycleService_Create(
            ctypes.byref(self.lifecycle_service),
            self.participant,
            ctypes.byref(lifecycle_config)
        )
        if result != 0:
            raise RuntimeError(f"Failed to create lifecycle service: {result}")
        print("Lifecycle service created (but not started yet)")
        
        # Create CAN controller
        self.can_controller = c_void_p()
        err = silkit.SilKit_CanController_Create(
            ctypes.byref(self.can_controller),
            self.participant,
            b"CanController1",  # Controller name
            self.can_channel_name
        )
        if err != 0:
            raise RuntimeError(f"Failed to create CAN controller: {err}")
        print(f"CAN controller created on network: {self.can_channel_name.decode()}")
        
        # Set up CAN message handler callback for receiving
        @ctypes.CFUNCTYPE(None, c_void_p, c_void_p, POINTER(SilKit_CanFrameEvent))
        def can_handler(context, controller, frame_event):
            print("DEBUG: SilKit frame handler called")
            if frame_event and frame_event.contents.frame:
                print(f"DEBUG: SilKit frame received - ID: 0x{frame_event.contents.frame.contents.id:x}")
                self.handle_can_message(controller, frame_event.contents.frame.contents)
            else:
                print("DEBUG: SilKit frame handler received NULL frame")
        self.can_handler = can_handler  # Keep reference to prevent garbage collection
        
        # Define direction mask for receiving frames - must match the can_receive_test
        SILKIT_DIRECTION_RX = 2  # SilKit_Direction_Receive=2
        
        # Add frame handler
        self.handler_id = c_uint32()
        err = silkit.SilKit_CanController_AddFrameHandler(
            self.can_controller,
            None,  # context
            self.can_handler,
            SILKIT_DIRECTION_RX,
            ctypes.byref(self.handler_id)
        )
        if err != 0:
            raise RuntimeError(f"Failed to add CAN handler: {err}")
        print("CAN frame handler registered")
        
        # Start CAN controller BEFORE starting lifecycle (like in can_send_test)
        print("Starting CAN controller...")
        err = silkit.SilKit_CanController_Start(self.can_controller)
        if err != 0:
            raise RuntimeError(f"Failed to start CAN controller: {err}")
        print("CAN controller started")
        
        # Now start the lifecycle service (after controller is started)
        print("Starting lifecycle service...")
        result = silkit.SilKit_LifecycleService_StartLifecycle(self.lifecycle_service)
        if result != 0:
            print(f"Warning: Failed to start lifecycle: {result}")
        else:
            print("Lifecycle service started successfully")
        
        # Create a test frame to verify CAN sending works
        print("Sending test CAN frame to verify connectivity...")
        self.send_test_frame()
        
        # TCP clients (Zephyr applications)
        self.clients = set()
        print("SilKit bridge initialization complete")

    async def start_servers(self):
        # Start server for ac_control on 192.0.2.10:5000
        server1 = await asyncio.start_server(
            self.handle_client, '127.0.0.1', 5000
        )
        print(f"Bridge server running for ac_control on 127.0.0.1:5000")
        
        # Start server for thermal on 192.0.2.20:5000
        server2 = await asyncio.start_server(
            self.handle_client, '192.0.2.20', 5000
        )
        print(f"Bridge server running for HVAC on 192.0.2.20:5000")
        
        # Run both servers concurrently
        await asyncio.gather(
            server1.serve_forever(),
            server2.serve_forever()
        )
        
    async def handle_client(self, reader, writer):
        addr = writer.get_extra_info('peername')
        print(f"New connection from {addr}")
        self.clients.add(writer)
        
        # Check if this is the thermal client (from 192.0.2.x)
        is_thermal = addr[0].startswith('192.0.2.')
        
        # Store references to data buffers to prevent garbage collection
        self.data_buffers = []
        
        try:
            while True:
                if is_thermal:
                    # Raw binary protocol for thermal
                    # Read header (5 bytes: 4 for ID, 1 for length)
                    header = await reader.read(5)
                    if not header or len(header) < 5:
                        print(f"Incomplete header received from {addr}, closing connection")
                        break
                    
                    # Extract CAN ID (first 4 bytes)
                    can_id = (header[0] << 24) | (header[1] << 16) | (header[2] << 8) | header[3]
                    
                    # Extract data length (next byte)
                    data_len = header[4]
                    
                    # Read data bytes
                    data_bytes = await reader.read(data_len)
                    if not data_bytes or len(data_bytes) < data_len:
                        print(f"Incomplete data received from {addr}, closing connection")
                        break
                    
                    print(f"Received raw CAN frame from thermal - ID: 0x{can_id:x}, Length: {data_len}")
                    
                    # Convert to list of integers for SilKit
                    data_array = list(data_bytes)
                    
                    # Create and send SilKit CAN frame directly without JSON conversion
                    frame = CanFrame()
                    memset(byref(frame), 0, sizeof(frame))
                    
                    # Initialize the struct header
                    frame.structHeader.version = ((83 << 56) | (75 << 48) | (1 << 40) | (1 << 32) | (1 << 24))
                    
                    # Set frame properties
                    frame.id = can_id
                    frame.flags = 0
                    frame.dlc = data_len
                    
                    # Create a C-compatible buffer for the data
                    data_buffer = (c_uint8 * data_len)(*data_array)
                    self.data_buffers.append(data_buffer)
                    if len(self.data_buffers) > 10:
                        self.data_buffers.pop(0)
                    
                    # Set data pointer and size
                    frame.data.data = cast(data_buffer, POINTER(c_uint8))
                    frame.data.size = data_len
                    
                    # Send the frame
                    print(f"Forwarding CAN frame to SilKit - ID: 0x{can_id:x}, Length: {data_len}")
                    err = silkit.SilKit_CanController_SendFrame(
                        self.can_controller,
                        byref(frame),
                        None
                    )
                    
                    if err != 0:
                        print(f"Failed to send CAN frame to SilKit: {err}")
                    else:
                        print(f"Successfully sent CAN frame to SilKit - ID: 0x{can_id:x}, Length: {data_len}")
                else:
                    # JSON protocol for other clients
                    # Read message length (4 bytes)
                    length_bytes = await reader.read(4)
                    if not length_bytes:
                        break
                        
                    msg_length = struct.unpack('!I', length_bytes)[0]
                    
                    # Read message
                    msg_bytes = await reader.read(msg_length)
                    if not msg_bytes:
                        break
                        
                    # Parse message
                    msg = json.loads(msg_bytes.decode())
                    
                    # Handle message based on type
                    if msg['type'] == 'can':
                        print(f"DEBUG: Received JSON CAN message from TCP client: ID=0x{msg['id']:x}, Data={msg.get('data', [])}")
                        
                        # Create and initialize CAN frame - approach similar to can_send_test.c
                        frame = CanFrame()
                        memset(byref(frame), 0, sizeof(frame)) # Zero out the entire structure first
                        
                        # Initialize the struct header with same version header as can_send_test
                        frame.structHeader.version = ((83 << 56) | (75 << 48) | (1 << 40) | (1 << 32) | (1 << 24))
                        
                        # Set basic frame properties
                        frame.id = msg['id']
                        frame.flags = 0
                        frame.sdt = 0
                        frame.vcid = 0
                        frame.af = 0

                        # Prepare data for CAN frame - directly use the bytes like in can_send_test
                        original_data = bytes(msg.get('data', []))
                        data_len = len(original_data)
                        
                        print(f"DEBUG: Converting to SilKit CAN frame: ID=0x{frame.id:x}, Raw Data={list(original_data)}")

                        # Set DLC to match data length (up to 8 bytes) like in can_send_test
                        # can_send_test simply uses actual data length for DLC
                        if data_len <= 8:
                            frame.dlc = data_len
                        else:
                            # For CAN FD frames that exceed standard CAN limits
                            if data_len <= 12:
                                frame.dlc = 9
                            elif data_len <= 16:
                                frame.dlc = 10
                            elif data_len <= 20:
                                frame.dlc = 11
                            elif data_len <= 24:
                                frame.dlc = 12
                            elif data_len <= 32:
                                frame.dlc = 13
                            elif data_len <= 48:
                                frame.dlc = 14
                            else:  # data_len <= 64
                                frame.dlc = 15
                                if data_len > 64:
                                    print(f"Warning: CAN data exceeds 64 bytes, truncating to 64")
                                    original_data = original_data[:64]
                                    data_len = 64

                        # Create a C-compatible buffer for the data - use static allocation approach
                        data_buffer = (c_uint8 * data_len)(*original_data)
                        
                        # Store the buffer to prevent garbage collection - critical for Python
                        self.data_buffers.append(data_buffer)
                        if len(self.data_buffers) > 10:
                            self.data_buffers.pop(0)  # Keep only recent buffers to avoid memory growth
                        
                        # Set data pointer and size, using proper casting like can_send_test does
                        frame.data.data = cast(data_buffer, POINTER(c_uint8))
                        frame.data.size = data_len

                        # Send the frame with proper parameters - exactly like can_send_test
                        print(f"Sending CAN frame with ID: 0x{frame.id:x}, size: {data_len}")
                        err = silkit.SilKit_CanController_SendFrame(
                            self.can_controller,
                            byref(frame),  # Use byref instead of ctypes.byref for consistency
                            None           # userContext
                        )
                        
                        if err != 0:
                            print(f"Failed to send CAN frame: {err}")
                        else:
                            print(f"Successfully sent CAN frame with ID: 0x{frame.id:x}, length: {data_len}")
                        
        except Exception as e:
            print(f"Error handling client {addr}: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            self.clients.remove(writer)
            print(f"Connection closed from {addr}")
            
    def handle_can_message(self, controller, frame):
        try:
            # Get actual data size
            data_size = min(self.get_dlc_size(frame.dlc), frame.data.size) if frame.data.data else 0
            
            print(f"DEBUG: SilKit->TCP - Handling CAN frame with ID: 0x{frame.id:x}, DLC: {frame.dlc}, Size: {data_size}")
            
            # Extract data bytes
            data_array = []
            if frame.data.data and data_size > 0:
                for i in range(data_size):
                    data_array.append(frame.data.data[i])
                
                print(f"DEBUG: SilKit->TCP - Frame data: {data_array}")
            
            # Instead of JSON, create a simple binary format:
            # [4 bytes for ID][1 byte for length][N bytes of data]
            raw_frame = bytearray()
            
            # Add CAN ID (4 bytes, network byte order)
            raw_frame.extend(struct.pack('!I', frame.id))
            
            # Add data length (1 byte)
            raw_frame.extend(struct.pack('!B', data_size))
            
            # Add actual data
            for byte in data_array:
                raw_frame.extend(struct.pack('!B', byte))
                
            # Send to all clients
            client_count = 0
            for writer in self.clients:
                try:
                    # Check if this is the thermal client (connected to 192.0.2.*)
                    peer = writer.get_extra_info('peername')
                    is_thermal = peer and peer[0].startswith('192.0.2.')
                    
                    if is_thermal:
                        print(f"DEBUG: Sending raw CAN frame to thermal client at {peer}")
                        print(f"DEBUG: Raw frame: {' '.join(f'{b:02x}' for b in raw_frame)}")
                    
                    # Send raw frame without any length prefix
                    writer.write(raw_frame)
                    client_count += 1
                except Exception as e:
                    print(f"Error sending to client: {e}")
            
            print(f"DEBUG: SilKit->TCP - Sent raw CAN frame to {client_count} clients")
        except Exception as e:
            print(f"Error processing CAN message: {e}")
            
    def get_dlc_size(self, dlc):
        """Convert DLC to actual data size for CAN FD"""
        if dlc <= 8:
            return dlc
        elif dlc == 9:
            return 12
        elif dlc == 10:
            return 16
        elif dlc == 11:
            return 20
        elif dlc == 12:
            return 24
        elif dlc == 13:
            return 32
        elif dlc == 14:
            return 48
        elif dlc == 15:
            return 64
        return 0

    def __del__(self):
        # Cleanup SIL-Kit resources
        if hasattr(self, 'lifecycle_service'):
            silkit.SilKit_LifecycleService_Stop(self.lifecycle_service)
            silkit.SilKit_LifecycleService_Destroy(self.lifecycle_service)
        if hasattr(self, 'can_controller') and hasattr(self, 'handler_id'):
            silkit.SilKit_CanController_RemoveFrameHandler(self.can_controller, self.handler_id)
        if hasattr(self, 'can_controller'):
            silkit.SilKit_CanController_Destroy(self.can_controller)
        if hasattr(self, 'participant'):
            silkit.SilKit_Participant_Destroy(self.participant)
        if hasattr(self, 'participant_config'):
            silkit.SilKit_ParticipantConfiguration_Destroy(self.participant_config)
                
    def send_test_frame(self):
        # Create a frame struct
        frame = CanFrame()
        memset(byref(frame), 0, sizeof(frame))
        
        # Initialize like can_send_test
        frame.structHeader.version = ((83 << 56) | (75 << 48) | (1 << 40) | (1 << 32) | (1 << 24))
        
        # Set simple test values
        frame.id = 0x123
        frame.flags = 0
        frame.dlc = 8
        
        # Create data like in can_send_test
        test_data = (c_uint8 * 8)(1, 2, 3, 4, 5, 6, 7, 8)
        self.test_buffer = test_data  # Keep reference to prevent garbage collection
        
        # Set data in frame
        frame.data.data = cast(test_data, POINTER(c_uint8))
        frame.data.size = 8
        
        # Send the frame
        print("Sending test frame with ID: 0x123")
        err = silkit.SilKit_CanController_SendFrame(
            self.can_controller, 
            byref(frame), 
            None
        )
        
        if err != 0:
            print(f"Error sending test frame: {err}")
        else:
            print("Test frame sent successfully")

async def main():
    bridge = SilKitBridge()
    await bridge.start_servers()  # No need for parameters as they're hardcoded now
    
if __name__ == '__main__':
    asyncio.run(main()) 