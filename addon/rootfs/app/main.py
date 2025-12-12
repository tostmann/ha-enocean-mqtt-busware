"""
EnOcean MQTT Slim - Main Application
"""
import asyncio
import logging
import os
import sys
from datetime import datetime

from core.serial_handler import SerialHandler
from core.esp3_protocol import ESP3Packet
from eep.loader import EEPLoader
from eep.parser import EEPParser

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


class EnOceanMQTTService:
    """Main service for EnOcean MQTT bridge"""
    
    def __init__(self):
        self.serial_handler = None
        self.eep_loader = None
        self.eep_parser = None
        self.running = False
        
        # Configuration from environment
        self.serial_port = os.getenv('SERIAL_PORT', '')
        self.mqtt_host = os.getenv('MQTT_HOST', 'localhost')
        self.mqtt_port = int(os.getenv('MQTT_PORT', 1883))
        self.mqtt_user = os.getenv('MQTT_USER', '')
        self.mqtt_password = os.getenv('MQTT_PASSWORD', '')
    
    async def initialize(self):
        """Initialize all components"""
        logger.info("=" * 60)
        logger.info("EnOcean MQTT Slim - Starting...")
        logger.info("=" * 60)
        
        # Load EEP profiles
        logger.info("Loading EEP profiles...")
        self.eep_loader = EEPLoader('/app/eep/definitions')
        self.eep_parser = EEPParser()
        
        if len(self.eep_loader.profiles) == 0:
            logger.error("No EEP profiles loaded! Check definitions directory.")
            return False
        
        logger.info(f"✓ Loaded {len(self.eep_loader.profiles)} EEP profiles")
        
        # List some profiles
        profiles = self.eep_loader.list_profiles()
        logger.info("Available EEP profiles:")
        for profile in profiles[:5]:  # Show first 5
            logger.info(f"  - {profile['eep']}: {profile['title']}")
        if len(profiles) > 5:
            logger.info(f"  ... and {len(profiles) - 5} more")
        
        # Initialize serial port if configured
        if self.serial_port:
            logger.info(f"Opening serial port: {self.serial_port}")
            self.serial_handler = SerialHandler(self.serial_port)
            
            if not self.serial_handler.open():
                logger.error(f"Failed to open serial port: {self.serial_port}")
                logger.warning("Continuing without serial port (web UI only mode)")
                self.serial_handler = None
            else:
                logger.info("✓ Serial port opened successfully")
                
                # Query gateway info
                try:
                    base_id = await self.serial_handler.get_base_id()
                    if base_id:
                        logger.info(f"✓ Gateway Base ID: {base_id}")
                    
                    version_info = await self.serial_handler.get_version_info()
                    if version_info:
                        logger.info(f"✓ Gateway Version: {version_info['app_version']}")
                        logger.info(f"  Chip ID: {version_info['chip_id']}")
                        logger.info(f"  Description: {version_info['app_description']}")
                except Exception as e:
                    logger.error(f"Error querying gateway info: {e}")
        else:
            logger.warning("No serial port configured")
            logger.info("Running in web UI only mode")
        
        # MQTT connection info
        logger.info(f"MQTT Broker: {self.mqtt_host}:{self.mqtt_port}")
        if self.mqtt_user:
            logger.info(f"MQTT User: {self.mqtt_user}")
        
        logger.info("=" * 60)
        logger.info("Initialization complete!")
        logger.info("=" * 60)
        
        return True
    
    async def process_telegram(self, packet: ESP3Packet):
        """Process received EnOcean telegram"""
        try:
            sender_id = packet.get_sender_id()
            rorg = packet.get_rorg()
            rssi = packet.get_rssi()
            
            logger.info(f"Received telegram from {sender_id}, RORG={hex(rorg) if rorg else 'N/A'}, RSSI={rssi}dBm")
            
            # Check if it's a teach-in telegram
            if packet.is_teach_in():
                logger.info(f"  → Teach-in telegram detected!")
            
            # For now, just log the raw data
            data_bytes = packet.get_data_bytes()
            logger.debug(f"  Data: {data_bytes.hex()}")
            
            # TODO: Look up device in database
            # TODO: Parse using EEP profile
            # TODO: Publish to MQTT
            
        except Exception as e:
            logger.error(f"Error processing telegram: {e}")
    
    async def run(self):
        """Main run loop"""
        self.running = True
        
        if not await self.initialize():
            logger.error("Initialization failed, exiting")
            return
        
        logger.info("Service is running...")
        logger.info("Press Ctrl+C to stop")
        
        # Start serial reading if available
        if self.serial_handler:
            logger.info("Listening for EnOcean telegrams...")
            try:
                await self.serial_handler.start_reading(self.process_telegram)
            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
        else:
            # No serial port, just keep running
            logger.info("No serial port - web UI only mode")
            try:
                while self.running:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
        
        await self.shutdown()
    
    async def shutdown(self):
        """Shutdown service"""
        logger.info("Shutting down...")
        self.running = False
        
        if self.serial_handler:
            self.serial_handler.stop_reading()
            self.serial_handler.close()
        
        logger.info("Shutdown complete")


async def main():
    """Main entry point"""
    service = EnOceanMQTTService()
    await service.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
