## [1.0.31] - 2026-01-20

### Added
- **Bi-Directional Control (Bi-Di)** - Full support for sending commands to EnOcean actuators
- **Cover Support (Rollläden)** - Native `cover` entities for Blinds/Shutters (Profile D2-05)
  - Supports: Open, Close, Stop, and Position (0-100%)
  - Auto-Inversion: Maps HA 100% (Open) to EnOcean 0% (Open) standard
- **Climate Control** - Support for Thermostats and Valves (A5-10, A5-20)
  - Creates `number` entities for Setpoint temperature and Valve position
  - Allows direct control of heating valves via MQTT
- **Diagnostic Entities** - Cleaned up device view
  - `RSSI`, `Last Seen`, and `Error` signals now marked as `diagnostic`
  - Prevents cluttering the default Home Assistant dashboard
- **Battery Management** - Automatic detection of `device_class: battery` for all sensors

### Improved
- **EEP Converter v8** - Major upgrade to profile generation logic
- **Command Translator** - Extended to handle `cover` and `number` domains
- **Dimmer Logic** - Improved mapping for D2-01 dimmers

## [1.0.30] - 2026-01-20

### Fixed
- **CRITICAL: Data Persistence** - Fixed data loss on Add-on restart
- Moved `devices.json` and downloaded EEP profiles from `/app` (volatile) to `/data` (persistent)
- Devices now survive container updates and reboots
- **Storage Path** - Updated `DeviceManager` and `EEPLoader` to use `/data` as primary storage

### Technical Details
- Previous versions stored data in the application directory which is reset on docker restart
- New architecture ensures `/data` volume is used for all user data
- **Action Required:** Users must re-discover devices one last time to populate the persistent database

## [1.0.29] - 2026-01-19

### Fixed
- **Device ID Handling** - Fixed bug where Device IDs were sometimes treated as Integers instead of Hex Strings
- **Profile Matching** - Improved fuzzy matching for EEP profile names

## [1.0.28] - 2026-01-18

### Added
- **New Switch Profiles** - Added specialized profiles for F6-02-01 Rockers
  - `F6-02-01-Light`: Standard 4-button dimmer/switch
  - `F6-02-01-Scenes`: Scene controller (Cinema, Relax, etc.)
  - `F6-02-01-Switch-2ch`: Toggle switch simulation (keeps state)
  - `F6-02-01-Simple`: Simple Up/Down mapping

### Fixed
- **Binary State Logic** - Enforced `"ON"`/`"OFF"` strings for all binary sensors and switches
- Fixed issue where Home Assistant showed "Unknown" for sensors returning raw `0`/`1`
