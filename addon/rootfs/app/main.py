"""
EnOcean MQTT TCP - Main Application
"""
import asyncio
import logging
import os
import sys
import signal
import json
from datetime import datetime, timedelta

# Determine base path dynamically
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
if BASE_PATH not in sys.path:
    sys.path.insert(0, BASE_PATH)

# FIX: Persistent Storage Path definition
DATA_PATH = '/data'

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
        self.addon_version = os.getenv('ADDON_VERSION', 'dev')
        self.serial_port = os.getenv('SERIAL_PORT', '')
        self.mqtt_host = os.getenv('MQTT_HOST', 'localhost')
        self.mqtt_port = int(os.getenv('MQTT_PORT', 1883))
        self.mqtt_user = os.getenv('MQTT_USER', '')
        self.mqtt_password = os.getenv('MQTT_PASSWORD', '')
        self.restore_state = os.getenv('RESTORE_STATE', 'true').lower() == 'true'
        self.restore_delay = int(os.getenv('RESTORE_DELAY', 5))
        self.provisioning_url = os.getenv('PROVISIONING_URL', 'https://prov.busser.io')

    # --- Discovery Methods ---
    def start_discovery(self, duration_seconds=60):
        self.discovery_end_time = datetime.now() + timedelta(seconds=duration_seconds)
        logger.info(f"🔎 DISCOVERY MODE ENABLED for {duration_seconds} seconds")
        return True

    def stop_discovery(self):
        self.discovery_end_time = None
        logger.info(f"🛑 DISCOVERY MODE DISABLED")
        return True

    def is_discovery_active(self):
        if self.discovery_end_time:
            if datetime.now() < self.discovery_end_time:
                return True
            else:
                self.discovery_end_time = None 
        return False
        
    def get_discovery_time_remaining(self):
        if not self.is_discovery_active(): return 0
        return int((self.discovery_end_time - datetime.now()).total_seconds())

    # --- Provisioning Logic ---
    async def _download_and_save_profile(self, url, filename_hint):
        """
        Downloads JSON profile, saves it to PERSISTENT storage, and RETURNS THE INTERNAL EEP NAME.
        """
        import aiohttp
        try:
            logger.info(f"Downloading profile from {url}...")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        real_eep_name = data.get('eep')
                        if not real_eep_name:
                            logger.error("Downloaded JSON has no 'eep' field!")
                            return None

                        # FIX: Save to /data/eep
                        path = os.path.join(DATA_PATH, 'eep')
                        os.makedirs(path, exist_ok=True)
                        
                        filename = f"{filename_hint}.json"
                        with open(os.path.join(path, filename), 'w') as f:
                            json.dump(data, f, indent=2)
                        
                        self.eep_loader.load_profiles() 
                        logger.info(f"✅ Profile loaded to persistent storage. Internal Name: {real_eep_name}")
                        return real_eep_name
                    else:
                        logger.error(f"Download failed with status {response.status}")
        except Exception as e:
            logger.error(f"Download failed: {e}")
        return None

    async def check_cloud_provisioning(self, device_id):
        if not self.provisioning_url: return None
        import aiohttp
        try:
            url = f"{self.provisioning_url.rstrip('/')}/{device_id}.json"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=2) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info("✨ Provisioning data found!")
                        return data
        except Exception as e:
            pass
        return None

    # --- Initialization ---
    async def initialize(self):
        logger.info("=" * 60)
        logger.info(f"EnOcean MQTT TCP v{self.addon_version} - Starting...")
        logger.info("=" * 60)
        
        service_state.update_status('version', self.addon_version)

        # 1. Load EEPs (Built-in AND Persistent)
        eep_path_builtin = os.path.join(BASE_PATH, 'eep', 'definitions')
        eep_path_custom = os.path.join(DATA_PATH, 'eep')
        
        # FIX: Loader mit beiden Pfaden initialisieren
        self.eep_loader = EEPLoader([eep_path_builtin, eep_path_custom])
        self.eep_parser = EEPParser() 
        service_state.update_status('eep_profiles', len(self.eep_loader.profiles))
        logger.info(f"✓ EEP Loader initialized (Custom Path: {eep_path_custom})")

        # 2. Connection
        if self.serial_port:
            logger.info(f"Initializing connection to: {self.serial_port}")
            try:
                self.serial_handler = SerialHandler(self.serial_port)
                if self.serial_handler.open():
                    logger.info("✓ Transceiver connection established")
                    service_state.update_status('gateway_connected', True)
                else:
                    logger.warning("⚠️ Connection failed. Will retry...")
                    service_state.update_status('gateway_connected', False)
            except Exception as e:
                logger.error(f"Error initializing handler: {e}")
                self.serial_handler = None
        else:
            logger.warning("No connection string configured")

        # 3. Core (FIX: DeviceManager on persistent storage)
        self.device_manager = DeviceManager(os.path.join(DATA_PATH, 'devices.json'))
        service_state.update_status('devices', len(self.device_manager.list_devices()))
        
        self.state_persistence = StatePersistence() # StatePersistence nutzt intern meist eh schon default paths, aber ist hier ok.
        self.command_translator = CommandTranslator(self.eep_loader)
        self.command_tracker = CommandTracker()
        self.command_tracker.set_confirmation_callback(self.on_command_confirmed)
        self.command_tracker.start()

        # 4. MQTT
        self.mqtt_handler = MQTTHandler(self.mqtt_host, self.mqtt_port, self.mqtt_user, self.mqtt_password)
        if self.mqtt_handler.connect():
            await asyncio.sleep(1)
            if self.mqtt_handler.connected:
                logger.info("✓ MQTT connected")
                service_state.update_status('mqtt_connected', True)
                self.mqtt_handler.event_loop = asyncio.get_event_loop()
                self.mqtt_handler.subscribe_commands(self.handle_command)
                
                # Discovery for existing devices
                for device in self.device_manager.list_devices():
                    if device.get('enabled') and device.get('eep') != 'pending':
                        await self.publish_device_discovery(device)
            else:
                service_state.update_status('mqtt_connected', False)
        
        return True

    # --- Core Logic ---
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
            
            # --- NEW DEVICE LOGIC ---
            if not device:
                if not self.is_discovery_active():
                    return 
                
                cloud_config = await self.check_cloud_provisioning(sender_id)
                
                if cloud_config:
                    logger.info(f"✨ Auto-Provisioning success for {sender_id}")
                    
                    variants = cloud_config.get('variants', [])
                    default_id = cloud_config.get('default_variant')
                    target_variant = next((v for v in variants if v['id'] == default_id), None)
                    
                    eep_to_use = cloud_config.get('eep', 'pending')
                    
                    if target_variant:
                        local_name_hint = f"PROV-{sender_id}-{target_variant['id']}"
                        # FIX: Download returns real EEP name
                        real_eep = await self._download_and_save_profile(target_variant['url'], local_name_hint)
                        if real_eep:
                            eep_to_use = real_eep
                    
                    self.device_manager.add_device(
                        sender_id,
                        cloud_config.get('name', f"Device {sender_id}"),
                        eep_to_use,
                        cloud_config.get('manufacturer', 'Unknown'),
                        provisioning_data=variants 
                    )
                    
                    device = self.device_manager.get_device(sender_id)
                    if eep_to_use != 'pending':
                         await self.publish_device_discovery(device)
                
                else:
                    logger.info(f"🆕 NEW DEVICE: {sender_id}")
                    self.device_manager.add_device(sender_id, f"New Device {sender_id}", "pending", "Unknown")
                    device = self.device_manager.get_device(sender_id)

            # --- Update Stats ---
            if not device: return 
            device['rorg'] = hex(rorg)
            self.device_manager.update_last_seen(sender_id, rssi) 
            service_state.update_status('devices', len(self.device_manager.list_devices()))

            if not device.get('enabled'): return
            if not service_state.get_status().get('gateway_connected'):
                service_state.update_status('gateway_connected', True)

            if device.get('eep') == 'pending': return

            # Parsing
            profile = self.eep_loader.get_profile(device['eep'])
            if not profile: 
                # logger.warning(f"Profile {device['eep']} not found!")
                return
            
            parsed_data = self.eep_parser.parse_telegram_with_full_data(packet.data, profile)

            if parsed_data:
                from datetime import datetime, timezone
                parsed_data['rssi'] = rssi
                parsed_data['last_seen'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                
                logger.info(f"📊 {device['name']}: {parsed_data}")
                
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

    async def on_command_confirmed(self, d, e, c, s): logger.info(f"Command confirmed {d}")
    async def on_command_timeout(self, d, e, c): logger.warning(f"Command timeout {d}")
    async def handle_command(self, device_id, entity, command):
        try:
            if not self.serial_handler: return
            device = self.device_manager.get_device(device_id)
            if not device or not device.get('enabled'): return
            logger.info(f"Command for {device_id}: {command}")
            result = self.command_translator.translate_command(device, entity, command)
            if result: pass 
        except Exception as e: logger.error(f"Cmd Error: {e}")

    async def run_serial_reader(self):
        if self.serial_handler:
            try: await self.serial_handler.start_reading(self.process_telegram)
            except: pass

    async def run_web_server(self):
        config = uvicorn.Config(web_app, host="0.0.0.0", port=8099, log_level="warning", access_log=True, loop="asyncio")
        server = uvicorn.Server(config)
        await server.serve()

    async def run(self):
        self.running = True
        service_state.set_service(self)
        tasks = [asyncio.create_task(self.run_web_server())]
        await self.initialize()
        service_state.update_status('status', 'running')
        if self.restore_state: await asyncio.sleep(self.restore_delay)
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try: loop.add_signal_handler(sig, lambda: stop_event.set())
            except: pass
        tasks.append(asyncio.create_task(stop_event.wait()))
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
