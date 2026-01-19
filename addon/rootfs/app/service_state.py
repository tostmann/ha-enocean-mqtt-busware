"""
Service State Singleton
Shared state between Main Service and Web UI
"""

class ServiceState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ServiceState, cls).__new__(cls)
            cls._instance.initialized = False
            cls._instance.status = {
                "status": "starting",
                "mqtt_connected": False,
                "gateway_connected": False,
                "devices": 0,
                "eep_profiles": 0
            }
            cls._instance.gateway_info = {}
            cls._instance._service = None # Reference to main service instance
            cls._instance.detected_profiles = {} # Cache for teach-in detection
        return cls._instance

    def set_service(self, service):
        """Store reference to main service instance"""
        self._service = service

    def get_service(self):
        """Get reference to main service instance"""
        return self._service

    def update_status(self, key, value):
        self.status[key] = value

    def get_status(self):
        return self.status

    def set_gateway_info(self, info):
        self.gateway_info = info

    def get_gateway_info(self):
        return self.gateway_info

    # Helper methods to access components via service
    def get_device_manager(self):
        if self._service:
            return self._service.device_manager
        return None

    def get_mqtt_handler(self):
        if self._service:
            return self._service.mqtt_handler
        return None

    def get_eep_loader(self):
        if self._service:
            return self._service.eep_loader
        return None
    
    # Teach-in helpers
    def set_detected_profiles(self, device_id, profiles):
        self.detected_profiles[device_id] = profiles
        
    def get_detected_profiles(self, device_id):
        return self.detected_profiles.get(device_id, [])

# Global instance
service_state = ServiceState()
