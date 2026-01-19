import json
import os
import logging

logger = logging.getLogger(__name__)

class DeviceManager:
    def __init__(self, storage_path=None):
        # Intelligente Pfad-Ermittlung
        if storage_path:
            self.storage_path = storage_path
        else:
            # Wenn wir im Home Assistant Addon sind, existiert /data
            if os.path.exists('/data') and os.access('/data', os.W_OK):
                self.storage_path = '/data/devices.json'
            else:
                # Fallback für lokale Entwicklung (damit keine Permission Errors kommen)
                self.storage_path = os.path.join(os.getcwd(), 'devices.json')
                logger.info(f"Running locally. Using storage path: {self.storage_path}")

        self.devices = {}
        self.load_devices()

    def load_devices(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    self.devices = json.load(f)
            except Exception as e:
                logger.error(f"Error loading devices from {self.storage_path}: {e}")
                self.devices = {}
        else:
            self.devices = {}

    def save_devices(self):
        try:
            # Sicherstellen, dass das Verzeichnis existiert
            directory = os.path.dirname(self.storage_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                
            with open(self.storage_path, 'w') as f:
                json.dump(self.devices, f, indent=2)
            # logger.info(f"Devices saved to {self.storage_path}") # Debug level, sonst Spam
        except Exception as e:
            logger.error(f"Error saving devices to {self.storage_path}: {e}")

    def list_devices(self):
        return list(self.devices.values())

    def get_device(self, device_id):
        return self.devices.get(device_id)

    def add_device(self, device_id, name, eep, manufacturer="EnOcean"):
        # Verhindern, dass wir existierende (konfigurierte) Geräte überschreiben
        if device_id in self.devices and self.devices[device_id].get('eep') != 'pending':
            return False
            
        self.devices[device_id] = {
            "id": device_id,
            "name": name,
            "eep": eep,
            "manufacturer": manufacturer,
            "enabled": True
        }
        self.save_devices()
        return True

    def update_device(self, device_id, data):
        """Update existing device configuration"""
        if device_id not in self.devices:
            return False
            
        device = self.devices[device_id]
        
        # Felder aktualisieren
        if 'name' in data: device['name'] = data['name']
        if 'eep' in data: device['eep'] = data['eep']
        if 'manufacturer' in data: device['manufacturer'] = data['manufacturer']
        if 'enabled' in data: device['enabled'] = data['enabled']
        if 'rorg' in data: device['rorg'] = data['rorg']
        
        self.save_devices()
        return True

    def remove_device(self, device_id):
        if device_id in self.devices:
            del self.devices[device_id]
            self.save_devices()
            return True
        return False
        
    def update_last_seen(self, device_id, rssi):
        if device_id in self.devices:
            self.devices[device_id]['rssi'] = rssi
            # Wir speichern RSSI nicht jedes Mal auf die Disk (schont SD-Karte)
