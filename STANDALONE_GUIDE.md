```markdown
# Standalone Installation Guide (Docker)

This guide describes how to run the **EnOcean MQTT Gateway** as a standalone Docker container. This setup works independently of the Home Assistant Supervisor and is ideal for users of **Zigbee2MQTT**, **Home Assistant Core**, **OpenHAB**, **ioBroker**, or anyone who prefers a lightweight container solution.

## Prerequisites

* **Docker** installed on your system.
* An **EnOcean Transceiver** (USB Stick e.g. busware.de EUL, or a TCP-Serial-Bridge).

---

## Method 1: Quick Start (Recommended)

Use the pre-built image from Docker Hub. No building or git cloning required.

### A) Using a USB Stick (Standard)
Replace `/dev/ttyUSB0` with the path to your EnOcean stick.

```bash
docker run -d \
  --name enocean-mqtt \
  --restart unless-stopped \
  --device /dev/ttyUSB0:/dev/ttyUSB0 \
  -p 8099:8099 \
  -e SERIAL_PORT=/dev/ttyUSB0 \
  -e MQTT_HOST=192.168.1.100 \
  -e MQTT_PORT=1883 \
  -e MQTT_USER=your_user \
  -e MQTT_PASSWORD=your_password \
  tostmann/enocean-mqtt:latest

```

### B) Using a TCP Bridge (Network)

If your EnOcean transceiver is connected via network (e.g., using `esp3-link` or `ser2net`).

```bash
docker run -d \
  --name enocean-mqtt \
  --restart unless-stopped \
  -p 8099:8099 \
  -e SERIAL_PORT=tcp://192.168.1.50:2000 \
  -e MQTT_HOST=192.168.1.100 \
  -e MQTT_PORT=1883 \
  -e MQTT_USER=your_user \
  -e MQTT_PASSWORD=your_password \
  tostmann/enocean-mqtt:latest

```

---

## Method 2: Build from Source (Advanced)

Use this method if you want to modify the code or build the image locally.

1. **Clone the Repository**
```bash
git clone [https://github.com/tostmann/ha-enocean-mqtt-busware.git](https://github.com/tostmann/ha-enocean-mqtt-busware.git)
cd ha-enocean-mqtt-busware

```


2. **Build the Image**
```bash
docker build -t enocean-local -f Dockerfile.standalone .

```


3. **Run the Container**
```bash
docker run -d \
  --name enocean-mqtt \
  --restart unless-stopped \
  --device /dev/ttyUSB0:/dev/ttyUSB0 \
  -p 8099:8099 \
  -e SERIAL_PORT=/dev/ttyUSB0 \
  -e MQTT_HOST=192.168.1.100 \
  enocean-local

```



---

## Accessing the Dashboard

This standalone version includes a web-based dashboard to manage devices and view logs.

👉 **Open in Browser:** `http://<YOUR_SERVER_IP>:8099`

*(Example: https://www.google.com/search?q=http://192.168.1.10:8099)*

---

## Configuration Reference

The container is configured entirely via Environment Variables (`-e VARIABLE=VALUE`).

| Variable | Description | Default |
| --- | --- | --- |
| `SERIAL_PORT` | Device path (e.g., `/dev/ttyUSB0`) or TCP URL (`tcp://ip:port`) | **Required** |
| `MQTT_HOST` | Hostname or IP of the MQTT Broker | `localhost` |
| `MQTT_PORT` | Port of the MQTT Broker | `1883` |
| `MQTT_USER` | MQTT Username (optional) | - |
| `MQTT_PASSWORD` | MQTT Password (optional) | - |
| `LOG_LEVEL` | Logging verbosity (`INFO`, `DEBUG`, `WARNING`, `ERROR`) | `INFO` |
| `RESTORE_STATE` | Fetch last known device states from MQTT on startup (`true`/`false`) | `true` |
| `TZ` | Timezone for correct log timestamps (e.g., `Europe/Berlin`) | `UTC` |

---

## Troubleshooting

### 1. "Permission denied" on USB Port

If the container crashes or logs show it cannot open `/dev/ttyUSB0`:

* Ensure the host user has permissions (usually group `dialout`).
* **Quick fix:** Run the container with `--privileged` (use with caution).

### 2. Web Interface not reachable

* Check if port `8099` is blocked by a firewall.
* You can map it to a different port: `-p 9000:8099` (Access via port 9000).

### 3. Viewing Logs

To see what the gateway is doing or why it failed to start:

```bash
docker logs -f enocean-mqtt

```

```

```
