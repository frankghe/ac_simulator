import socket
import time
import struct
import argparse

# --- Configuration ---
# CAN IDs from zephyr-apps/common/net/can_ids.h
# Command to turn AC ON/OFF (Data[0]: 0=OFF, 1=ON)
HVAC_POWER_STATUS_ID = 0xAC2
# Status message from HVAC system (thermal model) indicating AC state (Data[2]: 0=OFF, 1=ON)
HVAC_STATUS_ID_TO_CHECK = 0x125 # ID sent periodically by hvac app
AC_STATE_BYTE_INDEX = 2 # Index of AC ON/OFF state in HVAC_STATUS_ID message

DEFAULT_HOST = "192.0.2.3"
DEFAULT_PORT = 8080  # Must match CONFIG_TELEMATICS_PORT in prj.conf
RECEIVE_TIMEOUT = 5.0  # Seconds to wait for a specific status message
STATUS_CHECK_INTERVAL = 0.5 # Seconds between checking status

def encode_can_message(can_id, data):
    """Encodes a CAN message for transmission over TCP."""
    dlc = len(data)
    if dlc > 8:
        raise ValueError("CAN data length cannot exceed 8 bytes")
    # Pack CAN ID (4 bytes, big-endian), DLC (1 byte)
    header = struct.pack('>IB', can_id, dlc)
    return header + bytes(data)

def decode_can_message(tcp_data):
    """Decodes a CAN message received over TCP.
    Returns (can_id, dlc, data_payload, remaining_tcp_data).
    If a full message cannot be decoded, can_id will be None, 
    and remaining_tcp_data will be the original tcp_data passed in.
    """
    # Minimum length for header (ID 4 bytes + DLC 1 byte)
    if len(tcp_data) < 5:
        return None, None, None, tcp_data
    
    can_id, dlc = struct.unpack('>IB', tcp_data[:5])
    
    # Expected length of the CAN message payload based on DLC
    expected_payload_len = dlc # dlc itself is the count of data bytes
    # Total expected length for this single CAN frame in the tcp_data
    expected_frame_len = 5 + expected_payload_len

    if len(tcp_data) < expected_frame_len:
        # Not enough data for the complete frame (header + payload)
        return None, None, None, tcp_data

    # If we have enough data, extract the payload and the remainder of the tcp_data
    data_payload = tcp_data[5:expected_frame_len]
    remaining_tcp_data = tcp_data[expected_frame_len:]
    return can_id, dlc, data_payload, remaining_tcp_data

def send_ac_command(sock, state):
    """Sends an AC power command (ON/OFF) via the telematics gateway."""
    ac_state = 1 if state else 0
    # Assuming data format for HVAC_POWER_STATUS_ID is just [state]
    data = [ac_state]
    message = encode_can_message(HVAC_POWER_STATUS_ID, data)
    print(f"Sending AC {'ON' if state else 'OFF'} command (ID: 0x{HVAC_POWER_STATUS_ID:X}, Data: {data})")
    try:
        sock.sendall(message)
    except socket.error as e:
        print(f"Error sending command: {e}")
        return False
    return True

