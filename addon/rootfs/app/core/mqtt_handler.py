import asyncio
import json
import logging
import os  # <--- DIESER IMPORT FEHLTE!
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

class MQTTHandler:
    def __init__(self, host, port, username, password):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        # Hier wurde 'os' verwendet, ohne importiert zu sein:
        self.client = mqtt.Client(client_id=f"enocean-mqtt-tcp-{os.urandom(4).hex()}")
        
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)
        
        self.connected = False
        self.command_callback = None
        self.event_loop = None

        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def connect(self):
        try:
            self.client.connect(self.host, self.port, 60)
            self.client.loop_start()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            return False

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            logger.info("✓ Connected to MQTT broker")
            if self.command_callback:
                client.subscribe("enocean/+/set/#")
        else:
            logger.error(f"Failed to connect to MQTT, return code {rc}")

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        logger.warning("Disconnected from MQTT broker")

    def on_message(self, client, userdata, msg):
        try:
            if not self.command_callback or not self.event_loop: return
            parts = msg.topic.split('/')
            if len(parts) >= 4 and parts[2] == 'set':
                device_id = parts[1]
                entity_key = parts[3]
                payload = msg.payload.decode()
                asyncio.run_coroutine_threadsafe(
                    self.command_callback(device_id, entity_key, payload),
                    self.event_loop
                )
        except Exception as e:
            logger.error(f"Error handling MQTT message: {e}")

    def subscribe_commands(self, callback):
        self.command_callback = callback
        self.client.subscribe("enocean/+/set/#")

    def publish_discovery(self, device, entity, controllable=False):
        device_id = device['id']
        key = entity.get('key', 'main')
        component = entity.get('component', 'sensor')
        unique_id = f"{device_id}_{key}"
        discovery_topic = f"homeassistant/{component}/{unique_id}/config"

        config = {
            "name": f"{device['name']} {entity.get('name', key)}",
            "unique_id": unique_id,
            "device": {
                "identifiers": [f"enocean_{device_id}"],
                "name": device['name'],
                "manufacturer": device.get('manufacturer', 'EnOcean'),
                "model": device.get('eep', 'Unknown'),
                "via_device": "EnOcean_MQTT_TCP"
            },
            "state_topic": f"enocean/{device_id}/state",
            "availability_topic": f"enocean/{device_id}/availability",
            "value_template": f"{{{{ value_json.{key} }}}}",
        }

        for attr in ['device_class', 'unit_of_measurement', 'icon']:
            if attr == 'unit_of_measurement':
                if 'unit' in entity: config[attr] = entity['unit']
            elif attr in entity:
                config[attr] = entity[attr]

        if controllable:
            config["command_topic"] = f"enocean/{device_id}/set/{key}"

        self.client.publish(discovery_topic, json.dumps(config), qos=1, retain=True)

    def publish_state(self, device_id, data, retain=True):
        topic = f"enocean/{device_id}/state"
        self.client.publish(topic, json.dumps(data), qos=1, retain=retain)

    def publish_availability(self, device_id, available=True):
        topic = f"enocean/{device_id}/availability"
        payload = "online" if available else "offline"
        self.client.publish(topic, payload, qos=1, retain=True)

    def remove_device(self, device_id, entities):
        if not self.connected: return
        logger.info(f"🗑 Removing device {device_id} from Home Assistant...")
        
        self.client.publish(f"enocean/{device_id}/state", "", qos=1, retain=True)
        self.client.publish(f"enocean/{device_id}/availability", "", qos=1, retain=True)

        for entity in entities:
            key = entity.get('key', 'main')
            component = entity.get('component', 'sensor')
            unique_id = f"{device_id}_{key}"
            discovery_topic = f"homeassistant/{component}/{unique_id}/config"
            self.client.publish(discovery_topic, "", qos=1, retain=True)
            logger.debug(f"   -> Cleared discovery topic: {discovery_topic}")
