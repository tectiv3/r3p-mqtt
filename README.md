# r3p-mqtt

A Python daemon that connects to an EcoFlow River 3 Plus over BLE and publishes telemetry to MQTT.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Bluetooth adapter (the host must be within BLE range of the device)
- MQTT broker (e.g. Mosquitto)

## Setup

```bash
git clone <repo-url>
cd r3p-mqtt
uv sync
cp config.example.json config.json
```

Edit `config.json`:

```json
{
  "user_id": "YOUR_ECOFLOW_USER_ID",
  "device_serial": "YOUR_DEVICE_SERIAL",
  "mqtt": {
    "host": "localhost",
    "port": 1883,
    "username": null,
    "password": null
  },
  "log_level": "INFO"
}
```

- `user_id` — your EcoFlow account user ID
- `device_serial` — serial number of the device or omit to connect to the first River 3 Plus found
- `log_level` — `INFO` for normal operation, `DEBUG` for telemetry logging

## Usage

```bash
uv run r3p-mqtt
```

The daemon will:
1. Scan for the River 3 Plus via BLE
2. Connect and authenticate
3. Publish telemetry to MQTT as values change
4. Reconnect automatically on disconnect (exponential backoff)

Ctrl+C for clean shutdown.

## MQTT Topics

All topics are under `ecoflow/r3p/` (configurable via `mqtt.topic_prefix`), retained, and only published on change.

| Topic | Type | Description |
|-------|------|-------------|
| `status` | string | `online` / `offline` (LWT) |
| `battery_level` | int | Battery percentage |
| `ac_input_power` | float | AC input power (W) |
| `ac_output_power` | float | AC output power (W) |
| `dc_input_power` | float | DC input power (W) |
| `dc12v_output_power` | float | 12V DC output power (W) |
| `usba_output_power` | float | USB-A output power (W) |
| `usbc_output_power` | float | USB-C output power (W) |
| `input_power` | float | Total input power (W) |
| `output_power` | float | Total output power (W) |
| `cell_temperature` | float | Battery cell temperature (C) |
| `plugged_in_ac` | bool | AC plugged in |
| `energy_backup` | bool | Energy backup mode active |
| `battery_charge_limit_min` | int | Min charge limit (%) |
| `battery_charge_limit_max` | int | Max charge limit (%) |
| `ac_charging_speed` | int | AC charging speed setting |
| `remaining_time_charging` | int | Minutes until full |
| `remaining_time_discharging` | int | Minutes until empty |

Subscribe to all: `mosquitto_sub -t "ecoflow/r3p/#" -v`

## Systemd

```bash
sudo useradd -r -s /usr/sbin/nologin r3pmqtt
sudo usermod -aG bluetooth r3pmqtt
sudo cp r3p-mqtt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now r3p-mqtt
journalctl -u r3p-mqtt -f
```

The service file assumes installation at `/opt/r3p-mqtt`. Edit `r3p-mqtt.service` if your path differs.

## Acknowledgments

BLE protocol implementation extracted from [ha-ef-ble](https://github.com/rabits/ha-ef-ble) by rabits, licensed under Apache 2.0.
