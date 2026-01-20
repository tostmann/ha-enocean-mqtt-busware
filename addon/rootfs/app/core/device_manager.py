import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class DeviceManager:
    def __init__(self, storage_path=None):
        # FIX: Standardmäßig persistenten Speicher /data nutzen
        if not storage_path:
            storage_path = '/data/devices.json'
        
        self.storage_file = storage_path
        
        # Sicherstellen, dass das Verzeichnis existiert
        try:
            os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create storage directory: {e}")
        
        self.devices = {}
        self.load_devices()

    def load_devices(self):
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    self.devices = json.load(f)
                logger.info(f"Loaded {len(self.devices)} devices from {self.storage_file}")
            except Exception as e:
                logger.error(f"Error loading devices: {e}")
                self.devices = {}
        else:
            logger.info(f"No device database found at {self.storage_file}, starting fresh.")
            self.devices = {}

    def save_devices(self):
        try:
            with open(self.storage_file, 'w') as f:
                json.dump(self.devices, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving devices: {e}")

    def list_devices(self):
        return list(self.devices.values())

    def get_device(self, device_id):
        return self.devices.get(device_id)

    def add_device(self, device_id, name, eep, manufacturer='Unknown', provisioning_data=None):
        # Wenn Gerät existiert und EEP gleich ist, nichts tun
        if device_id in self.devices and self.devices[device_id].get('eep') == eep:
            return False
        
        device = {
            'id': device_id,
            'name': name,
            'eep': eep,
            'manufacturer': manufacturer,
            'enabled': True,
            'created_at': datetime.now().isoformat()
        }
        if provisioning_data:
            device['provisioning_options'] = provisioning_data
            
        self.devices[device_id] = device
        self.save_devices()
        logger.info(f"Added/Updated device: {device_id} ({name})")
        return True

    def update_device(self, device_id, data):
        if device_id in self.devices:
            self.devices[device_id].update(data)
            self.save_devices()
            logger.info(f"Updated device {device_id}")
            return True
        return False
        
    def remove_device(self, device_id):
        if device_id in self.devices:
            del self.devices[device_id]
            self.save_devices()
            logger.info(f"Removed device {device_id}")
            return True
        return False

    def update_last_seen(self, device_id, rssi):
        if device_id in self.devices:
            self.devices[device_id]['rssi'] = rssi
            self.devices[device_id]['last_seen'] = datetime.now().isoformat()
            # Wir speichern hier NICHT jedes Mal auf Disk (I/O Reduktion)
