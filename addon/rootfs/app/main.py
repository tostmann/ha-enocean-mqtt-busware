"""
EnOcean MQTT TCP - Main Application
(Updated: Version, EEP Count & Name)
"""
import asyncio
import logging
import os
import sys
import signal
from datetime import datetime, timedelta

# Determine base path dynamically
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
if BASE_PATH not in sys.path:
    sys.path.insert(0, BASE_PATH)

from core.serial_handler import SerialHandler
from core.esp3_protocol import ESP3Packet
from core.mqtt_handler import MQTTHandler
from core.device_manager import DeviceManager
from core.state_persistence import StatePersistence
from core.command_translator import CommandTranslator
from core.command_tracker import CommandTracker
from eep.loader import EEPLoader
from eep.parser import EEPParser
from service_state import service_state
import uvicorn
from web_ui.app import app as web_app

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
        self.mqtt_handler = None
        self.device_manager = None
        self.state_persistence = None
        self.eep_loader = None
        self.eep_parser = None
        self.command_translator = None
        self.command_tracker = None
        self.running = False
        self.discovery_end_time = None
        
        # Config
        self.addon_version = os.getenv('ADDON_VERSION', 'dev') # NEU
        self.serial_port = os.getenv('SERIAL_PORT', '')
        self.mqtt_host = os.getenv('MQTT_HOST', 'localhost')
        self.mqtt_port = int(os.getenv('MQTT_PORT', 1883))
        self.mqtt_user = os.getenv('MQTT_USER', '')
        self.mqtt_password = os.getenv('MQTT_PASSWORD', '')
        self.restore_state = os.getenv('RESTORE_STATE', 'true').lower() == 'true'
        self.restore_delay = int(os.getenv('RESTORE_DELAY', 5))
    
    # ... (Discovery Methods unverändert) ...
    def start_discovery(self, duration_seconds=60):
        self.discovery_end_time = datetime.now() + timedelta(seconds=duration_seconds)
        logger.info(f"🔎 DISCOVERY MODE ENABLED for {duration_seconds} seconds")
        return True

    def stop_discovery(self):
        self.discovery_end_time = None
        logger.info(f"🛑 DISCOVERY MODE DISABLED")
        return True

    def is_discovery_active(self):
        if self.discovery_end_time and datetime.now() < self.discovery_end_time:
            return True
        self.discovery_end_time = None
        return False
        
    def get_discovery_time_remaining(self):
        if not self.is_discovery_active(): return 0
        return int((self.discovery_end_time - datetime.now()).total_seconds())

    # --- Initialization ---
    async def initialize(self):
        logger.info("=" * 60)
        logger.info(f"EnOcean MQTT TCP v{self.addon_version} - Starting...")
        logger.info("=" * 60)
        
        # STATUS UPDATE: Version initial setzen
        service_state.update_status('version', self.addon_version)

        # 1. Load EEPs
        logger.info("Loading EEP profiles...")
        eep_path = os.path.join(BASE_PATH, 'eep', 'definitions')
        self.eep_loader = EEPLoader(eep_path)
        self.eep_parser = EEPParser()
        
        if len(self.eep_loader.profiles) == 0:
            logger.error(f"No EEP profiles loaded!")
            return False
            
        logger.info(f"✓ Loaded {len(self.eep_loader.profiles)} EEP profiles")
        # STATUS UPDATE: EEP Count
        service_state.update_status('eep_profiles', len(self.eep_loader.profiles))

        # 2. Connection Logic
        if self.serial_port:
            logger.info(f"Initializing connection to: {self.serial_port}")
            try:
                self.serial_handler = SerialHandler(self.serial_port)
                if self.serial_handler.open():
                    logger.info("✓ Transceiver connection established successfully")
                    service_state.update_status('gateway_connected', True)
                else:
                    logger.warning(f"⚠️ Initial connection to {self.serial_port} failed. Will retry...")
                    service_state.update_status('gateway_connected', False)
            except Exception as e:
                logger.error(f"Error initializing handler: {e}")
                self.serial_handler = None
        else:
            logger.warning("No connection string configured")

        # 3. Core Components
        self.device_manager = DeviceManager()
        service_state.update_status('devices', len(self.device_manager.list_devices()))
        
        self.state_persistence = StatePersistence()
        self.command_translator = CommandTranslator(self.eep_loader)
        
        self.command_tracker = CommandTracker()
        self.command_tracker.set_confirmation_callback(self.on_command_confirmed)
        self.command_tracker.set_timeout_callback(self.on_command_timeout)
        self.command_tracker.start()

        # 4. MQTT
        self.mqtt_handler = MQTTHandler(self.mqtt_host, self.mqtt_port, self.mqtt_user, self.mqtt_password)
        if self.mqtt_handler.connect():
            await asyncio.sleep(1)
            if self.mqtt_handler.connected:
                logger.info("✓ MQTT connected successfully")
                service_state.update_status('mqtt_connected', True)
                self.mqtt_handler.event_loop = asyncio.get_event_loop()
                self.mqtt_handler.subscribe_commands(self.handle_command)
                
                for device in self.device_manager.list_devices():
                    if device.get('enabled') and device.get('eep') != 'pending':
                        await self.publish_device_discovery(device)
            else:
                logger.warning("MQTT connection pending...")
                service_state.update_status('mqtt_connected', False)
        
        logger.info("=" * 60)
        return True

    # ... (Rest der Datei callbacks, process_telegram, etc. bleibt identisch wie zuvor) ...
    # (Ich kürze hier ab, um Platz zu sparen - der Rest ist unverändert zur letzten Version)
    
    async def on_command_confirmed(self, device_id: str, entity: str, command: dict, state_data: dict):
        logger.info(f"   🎯 Command confirmation processed for {device_id}/{entity}")
    
    async def on_command_timeout(self, device_id: str, entity: str, command: dict):
        logger.warning(f"   ⚠️  Command timeout - device may not have responded")
    
    async def publish_device_discovery(self, device: dict):
        if device.get('eep') == 'pending': return
        try:
            profile = self.eep_loader.get_profile(device['eep'])
            if not profile: return
            is_controllable = self.command_translator.is_controllable(device['eep'])
            if self.mqtt_handler and self.mqtt_handler.connected:
                self.mqtt_handler.client.publish(f"enocean/{device['id']}/state", "", qos=1, retain=True)
                self.mqtt_handler.client.publish(f"enocean/{device['id']}/availability", "", qos=1, retain=True)
                await asyncio.sleep(0.1)
            entities = profile.get_entities()
            for entity in entities:
                entity_controllable = is_controllable
                if entity.get('component', 'sensor') in ['sensor', 'binary_sensor']:
                    entity_controllable = False
                self.mqtt_handler.publish_discovery(device, entity, entity_controllable)
            self.mqtt_handler.publish_availability(device['id'], True)
        except Exception as e:
            logger.error(f"Error publishing discovery: {e}")

    async def process_telegram(self, packet: ESP3Packet):
        try:
            sender_id = packet.get_sender_id()
            rorg = packet.get_rorg()
            rssi = packet.get_rssi()
            device = self.device_manager.get_device(sender_id)
            
            if not device:
                if not self.is_discovery_active(): return
                logger.info("=" * 80)
                logger.info("🆕 NEW DEVICE DETECTED (Discovery Mode Active)")
                self.device_manager.add_device(sender_id, f"New Device {sender_id}", "pending", "Unknown")
                device = self.device_manager.get_device(sender_id)
                if device:
                    device['rorg'] = hex(rorg)
                    device['rssi'] = rssi
                    device['last_seen'] = datetime.now().isoformat()
                    self.device_manager.save_devices()
                    service_state.update_status('devices', len(self.device_manager.list_devices()))
                logger.info("   ✅ Device added! Go to Web UI to select profile.")
                return

            if not device.get('enabled'): return
            if not service_state.get_status().get('gateway_connected'):
                service_state.update_status('gateway_connected', True)
            if device.get('eep') == 'pending':
                self.device_manager.update_last_seen(sender_id, rssi)
                return

            self.device_manager.update_last_seen(sender_id, rssi)
            profile = self.eep_loader.get_profile(device['eep'])
            if not profile: return
            parsed_data = self.eep_parser.parse_telegram_with_full_data(packet.data, profile)

            if parsed_data:
                from datetime import datetime, timezone
                parsed_data['rssi'] = rssi
                parsed_data['last_seen'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                logger.info(f"📊 {device['name']} ({sender_id}): {parsed_data}")
                if self.command_tracker: await self.command_tracker.check_telegram(sender_id, parsed_data)
                if self.state_persistence: self.state_persistence.save_state(sender_id, parsed_data)
                if self.mqtt_handler and self.mqtt_handler.connected:
                    if not device.get('discovery_published', False):
                        await self.publish_device_discovery(device)
                        device['discovery_published'] = True
                        self.device_manager.devices[sender_id] = device
                    self.mqtt_handler.publish_state(sender_id, parsed_data, retain=True)
                    self.mqtt_handler.publish_availability(sender_id, True)
                else:
                    if service_state.get_status().get('mqtt_connected'): service_state.update_status('mqtt_connected', False)
        except Exception as e:
            logger.error(f"Error processing telegram: {e}", exc_info=True)

    async def handle_command(self, device_id: str, entity: str, command: dict):
        try:
            if not self.serial_handler: return
            device = self.device_manager.get_device(device_id)
            if not device or not device.get('enabled') or device.get('eep') == 'pending': return
            logger.info(f"🎮 Command for {device['name']}: {command}")
            result = self.command_translator.translate_command(device, entity, command)
            if not result:
                logger.error(f"   ❌ Could not translate command")
                return
            command_type, rorg_or_button, data_bytes = result
            success = False
            if command_type == 'rps':
                success = await self.serial_handler.send_rps_command(device_id, rorg_or_button)
            elif command_type == 'telegram':
                success = await self.serial_handler.send_telegram(device_id, rorg_or_button, data_bytes)
            if success:
                logger.info(f"   ✅ Command sent")
                if self.mqtt_handler and self.mqtt_handler.connected:
                    state_update = {}
                    if 'state' in command: state_update[entity] = 1 if command['state'].upper() == 'ON' else 0
                    elif 'brightness' in command: state_update[entity] = command['brightness']
                    if state_update: self.mqtt_handler.publish_state(device_id, state_update, retain=True)
        except Exception as e:
            logger.error(f"Error handling command: {e}")

    async def run_serial_reader(self):
        if self.serial_handler:
            try: await self.serial_handler.start_reading(self.process_telegram)
            except: pass

    async def run_web_server(self):
        config = uvicorn.Config(web_app, host="0.0.0.0", port=8099, log_level="warning", access_log=False, loop="asyncio")
        server = uvicorn.Server(config)
        await server.serve()

    async def run(self):
        self.running = True
        if not await self.initialize(): return
        service_state.set_service(self)
        service_state.update_status('status', 'running')
        if self.restore_state and self.state_persistence and self.mqtt_handler:
             await asyncio.sleep(self.restore_delay)
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try: loop.add_signal_handler(sig, lambda: stop_event.set())
            except: pass
        tasks = [asyncio.create_task(self.run_web_server()), asyncio.create_task(stop_event.wait())]
        if self.serial_handler: tasks.append(asyncio.create_task(self.run_serial_reader()))
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        service_state.update_status('status', 'stopping')
        self.running = False
        if self.serial_handler: 
            self.serial_handler.stop_reading()
            self.serial_handler.close()

async def main():
    service = EnOceanMQTTService()
    await service.run()

if __name__ == "__main__":
    try: asyncio.run(main())
    except: pass
