# EnOcean MQTT Slim

A lightweight, user-friendly EnOcean to MQTT bridge for Home Assistant with a built-in web UI for device management.

## Features

- ✅ **Zero Configuration Files** - Everything managed through web UI
- ✅ **150+ Built-in EEP Profiles** - Including Kessel Staufix Control (MV-01-01)
- ✅ **Auto-Discovery** - Teach-in mode with automatic device detection
- ✅ **Web-Based Management** - Add, edit, and monitor devices via browser
- ✅ **MQTT Auto-Discovery** - Entities appear automatically in Home Assistant
- ✅ **Better USB Communication** - Direct Python serial implementation
- ✅ **MIT Licensed** - Free for commercial and personal use

## Installation

1. Add this repository to your Home Assistant Add-on Store
2. Install the "EnOcean MQTT Slim" addon
3. Configure your serial port in the Configuration tab
4. Start the addon
5. Click "Open Web UI" to manage devices

## Configuration

### Serial Port

Select your EnOcean USB stick from the dropdown. Common paths:
- `/dev/ttyUSB0`
- `/dev/ttyAMA0`
- `/dev/serial/by-id/usb-EnOcean_...`

If you don't see your device, check **Settings → System → Hardware** in Home Assistant.

### Log Level

Choose the logging verbosity:
- `debug` - Detailed debugging information
- `info` - General information (recommended)
- `warning` - Only warnings and errors
- `error` - Only errors

## Usage

### Adding Your First Device

1. Click **"Open Web UI"** in the addon page
2. Click **"Add Device"**
3. Choose one of two methods:

#### Method 1: Teach-In Mode (Recommended)
1. Click **"Start Teach-In"**
2. Trigger your EnOcean device (press button, etc.)
3. Device is automatically detected!
4. Confirm the device name and save

#### Method 2: Manual Entry
1. Enter the device ID (e.g., `05834fa4`)
2. Enter a friendly name
3. Select the EEP profile from the dropdown
4. Click **"Save Device"**

### Supported Devices

This addon includes 150+ EEP profiles for various EnOcean devices:

- **Kessel Staufix Control** (MV-01-01) - Backwater alarm
- **Temperature Sensors** (A5-02-xx)
- **Rocker Switches** (F6-02-xx)
- **Occupancy Sensors** (A5-07-xx)
- **Window Contacts** (D5-00-01)
- **LED Controllers** (D2-01-xx)
- And many more...

### Example: Kessel Staufix Control

The Kessel Staufix Control backwater alarm is fully supported:

1. Add device via teach-in or manual entry
2. Device ID: Your device's EnOcean ID (e.g., `05834fa4`)
3. EEP Profile: MV-01-01 (Kessel Staufix Control)
4. Entity Created: `binary_sensor.staufix_control_alarm`
5. Device Class: `problem` (shows as alert in HA)

The alarm entity will automatically update when water is detected!

## Web UI Features

### Dashboard
- View all devices at a glance
- See online/offline status
- Monitor signal strength (RSSI)
- Quick access to device actions

### Device Management
- **Teach-In Mode** - Automatic device detection
- **Manual Entry** - Add devices by ID
- **Edit Devices** - Change names, EEP profiles
- **Delete Devices** - Remove unwanted devices

### EEP Browser
- Browse 150+ built-in profiles
- Search by name or EEP code
- View profile details

### Settings
- Gateway information
- Serial port configuration
- MQTT status
- System diagnostics

## Troubleshooting

### Device Not Detected

1. Check serial port is correct
2. Ensure USB stick is connected
3. Try teach-in mode again
4. Check addon logs

### Entities Not Appearing in HA

1. Verify MQTT broker is running (Mosquitto addon)
2. Check MQTT integration is configured
3. Restart Home Assistant
4. Check web UI shows device as online

### USB Stick Not Found

1. Go to **Settings → System → Hardware**
2. Find your EnOcean USB stick path
3. Update serial port in addon configuration
4. Restart addon

### Addon Won't Start

1. Check the addon logs for errors
2. Verify MQTT broker is running
3. Ensure serial port path is correct
4. Try removing and re-adding the addon

## Support

For issues and feature requests:
- GitHub Issues: https://github.com/ESDN83/ha-enocean-mqtt-slim/issues
- Home Assistant Community Forum

## Credits

- EEP profile structure inspired by [ioBroker.enocean](https://github.com/Jey-Cee/ioBroker.enocean)
- Built for the Home Assistant community
- Developed by ESDN83

## License

MIT License - See repository for details
