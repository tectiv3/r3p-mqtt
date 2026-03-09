# R3P MQTT Daemon Design

## Goal

Standalone Python daemon that connects to an EcoFlow River 3 Plus over BLE and publishes telemetry to MQTT (Mosquitto). Read-only for now — no command sending.

## Approach

Extract the protocol implementation from [ha-ef-ble](https://github.com/rabits/ha-ef-ble) (`eflib/`), strip Home Assistant dependencies, wrap in an asyncio daemon with MQTT publishing.

## Config

`config.json` at project root:

```json
{
  "user_id": "",
  "device_serial": "",
  "mqtt": {
    "host": "localhost",
    "port": 1883
  }
}
```

## Architecture

```
r3p-mqtt daemon (asyncio)
├── BLE Scanner (bleak) — discovers device via manufacturer ID 0xB5B5
├── Protocol Client (eflib) — ECDH auth, AES encryption, protobuf parsing
└── MQTT Publisher (aiomqtt) — flat topics to Mosquitto
```

## Project Structure

```
r3p-mqtt/
├── config.json
├── pyproject.toml
├── src/
│   └── r3p_mqtt/
│       ├── __main__.py        # daemon entry point
│       ├── config.py          # load config.json
│       ├── scanner.py         # BLE discovery
│       ├── mqtt.py            # MQTT publish logic
│       └── eflib/             # extracted from ha-ef-ble
│           ├── connection.py  # BLE auth + encryption
│           ├── packet.py      # inner packet framing
│           ├── encpacket.py   # outer encrypted packet
│           ├── crc.py         # CRC8/CRC16
│           ├── keydata.py     # key derivation data
│           ├── river3plus.py  # R3P device + protobuf parsing
│           └── proto/
│               └── pr705_pb2.py
```

## Dependencies

Managed with `uv`. Python 3.13+.

- bleak — BLE communication
- bleak-retry-connector — connection resilience
- ecdsa — ECDH key exchange (SECP160r1)
- pycryptodome — AES-128-CBC encryption
- protobuf — protobuf message parsing
- crc — CRC8/CRC16 checksums
- aiomqtt — async MQTT client

## BLE Protocol

### Discovery
- Scan for manufacturer ID `0xB5B5`
- Match serial prefix: R631, R634, R635

### Authentication (3-stage)
1. ECDH key exchange (SECP160r1) → shared secret → IV = MD5(shared_key)
2. Device sends sRand + seed → session key derived via keydata + MD5
3. HMAC-MD5 auth: MD5(user_id + serial_number) sent to device

### Packet Structure
- Outer: `0x5a5a` prefix, AES-128-CBC encrypted, CRC16
- Inner: `0xaa` prefix, version byte, src/dst/cmdSet/cmdId, protobuf payload, CRC16
- River 3 payloads XOR'd with seq[0]

### Characteristics
- Write: `00000002-0000-1000-8000-00805f9b34fb`
- Notify: `00000003-0000-1000-8000-00805f9b34fb`

## MQTT Topics

All published under `ecoflow/r3p/` with retain flag:

| Topic | Type | Description |
|-------|------|-------------|
| `status` | string | online/offline (LWT) |
| `battery_level` | int | 0-100% |
| `ac_input_power` | float | watts |
| `ac_output_power` | float | watts |
| `dc_input_power` | float | solar/DC watts |
| `dc12v_output_power` | float | watts |
| `usba_output_power` | float | watts |
| `usbc_output_power` | float | watts |
| `cell_temperature` | float | °C |
| `plugged_in_ac` | bool | AC charger connected |
| `energy_backup` | bool | backup mode active |
| `fault` | json | fault event payload |

## Daemon Behavior

1. Load config.json
2. Connect to Mosquitto, register LWT (status → offline)
3. BLE scan for device
4. Authenticate via 3-stage handshake
5. Subscribe to BLE notifications (char 0x0003)
6. On notification: decrypt → parse protobuf → publish changed values
7. On BLE disconnect: exponential backoff reconnect (1s → 60s max)

Dedup: only publish values that changed since last update.
Logging: Python logging to stderr, level configurable via config.

## References

- ha-ef-ble: https://github.com/rabits/ha-ef-ble
- r3pcomms: https://github.com/greyltc/r3pcomms
- Protobuf definition: pr705.proto
