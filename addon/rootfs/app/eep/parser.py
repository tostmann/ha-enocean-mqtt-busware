import logging
import struct

logger = logging.getLogger(__name__)

class EEPParser:
    def __init__(self):
        pass

    def _get_profile_data(self, profile):
        """Helper to extract dict data from profile object or dict"""
        if isinstance(profile, dict):
            return profile
        if hasattr(profile, 'data'):
            return profile.data
        if hasattr(profile, 'config'):
            return profile.config
        try: return profile.__dict__
        except: return {}

    def parse_telegram_with_full_data(self, data, profile):
        if not profile: return None
        
        # --- FIX HIER ---
        profile_data = self._get_profile_data(profile)
        # ----------------
        
        rorg = data[0]
        eep_name = profile_data.get('eep', 'Unknown')
        logger.info(f"📊 Parsing telegram with profile {eep_name}")
        
        matched_case = None
        raw_val = 0
        status_byte = data[-1]
        
        if rorg == 0xF6:
            raw_val = data[1]
            logger.info(f"RPS (F6) Data Byte: {hex(raw_val)}")
        elif rorg == 0xD5:
            raw_val = data[1]
            logger.info(f"1BS (D5) Data Byte: {hex(raw_val)}")
        else:
            raw_val = int.from_bytes(data[1:5], 'big')
            logger.info(f"4BS (A5) Data Bytes: {data[1:5].hex()}")

        for case in profile_data.get('case', []):
            match = True
            if 'data' in case:
                if int(case['data'], 16) != raw_val: match = False
            if match and 'status' in case:
                if int(case['status'], 16) != status_byte: match = False
            if match:
                matched_case = case
                break
        
        if not matched_case:
            logger.info(f"No matching case found for Data={hex(raw_val)}")
            return {}

        result = {}
        for field in matched_case.get('datafield', []):
            shortcut = field.get('shortcut')
            value = field.get('value')
            if shortcut and value is not None:
                try:
                    if "." in str(value): result[shortcut] = float(value)
                    else: result[shortcut] = int(value)
                except: result[shortcut] = value

        logger.info(f"Parsed result: {result}")
        return result
