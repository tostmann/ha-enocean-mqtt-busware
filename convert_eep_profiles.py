#!/usr/bin/env python3
"""
Smart EEP Downloader & Converter v3
- Lädt EEPs von ioBroker
- Löst 'preDefined' Kürzel (TMP, HUM etc.) in echte Objekte auf
- Setzt korrekte HA Components & Classes
- Behält Beschreibungen bei
"""
import json
import os
import re
import urllib.request
import zipfile
from pathlib import Path

# ==============================================================================
# KONFIGURATION
# ==============================================================================
GITHUB_URL = "https://github.com/Jey-Cee/ioBroker.enocean/archive/refs/heads/master.zip"
ZIP_INTERNAL_PATH = "ioBroker.enocean-master/lib/definitions/eep"
DEST_DIR = Path("addon/rootfs/app/eep/definitions")

# ==============================================================================
# DEFINITIONEN & MAPPINGS
# ==============================================================================

# Auflösung für 'preDefined' Kürzel aus ioBroker
PREDEFINED_MAPPING = {
    "TMP": {
        "name": "Temperature",
        "component": "sensor",
        "device_class": "temperature",
        "unit": "°C",
        "icon": "mdi:thermometer",
        "shortcut": "TMP"
    },
    "HUM": {
        "name": "Humidity",
        "component": "sensor",
        "device_class": "humidity",
        "unit": "%",
        "icon": "mdi:water-percent",
        "shortcut": "HUM"
    },
    "ILLU": {
        "name": "Illuminance",
        "component": "sensor",
        "device_class": "illuminance",
        "unit": "lx",
        "icon": "mdi:brightness-6",
        "shortcut": "ILLU"
    },
    "PIR": {
        "name": "Motion",
        "component": "binary_sensor",
        "device_class": "motion",
        "icon": "mdi:motion-sensor",
        "shortcut": "PIR"
    },
    "WND": {
        "name": "Wind Speed",
        "component": "sensor",
        "device_class": "wind_speed",
        "unit": "m/s",
        "icon": "mdi:weather-windy",
        "shortcut": "WND"
    },
    "SUN": {
        "name": "Solar Radiation",
        "component": "sensor",
        "device_class": "irradiance",
        "unit": "W/m²",
        "icon": "mdi:solar-power",
        "shortcut": "SUN"
    },
    "CO2": {
        "name": "CO2",
        "component": "sensor",
        "device_class": "carbon_dioxide",
        "unit": "ppm",
        "icon": "mdi:molecule-co2",
        "shortcut": "CO2"
    },
    "BTN": {
        "name": "Button",
        "component": "binary_sensor",
        "icon": "mdi:gesture-tap-button",
        "shortcut": "BTN"
    }
}

# Regex für automatische Anreicherung bestehender Objekte
SEMANTIC_MAPPING = [
    (r'(?i)^(tmp|temp|temperature)', {"component": "sensor", "device_class": "temperature", "unit": "°C", "icon": "mdi:thermometer"}),
    (r'(?i)^(hum|humidity)', {"component": "sensor", "device_class": "humidity", "unit": "%", "icon": "mdi:water-percent"}),
    (r'(?i)^(illu|illumination|brightness|light)', {"component": "sensor", "device_class": "illuminance", "unit": "lx", "icon": "mdi:brightness-6"}),
    (r'(?i)^(volt|voltage)', {"component": "sensor", "device_class": "voltage", "unit": "V", "icon": "mdi:lightning-bolt"}),
    (r'(?i)^(curr|current)', {"component": "sensor", "device_class": "current", "unit": "A", "icon": "mdi:current-ac"}),
    (r'(?i)^(pwr|power|energy)', {"component": "sensor", "device_class": "power", "unit": "W", "icon": "mdi:flash"}),
    (r'(?i)^(contact|window|door|closed|open)', {"component": "binary_sensor", "device_class": "window", "icon": "mdi:window-closed"}),
    (r'(?i)^(motion|pir|occ|occupancy)', {"component": "binary_sensor", "device_class": "motion", "icon": "mdi:motion-sensor"}),
    (r'(?i)^(btn|button|sw|switch)', {"component": "binary_sensor", "icon": "mdi:gesture-tap-button"}),
    (r'(?i)^(co2|carbon)', {"component": "sensor", "device_class": "carbon_dioxide", "unit": "ppm", "icon": "mdi:molecule-co2"}),
    (r'(?i)^(rssi|signal)', {"component": "sensor", "device_class": "signal_strength", "unit": "dBm", "icon": "mdi:wifi"})
]