def check_hvac_status(sock, expected_ac_state, timeout=RECEIVE_TIMEOUT):
    """Checks for HVAC status message and verifies the AC state.
    Continuously checks for messages until the expected state is found or timeout occurs.
    """
    start_time = time.time()
    buffer = b'' # Holds data received from socket, potentially multiple/partial messages
    last_seen_incorrect_state = None

    print(f"Waiting for HVAC Status (ID: 0x{HVAC_STATUS_ID_TO_CHECK:X}) with AC state = {expected_ac_state} for up to {timeout:.1f}s...")

    while time.time() - start_time < timeout:
        loop_iteration_start_time = time.time()
        try:
            # Set a short timeout for individual recv attempts
            # This allows the loop to be responsive and check the main timeout condition
            sock.settimeout(0.05) # 50ms timeout for this recv call
            chunk = sock.recv(128) # Attempt to read some data
            if not chunk:
                print("  Connection closed by server during status check.")
                return False # Connection lost
            buffer += chunk
        except socket.timeout:
            # This is an expected timeout for a single recv attempt if no new data arrived quickly.
            # The outer loop will continue until the main `timeout` is reached.
            pass 
        except socket.error as e:
            print(f"  Error receiving data: {e}")
            return False # Unrecoverable socket error

        # Process all complete CAN messages currently in the buffer
        while True: # Inner loop to consume all messages from the current buffer
            can_id, dlc, data_payload, remaining_buffer_after_decode = decode_can_message(buffer)
            
            if can_id is None: # Indicates a full message could not be decoded
                buffer = remaining_buffer_after_decode # Store the partial message back
                break # Exit inner loop, need more data from sock.recv()

            # A message was successfully decoded, update buffer for next inner loop iteration
            buffer = remaining_buffer_after_decode 

            print(f"  Received Raw - ID: 0x{can_id:X}, DLC: {dlc}, Data: {list(data_payload)}")

            if can_id == HVAC_STATUS_ID_TO_CHECK:
                if dlc > AC_STATE_BYTE_INDEX:
                    actual_ac_state = data_payload[AC_STATE_BYTE_INDEX]
                    print(f"  HVAC Status (0x{can_id:X}) found. Actual AC state: {actual_ac_state}. Expected: {expected_ac_state}.")
                    if actual_ac_state == expected_ac_state:
                        print("  Correct AC state confirmed.")
                        sock.settimeout(None) # Reset socket to blocking mode (or original state)
                        return True # SUCCESS!
                    else:
                        last_seen_incorrect_state = actual_ac_state
                        print(f"  Incorrect AC state ({actual_ac_state}) but continuing to listen.")
                else:
                    print(f"  HVAC Status (0x{can_id:X}) too short (DLC={dlc}) for AC state byte.")
            # else: # Optionally log other CAN IDs received if needed for debugging
            #     print(f"  Ignoring message ID 0x{can_id:X}.")
        
        # Small sleep to prevent outer loop from spinning too fast if recv keeps timing out
        # and buffer is empty. Ensures other OS tasks can run.
        elapsed_in_loop_iteration = time.time() - loop_iteration_start_time
        if elapsed_in_loop_iteration < 0.05: # If loop was faster than typical socket timeout
            time.sleep(0.05 - elapsed_in_loop_iteration) 

    sock.settimeout(None) # Reset socket to blocking mode (or original state) before exiting function
    if last_seen_incorrect_state is not None:
        print(f"Timeout: Expected HVAC status (ID 0x{HVAC_STATUS_ID_TO_CHECK:X}, state {expected_ac_state}) not received. Last incorrect state seen was {last_seen_incorrect_state}.")
    else:
        print(f"Timeout: Did not receive any matching HVAC status (ID 0x{HVAC_STATUS_ID_TO_CHECK:X}) within {timeout:.1f} seconds.")
    return False


def main(host, port):
    """Main test function."""
    print(f"Connecting to Telematics Gateway at {host}:{port}...")
    test_socket = None # Define socket variable outside try to use in finally
    try:
        # It's better to manage the socket explicitly if we are setting timeouts frequently
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.settimeout(5) # Connection timeout
        test_socket.connect((host, port))
        print("Connected.")
        test_socket.settimeout(None) # Set back to blocking for sendall, or specific for check_hvac_status

        # --- Test AC ON ---
        if not send_ac_command(test_socket, True):
                 return
        # time.sleep(STATUS_CHECK_INTERVAL) # Give ECU time to process - check_hvac_status now has its own polling
        if check_hvac_status(test_socket, 1, timeout=RECEIVE_TIMEOUT):
            print("--> AC ON Test: SUCCESS")
        else:
            print("--> AC ON Test: FAILED")
            return # Stop if first test fails

        print("-" * 20)
        # time.sleep(5) # Pause between tests - can be shorter if desired
        print("Pausing for 2 seconds before AC OFF test...")
        time.sleep(2) 

        # --- Test AC OFF ---
        if not send_ac_command(test_socket, False):
            return
        # time.sleep(STATUS_CHECK_INTERVAL) # Give ECU time to process - check_hvac_status now has its own polling
        if check_hvac_status(test_socket, 0, timeout=RECEIVE_TIMEOUT):
            print("--> AC OFF Test: SUCCESS")
        else:
            print("--> AC OFF Test: FAILED")

    except socket.timeout as e:
        print(f"Socket timeout: {e} (Host: {host}:{port})")
    except socket.error as e:
        print(f"Socket error: {e} (Host: {host}:{port})")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if test_socket:
            test_socket.close()
        print("Test finished.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Telematics Gateway and HVAC ECU via TCP.")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Telematics Gateway IP address (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Telematics Gateway TCP port (default: {DEFAULT_PORT})")
    args = parser.parse_args()

    main(args.host, args.port) 