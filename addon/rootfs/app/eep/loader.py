import os
import json
import logging
from glob import glob

logger = logging.getLogger(__name__)

class EEPProfile:
    """Wrapper class for profile data"""
    def __init__(self, data):
        self.data = data
        self.eep = data.get('eep')
        self.title = data.get('type_title', 'Unknown')
        self.rorg = data.get('rorg_number')

    def get_entities(self):
        entities = []
        objects = self.data.get('objects', {})
        for key, config in objects.items():
            entity = config.copy()
            entity['key'] = key
            if 'component' not in entity:
                entity['component'] = 'sensor'
            entities.append(entity)
        return entities

class EEPLoader:
    def __init__(self, base_paths):
        """
        base_paths: List of directories to search for EEPs (or single string)
        """
        if isinstance(base_paths, str):
            self.base_paths = [base_paths]
        else:
            self.base_paths = base_paths
            
        self.profiles = {}
        self.load_profiles()

    def load_profiles(self):
        """Loads or reloads all JSON profiles from all configured base paths"""
        self.profiles = {}
        count = 0
        
        # Durchlaufe alle Pfade (z.B. erst /app/eep..., dann /data/eep...)
        # Spätere Definitionen überschreiben frühere -> Custom > Built-in
        for base_path in self.base_paths:
            if not os.path.exists(base_path):
                continue
                
            logger.info(f"Scanning for EEPs in {base_path}...")
            pattern = os.path.join(base_path, '**', '*.json')
            files = glob(pattern, recursive=True)
            
            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if 'eep' in data:
                            self.profiles[data['eep']] = EEPProfile(data)
                            count += 1
                except Exception as e:
                    logger.error(f"Error loading EEP from {file_path}: {e}")
        
        logger.info(f"Loaded total {len(self.profiles)} unique EEP profiles")

    def get_profile(self, eep_name):
        return self.profiles.get(eep_name)

    def list_profiles(self):
        result = []
        for p in self.profiles.values():
            result.append({'eep': p.eep, 'title': p.title, 'rorg': p.rorg})
        return result