def apply_family_rules(eep_code, obj_key, obj_data):
    """Spezielle Regeln für EEP-Familien"""
    eep = eep_code.upper()
    
    # Rocker Switch
    if eep.startswith("F6-02") or eep.startswith("F6-01"):
        obj_data["component"] = "binary_sensor"
        obj_data["icon"] = "mdi:light-switch"
        return
        
    # Fensterkontakte
    if eep.startswith("D5-00"):
        obj_data["component"] = "binary_sensor"
        if "contact" in obj_key.lower(): obj_data["device_class"] = "window"
        return

    # Fenstergriffe (3 Zustände -> Sensor)
    if eep.startswith("F6-10"):
        if "handle" in obj_key.lower():
            obj_data["component"] = "sensor"
            obj_data["icon"] = "mdi:window-open-variant"
        return
        
    # Aktoren (Switches/Plugs)
    if eep.startswith("D2-01") or eep.startswith("A5-38"):
        # Wenn es nach Output oder Channel klingt -> Switch
        if any(x in obj_key.lower() for x in ['channel', 'output', 'switch', 'relay']):
             obj_data["component"] = "switch"
             obj_data["device_class"] = "outlet"

# ==============================================================================
# LOGIK
# ==============================================================================

def enhance_profile(profile_data):
    """Fügt HA Metadaten hinzu und löst preDefined auf"""
    eep_code = profile_data.get("eep", "UNKNOWN")
    if "objects" not in profile_data: profile_data["objects"] = {}

    # 1. preDefined Auflösung
    # Manche Profile haben nur ["TMP"] in preDefined. Das Addon braucht aber echte Objekte.
    if "preDefined" in profile_data["objects"]:
        pre_def_list = profile_data["objects"]["preDefined"]
        if isinstance(pre_def_list, list):
            for item in pre_def_list:
                # Wenn wir eine Definition dafür haben (z.B. TMP)
                if item in PREDEFINED_MAPPING:
                    # Kopie der Definition erstellen
                    new_obj = PREDEFINED_MAPPING[item].copy()
                    # In objects einfügen, falls noch nicht explizit da
                    if item not in profile_data["objects"]:
                        profile_data["objects"][item] = new_obj
        
        # preDefined entfernen, da es das Addon verwirren könnte (es erwartet Dicts)
        del profile_data["objects"]["preDefined"]

    # 2. Standards hinzufügen (Mit Description!)
    profile_data["objects"]["rssi"] = {
        "name": "RSSI", 
        "component": "sensor", 
        "device_class": "signal_strength", 
        "unit": "dBm", 
        "icon": "mdi:wifi",
        "description": "Signal strength"
    }
    profile_data["objects"]["last_seen"] = {
        "name": "Last Seen", 
        "component": "sensor", 
        "device_class": "timestamp", 
        "icon": "mdi:clock-outline",
        "description": "Last telegram received"
    }

    # 3. Durchlaufe alle Objekte
    # Wir müssen list() nutzen, da wir das Dict während der Iteration verändern könnten
    for obj_key in list(profile_data["objects"].keys()):
        obj_data = profile_data["objects"][obj_key]

        # Sicherheitscheck: Überspringe kaputte Einträge (Listen etc.)
        if not isinstance(obj_data, dict):
            continue

        if obj_key in ["rssi", "last_seen"]: continue
        
        # Regex Matching
        for pattern, attributes in SEMANTIC_MAPPING:
            if re.search(pattern, obj_key):
                for k, v in attributes.items():
                    if k not in obj_data: obj_data[k] = v
                break
        
        # Familien Regeln
        apply_family_rules(eep_code, obj_key, obj_data)
        
        # Fallback
        if "component" not in obj_data:
            obj_data["component"] = "sensor"
            if obj_data.get("unit") == "%": obj_data["icon"] = "mdi:percent"

    return profile_data

def download_and_process():
    print(f"ℹ️  Nutze relatives Zielverzeichnis: {DEST_DIR}")
    print(f"⬇️  Lade Repository von GitHub...\n    {GITHUB_URL}")
    
    try:
        zip_path, _ = urllib.request.urlretrieve(GITHUB_URL)
        
        print("📦 Extrahiere und verarbeite Dateien...")
        count = 0
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for file_info in zip_ref.infolist():
                if file_info.filename.startswith(ZIP_INTERNAL_PATH) and file_info.filename.endswith(".json"):
                    
                    with zip_ref.open(file_info) as f:
                        try:
                            data = json.load(f)
                        except json.JSONDecodeError:
                            print(f"⚠️  Warnung: Defektes JSON in {file_info.filename}")
                            continue

                    try:
                        enhanced_data = enhance_profile(data)
                    except Exception as e:
                        print(f"⚠️  Fehler bei {file_info.filename}: {e}")
                        continue
                    
                    rel_path = file_info.filename.replace(ZIP_INTERNAL_PATH + "/", "")
                    target_file = DEST_DIR / rel_path
                    
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(target_file, 'w', encoding='utf-8') as f:
                        json.dump(enhanced_data, f, indent=2, ensure_ascii=False)
                    
                    count += 1
                    if count % 10 == 0:
                        print(f"   ... {count} Dateien verarbeitet", end="\r")
        
        os.remove(zip_path)
        print(f"\n🎉 Fertig! {count} Profile erfolgreich heruntergeladen und konvertiert.")

    except Exception as e:
        print(f"\n❌ FEHLER: {e}")

if __name__ == "__main__":
    download_and_process()
