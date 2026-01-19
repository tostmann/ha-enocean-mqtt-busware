"""
Connection Handler for EnOcean Gateway
Manages communication with EnOcean via Serial Port or TCP Socket
Robustness improvements: TCP KeepAlive, App-Level Ping, Reconnect Logic
"""
import asyncio
import logging
import serial
import socket
import time
import urllib.parse
import struct
from typing import Optional, Callable
from .esp3_protocol import ESP3Packet

logger = logging.getLogger(__name__)


class SerialHandler:
    """Handle communication with EnOcean gateway (Serial or TCP)"""
    
    def __init__(self, connection_string: str, baudrate: int = 57600):
        """
        Initialize connection handler
        
        Args:
            connection_string: Path (e.g., /dev/ttyUSB0) or URL (e.g., tcp://192.168.1.10:2000)
            baudrate: Baud rate (default: 57600 for EnOcean, ignored for TCP)
        """
        self.connection_string = connection_string
        self.baudrate = baudrate
        self.serial = None
        self.socket = None
        self.running = False
        self.base_id = None
        self.version_info = None
        self.last_data_received = 0.0
        
        # Determine connection type
        if connection_string.lower().startswith('tcp://'):
            self.mode = 'tcp'
            parsed = urllib.parse.urlparse(connection_string)
            self.host = parsed.hostname
            self.port = parsed.port
            if not self.port:
                raise ValueError("Port missing in TCP connection string")
        else:
            self.mode = 'serial'
            self.port_path = connection_string
        
    def open(self) -> bool:
        """Open connection (Serial or TCP)"""
        try:
            if self.mode == 'serial':
                self.serial = serial.Serial(
                    port=self.port_path,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.5  # Short timeout to yield control frequently
                )
                logger.info(f"Opened serial port {self.port_path} at {self.baudrate} baud")
                self.flush_input()
            
            elif self.mode == 'tcp':
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                
                # Enable TCP KeepAlive on OS level
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                
                # Linux specific keepalive settings (try/except for compatibility)
                try:
                    # Send keepalive probe after 60s idle
                    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
                    # Send probe every 10s
                    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                    # Fail after 3 failed probes
                    self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                except (AttributeError, OSError):
                    pass # Not supported on all platforms, ignore

                self.socket.settimeout(5.0) # Connection timeout
                self.socket.connect((self.host, self.port))
                self.socket.settimeout(0.5) # Short Read timeout
                logger.info(f"Connected to TCP transceiver at {self.host}:{self.port}")
                
                self.flush_input()
            
            self.last_data_received = time.time()    
            return True
        except Exception as e:
            logger.error(f"Failed to open connection {self.connection_string}: {e}")
            return False
    
    def close(self):
        """Close connection"""
        if self.mode == 'serial' and self.serial and self.serial.is_open:
            try:
                self.serial.close()
            except Exception:
                pass
            logger.info(f"Closed serial port {self.port_path}")
        elif self.mode == 'tcp' and self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
            logger.info(f"Closed TCP connection to {self.host}:{self.port}")

    def flush_input(self):
        """Flush input buffer to remove stale data"""
        logger.debug("Flushing input buffer...")
        try:
            if self.mode == 'serial' and self.serial:
                self.serial.reset_input_buffer()
            elif self.mode == 'tcp' and self.socket:
                self.socket.setblocking(0)
                while True:
                    try:
                        data = self.socket.recv(4096)
                        if not data: break
                    except BlockingIOError:
                        break
                    except Exception:
                        break
                self.socket.setblocking(1)
                self.socket.settimeout(0.5)
        except Exception as e:
            logger.warning(f"Error flushing input: {e}")
    
    def is_open(self) -> bool:
        """Check if connection is open"""
        if self.mode == 'serial':
            return self.serial is not None and self.serial.is_open
        elif self.mode == 'tcp':
            return self.socket is not None
        return False
        
    def _read_bytes_sync(self, count: int) -> bytes:
        """Helper to read bytes synchronously from the active interface"""
        if self.mode == 'serial':
            return self.serial.read(count)
        elif self.mode == 'tcp':
            data = b''
            try:
                while len(data) < count:
                    chunk = self.socket.recv(count - len(data))
                    if not chunk: # EOF
                        logger.warning("TCP connection closed by remote host (EOF)")
                        self.close()
                        break
                    data += chunk
                return data
            except socket.timeout:
                return data 
            except Exception as e:
                logger.error(f"Socket read error: {e}")
                self.close()
                return b''
        return b''

    def _write_bytes_sync(self, data: bytes):
        """Helper to write bytes synchronously"""
        if self.mode == 'serial':
            self.serial.write(data)
        elif self.mode == 'tcp':
            self.socket.sendall(data)

    async def read_packet(self) -> Optional[ESP3Packet]:
        """
        Try to read one ESP3 packet.
        Returns None immediately if no full packet is available or on timeout.
        Does NOT block indefinitely waiting for sync.
        """
        if not self.is_open():
            return None
        
        try:
            # 1. Try to read Sync Byte (0x55)
            # This uses the short timeout (0.5s) set in open()
            byte = await asyncio.get_event_loop().run_in_executor(
                None, self._read_bytes_sync, 1
            )
            
            if not byte:
                # Timeout / No data available
                return None
            
            # Data received! Update timestamp
            self.last_data_received = time.time()
            
            if byte[0] != ESP3Packet.SYNC_BYTE:
                # Received garbage, ignore and return to let loop handle flow
                # (In a noisy environment, we might want to loop here, but 
                # returning allows the keep-alive logic to run)
                # logger.debug(f"Skip non-sync byte: 0x{byte[0]:02x}")
                return None
            
            logger.debug("Found sync byte 0x55, reading header...")

            # 2. Read Header (4 bytes)
            header = await asyncio.get_event_loop().run_in_executor(
                None, self._read_bytes_sync, 4
            )
            if len(header) != 4:
                logger.warning("Incomplete header received")
                return None
            
            data_length = int.from_bytes(header[0:2], 'big')
            optional_length = header[2]
            
            # 3. Read Header CRC (1 byte)
            header_crc = await asyncio.get_event_loop().run_in_executor(
                None, self._read_bytes_sync, 1
            )
            if len(header_crc) != 1:
                return None
            
            # 4. Read Data (Data + Opt + CRC)
            total_data_length = data_length + optional_length + 1
            data_block = await asyncio.get_event_loop().run_in_executor(
                None, self._read_bytes_sync, total_data_length
            )
            if len(data_block) != total_data_length:
                logger.warning(f"Incomplete data block: {len(data_block)}/{total_data_length}")
                return None
            
            # Reconstruct and parse
            raw_packet = bytes([ESP3Packet.SYNC_BYTE]) + header + header_crc + data_block
            packet = ESP3Packet(raw_packet)
            logger.debug(f"Received packet: {packet}")
            return packet
            
        except Exception as e:
            logger.error(f"Error reading packet: {e}")
            if self.mode == 'tcp':
                self.close()
            return None
    
    async def write_packet(self, packet: ESP3Packet) -> bool:
        """Write ESP3 packet to connection"""
        if not self.is_open():
            return False
        
        try:
            raw_data = packet.build()
            await asyncio.get_event_loop().run_in_executor(
                None, self._write_bytes_sync, raw_data
            )
            logger.debug(f"Sent packet: {packet}")
            return True
        except Exception as e:
            logger.error(f"Error writing packet: {e}")
            if self.mode == 'tcp':
                self.close()
            return False

    async def send_ping(self) -> bool:
        """Send a 'Read Version' command as Ping/KeepAlive"""
        logger.info("⏳ Connection idle > 30s. Sending KeepAlive Ping...")
        try:
            # We use Read Version (Common Command 0x03) as Ping
            ping_packet = ESP3Packet.create_read_version()
            return await self.write_packet(ping_packet)
        except Exception as e:
            logger.error(f"Failed to send Ping: {e}")
            return False

    async def send_command_and_wait_response(self, command_packet: ESP3Packet, timeout: float = 2.0) -> Optional[ESP3Packet]:
        """Send command and wait for response"""
        if not await self.write_packet(command_packet):
            return None
        
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            # We call read_packet directly. 
            # Note: This might steal a packet from the main loop if running concurrently,
            # but usually this method is called during initialization or when idle.
            packet = await self.read_packet()
            if packet and packet.packet_type == ESP3Packet.PACKET_TYPE_RESPONSE:
                return packet
            await asyncio.sleep(0.01)
        return None

    # ... get_base_id and get_version_info remain mostly the same ...
    async def get_base_id(self) -> Optional[str]:
        if self.base_id: return self.base_id
        command = ESP3Packet.create_read_base_id()
        response = await self.send_command_and_wait_response(command)
        if response and len(response.data) >= 5 and response.data[0] == 0:
            self.base_id = response.data[1:5].hex()
            return self.base_id
        return None
    
    async def get_version_info(self) -> Optional[dict]:
        if self.version_info: return self.version_info
        command = ESP3Packet.create_read_version()
        response = await self.send_command_and_wait_response(command)
        if response and len(response.data) >= 33 and response.data[0] == 0:
            self.version_info = {
                'app_version': '.'.join(str(b) for b in response.data[1:5]),
                'chip_id': response.data[9:13].hex()
            }
            return self.version_info
        return None

    async def start_reading(self, callback: Callable[[ESP3Packet], None]):
        """
        Start continuous reading with KeepAlive logic
        """
        self.running = True
        logger.info(f"Started reading from {self.mode} interface")
        logger.info("=" * 80)
        logger.info("🎧 LISTENING FOR ENOCEAN TELEGRAMS (KeepAlive Enabled)")
        logger.info("=" * 80)
        
        # Settings
        PING_INTERVAL = 30.0  # Send ping if idle for 30s
        PING_TIMEOUT = 10.0   # Wait 10s for response (implied by loop)
        
        self.last_data_received = time.time()
        
        while self.running:
            try:
                # 1. Check Connection
                if self.mode == 'tcp' and not self.is_open():
                    logger.warning(f"TCP connection lost. Reconnecting to {self.host}:{self.port} in 5s...")
                    await asyncio.sleep(5)
                    if self.open():
                        logger.info("TCP connection re-established")
                        self.last_data_received = time.time() # Reset timer
                        
                        # --- NEW: Fetch info if missed at startup ---
                        if not self.base_id:
                            logger.info("Fetching Base ID after reconnect...")
                            await self.get_base_id()
                        if not self.version_info:
                            await self.get_version_info()
                        # --------------------------------------------
                    continue

                # 2. Try to read a packet
                packet = await self.read_packet()
                
                if packet:
                    # Packet received, processing
                    if packet.packet_type == ESP3Packet.PACKET_TYPE_RADIO_ERP1:
                        await callback(packet)
                    elif packet.packet_type == ESP3Packet.PACKET_TYPE_RESPONSE:
                        logger.debug("Received Ping/Response")
                    
                    continue # Valid packet reset the flow
                
                # 3. No packet received (Idle). Check Timers.
                now = time.time()
                time_since_data = now - self.last_data_received
                
                if time_since_data > (PING_INTERVAL + PING_TIMEOUT):
                     # We sent a ping (at 30s) and waited (until 40s) but still no data.
                     # Connection is dead.
                     logger.warning(f"❌ Connection dead! No data for {time_since_data:.1f}s (Ping failed). Closing...")
                     self.close()
                     continue

                if time_since_data > PING_INTERVAL:
                    # Idle for > 30s. Send a Ping if we haven't just done it
                    # (We use a simple modulo or flag logic to avoid spamming ping every loop cycle)
                    # Simple hack: send ping every 5s once we are in "idle" territory
                    if int(time_since_data) % 5 == 0: 
                        # Only send if we can write
                        if not await self.send_ping():
                            logger.warning("Failed to send Ping. Closing connection.")
                            self.close()
                
            except Exception as e:
                logger.error(f"Error in read loop: {e}")
                await asyncio.sleep(1)
    
    def stop_reading(self):
        self.running = False

    async def send_telegram(self, destination_id: str, rorg: int, data_bytes: bytes, status: int = 0x00) -> bool:
        if not self.base_id: await self.get_base_id()
        packet = ESP3Packet.create_radio_packet(self.base_id, destination_id, rorg, data_bytes, status)
        return await self.write_packet(packet)
    
    async def send_rps_command(self, destination_id: str, button_code: int, press_duration: float = 0.1) -> bool:
        if not self.base_id: await self.get_base_id()
        packet_press = ESP3Packet.create_rps_packet(self.base_id, destination_id, button_code, pressed=True)
        if await self.write_packet(packet_press):
            await asyncio.sleep(press_duration)
            packet_release = ESP3Packet.create_rps_packet(self.base_id, destination_id, button_code, pressed=False)
            return await self.write_packet(packet_release)
        return False
