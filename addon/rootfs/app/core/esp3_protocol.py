"""
ESP3 Protocol Implementation for EnOcean
Handles packet parsing and creation according to ESP3 specification
"""
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class ESP3Packet:
    """ESP3 packet structure parser and builder"""
    
    SYNC_BYTE = 0x55
    
    # Packet types
    PACKET_TYPE_RADIO_ERP1 = 0x01
    PACKET_TYPE_RESPONSE = 0x02
    PACKET_TYPE_RADIO_SUB_TEL = 0x03
    PACKET_TYPE_EVENT = 0x04
    PACKET_TYPE_COMMON_COMMAND = 0x05
    PACKET_TYPE_SMART_ACK_COMMAND = 0x06
    PACKET_TYPE_REMOTE_MAN_COMMAND = 0x07
    PACKET_TYPE_RADIO_MESSAGE = 0x09
    PACKET_TYPE_RADIO_ERP2 = 0x0A
    
    # Common commands
    CO_WR_SLEEP = 0x01
    CO_WR_RESET = 0x02
    CO_RD_VERSION = 0x03
    CO_RD_SYS_LOG = 0x04
    CO_WR_SYS_LOG = 0x05
    CO_WR_BIST = 0x06
    CO_WR_IDBASE = 0x07
    CO_RD_IDBASE = 0x08
    CO_WR_REPEATER = 0x09
    CO_RD_REPEATER = 0x0A
    
    def __init__(self, raw_data: Optional[bytes] = None):
        """Initialize ESP3 packet from raw data or create empty packet"""
        if raw_data:
            self.parse(raw_data)
        else:
            self.sync = self.SYNC_BYTE
            self.data_length = 0
            self.optional_length = 0
            self.packet_type = 0
            self.data = b''
            self.optional_data = b''
    
    def parse(self, raw_data: bytes):
        """Parse raw ESP3 packet data"""
        if len(raw_data) < 6:
            raise ValueError("Packet too short")
        
        # Parse header
        self.sync = raw_data[0]
        if self.sync != self.SYNC_BYTE:
            raise ValueError(f"Invalid sync byte: {hex(self.sync)}")
        
        self.data_length = int.from_bytes(raw_data[1:3], 'big')
        self.optional_length = raw_data[3]
        self.packet_type = raw_data[4]
        header_crc = raw_data[5]
        
        # Validate header CRC
        calculated_header_crc = self.calculate_crc8(raw_data[1:5])
        if header_crc != calculated_header_crc:
            raise ValueError(f"Header CRC mismatch: {hex(header_crc)} != {hex(calculated_header_crc)}")
        
        # Extract data and optional data
        data_start = 6
        data_end = data_start + self.data_length
        optional_end = data_end + self.optional_length
        
        if len(raw_data) < optional_end + 1:
            raise ValueError("Packet data incomplete")
        
        self.data = raw_data[data_start:data_end]
        self.optional_data = raw_data[data_end:optional_end]
        data_crc = raw_data[optional_end]
        
        # Validate data CRC
        calculated_data_crc = self.calculate_crc8(self.data + self.optional_data)
        if data_crc != calculated_data_crc:
            raise ValueError(f"Data CRC mismatch: {hex(data_crc)} != {hex(calculated_data_crc)}")
        
        logger.debug(f"Parsed ESP3 packet: type={hex(self.packet_type)}, data_len={self.data_length}, opt_len={self.optional_length}")
    
    @staticmethod
    def calculate_crc8(data: bytes) -> int:
        """Calculate CRC8 checksum using EnOcean polynomial"""
        crc = 0
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x07
                else:
                    crc = crc << 1
                crc &= 0xFF
        return crc
    
    def build(self) -> bytes:
        """Build raw ESP3 packet from components"""
        # Build header
        header = bytes([
            (self.data_length >> 8) & 0xFF,
            self.data_length & 0xFF,
            self.optional_length,
            self.packet_type
        ])
        header_crc = self.calculate_crc8(header)
        
        # Build data CRC
        data_crc = self.calculate_crc8(self.data + self.optional_data)
        
        # Assemble packet
        packet = bytes([self.SYNC_BYTE]) + header + bytes([header_crc]) + self.data + self.optional_data + bytes([data_crc])
        return packet
    
    def get_sender_id(self) -> Optional[str]:
        """Extract sender ID from radio telegram"""
        if self.packet_type == self.PACKET_TYPE_RADIO_ERP1:
            if len(self.data) >= 5:
                # Sender ID is bytes 1-4 (after RORG)
                sender_bytes = self.data[1:5]
                return sender_bytes.hex()
        return None
    
    def get_rorg(self) -> Optional[int]:
        """Extract RORG (R-ORG) from radio telegram"""
        if self.packet_type == self.PACKET_TYPE_RADIO_ERP1:
            if len(self.data) >= 1:
                return self.data[0]
        return None
    
    def get_rssi(self) -> Optional[int]:
        """Extract RSSI from optional data"""
        if len(self.optional_data) >= 6:
            # RSSI is at byte 5 of optional data
            rssi_raw = self.optional_data[5]
            # Convert to dBm (negative value)
            return -rssi_raw
        return None
    
    def get_data_bytes(self) -> bytes:
        """Get data bytes (without sender ID and status)"""
        if self.packet_type == self.PACKET_TYPE_RADIO_ERP1:
            if len(self.data) >= 6:
                # Data bytes are after sender ID (4 bytes) and before status byte
                return self.data[5:-1]
        return b''
    
    def get_status_byte(self) -> Optional[int]:
        """Get status byte from telegram"""
        if self.packet_type == self.PACKET_TYPE_RADIO_ERP1:
            if len(self.data) >= 1:
                return self.data[-1]
        return None
    
    def is_teach_in(self) -> bool:
        """Check if this is a teach-in telegram"""
        rorg = self.get_rorg()
        status = self.get_status_byte()
        
        if rorg == 0xA5:  # 4BS telegram
            # Check LRN bit (bit 3 of status byte)
            if status is not None:
                return (status & 0x08) == 0
        elif rorg == 0xF6:  # RPS telegram
            # RPS teach-in detection is more complex
            # Usually indicated by specific button combinations
            pass
        elif rorg == 0xD5:  # 1BS telegram
            # Check LRN bit
            if status is not None:
                return (status & 0x08) == 0
        
        return False
    
    @classmethod
    def create_common_command(cls, command: int, data: bytes = b'') -> 'ESP3Packet':
        """Create a common command packet"""
        packet = cls()
        packet.packet_type = cls.PACKET_TYPE_COMMON_COMMAND
        packet.data = bytes([command]) + data
        packet.data_length = len(packet.data)
        packet.optional_length = 0
        packet.optional_data = b''
        return packet
    
    @classmethod
    def create_read_base_id(cls) -> 'ESP3Packet':
        """Create packet to read base ID"""
        return cls.create_common_command(cls.CO_RD_IDBASE)
    
    @classmethod
    def create_read_version(cls) -> 'ESP3Packet':
        """Create packet to read version info"""
        return cls.create_common_command(cls.CO_RD_VERSION)
    
    def __repr__(self) -> str:
        return (f"ESP3Packet(type={hex(self.packet_type)}, "
                f"data_len={self.data_length}, "
                f"opt_len={self.optional_length}, "
                f"sender={self.get_sender_id()}, "
                f"rorg={hex(self.get_rorg()) if self.get_rorg() else None})")
