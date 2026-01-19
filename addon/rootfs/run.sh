#!/usr/bin/with-contenv bashio

# Configuration loading with priority logic
TCP_ADDR=$(bashio::config 'tcp_address')
SERIAL_DEV=$(bashio::config 'serial_device')

# Logic: TCP Address overrides Serial Device selection
if [ -n "$TCP_ADDR" ]; then
    bashio::log.info "Configuration: Using TCP Address provided in text field."
    SERIAL_PORT="$TCP_ADDR"
elif [ -n "$SERIAL_DEV" ] && [ "$SERIAL_DEV" != "null" ]; then
    bashio::log.info "Configuration: Using selected Serial Device."
    SERIAL_PORT="$SERIAL_DEV"
else
    # Fallback / Error
    bashio::log.warning "No connection configured! Please select a device or enter a TCP address."
    SERIAL_PORT="/dev/ttyUSB0"
fi

LOG_LEVEL=$(bashio::config 'log_level')

# --- NEU: Version automatisch holen ---
ADDON_VERSION="$(bashio::addon.version)"
bashio::log.info "Add-on Version: ${ADDON_VERSION}"

# Export environment variables
export ADDON_VERSION="${ADDON_VERSION}"  # <--- Hier wird sie für Python verfügbar gemacht
export SERIAL_PORT="${SERIAL_PORT}"
export LOG_LEVEL="${LOG_LEVEL}"
export MQTT_HOST=$(bashio::services mqtt "host")
export MQTT_PORT=$(bashio::services mqtt "port")
export MQTT_USER=$(bashio::services mqtt "username")
export MQTT_PASSWORD=$(bashio::services mqtt "password")
export RESTORE_STATE=$(bashio::config 'restore_state')
export RESTORE_DELAY=$(bashio::config 'restore_delay')

# Log startup details
bashio::log.info "Starting EnOcean MQTT Slim..."
bashio::log.info "Target Interface: ${SERIAL_PORT}"
bashio::log.info "Log Level: ${LOG_LEVEL}"

# Start the application
cd /app
exec python3 main.py
