#!/usr/bin/env bash

# --- 1. Umgebungserkennung & Bashio laden ---

# WICHTIG: Wir müssen bashio 'sourcen', damit Funktionen wie bashio::config verfügbar sind.
if [ -f "/usr/lib/bashio/bashio" ]; then
    source /usr/lib/bashio/bashio
    MODE="HA"
elif [ -f "/usr/bin/bashio" ]; then
    source /usr/bin/bashio
    MODE="HA"
else
    # Fallback für Standalone
    MODE="STANDALONE"
fi

# Logging Wrapper
log_info() {
    if [ "$MODE" = "HA" ] && command -v bashio::log.info >/dev/null 2>&1; then
        bashio::log.info "$@"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $@"
    fi
}

log_warn() {
    if [ "$MODE" = "HA" ] && command -v bashio::log.warning >/dev/null 2>&1; then
        bashio::log.warning "$@"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') [WARN] $@"
    fi
}

# Config Helper
ha_config() {
    if [ "$MODE" = "HA" ] && command -v bashio::config >/dev/null 2>&1; then
        if bashio::config.has_value "$1"; then
            bashio::config "$1"
        fi
    fi
}

# Service Helper
ha_service() {
    if [ "$MODE" = "HA" ] && command -v bashio::services >/dev/null 2>&1; then
        bashio::services "$1" "$2"
    fi
}


# --- 2. Konfiguration laden ---

log_info "Starting Add-on in $MODE mode..."

# A) Ziel-Schnittstelle (Serial/TCP) bestimmen
# Priorität: 1. ENV (Standalone) -> 2. HA Config (TCP) -> 3. HA Config (Serial)

# Werte aus HA holen (falls möglich)
HA_TCP=$(ha_config 'tcp_address')
HA_SERIAL=$(ha_config 'serial_device')

if [ -n "$SERIAL_PORT" ]; then
    TARGET_PORT="$SERIAL_PORT"
    log_info "Configuration: Using ENV variable SERIAL_PORT."
elif [ -n "$HA_TCP" ]; then
    log_info "Configuration: Using TCP Address from HA Add-on config."
    TARGET_PORT="$HA_TCP"
elif [ -n "$HA_SERIAL" ] && [ "$HA_SERIAL" != "null" ]; then
    log_info "Configuration: Using Serial Device from HA Add-on config."
    TARGET_PORT="$HA_SERIAL"
else
    log_warn "No connection configured! Defaulting to /dev/ttyUSB0"
    TARGET_PORT="/dev/ttyUSB0"
fi


# B) Log Level
# Hier fehlte vorher der Fallback, falls bashio fehlschlägt
HA_LOG=$(ha_config 'log_level')
if [ -n "$HA_LOG" ]; then
    LOG_LEVEL="$HA_LOG"
elif [ -z "$LOG_LEVEL" ]; then
    LOG_LEVEL="info"
fi


# C) Version
if [ -z "$ADDON_VERSION" ]; then
    if [ "$MODE" = "HA" ] && command -v bashio::addon.version >/dev/null 2>&1; then
        ADDON_VERSION="$(bashio::addon.version)"
    else
        ADDON_VERSION="standalone-dev"
    fi
fi
log_info "Add-on Version: ${ADDON_VERSION}"


# D) MQTT Credentials
if [ -z "$MQTT_HOST" ]; then
    MQTT_HOST=$(ha_service mqtt "host")
    MQTT_PORT=$(ha_service mqtt "port")
    MQTT_USER=$(ha_service mqtt "username")
    MQTT_PASSWORD=$(ha_service mqtt "password")
fi

# E) Sonstiges
if [ -z "$RESTORE_STATE" ]; then RESTORE_STATE=$(ha_config 'restore_state'); fi
if [ -z "$RESTORE_DELAY" ]; then RESTORE_DELAY=$(ha_config 'restore_delay'); fi


# --- 3. Export & Start ---

export ADDON_VERSION
export SERIAL_PORT="$TARGET_PORT"
export LOG_LEVEL
export MQTT_HOST
export MQTT_PORT
export MQTT_USER
export MQTT_PASSWORD
export RESTORE_STATE
export RESTORE_DELAY

log_info "Target Interface: ${SERIAL_PORT}"
log_info "Log Level: ${LOG_LEVEL}"

cd /app
exec python3 main.py
