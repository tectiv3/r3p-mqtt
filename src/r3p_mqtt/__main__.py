import asyncio
import logging
import sys
import time
from pathlib import Path

from .config import Config
from .eflib import NewDevice
from .eflib.connection import ConnectionState
from .mqtt import PUBLISH_FIELDS, MqttPublisher
from .scanner import discover_device

log = logging.getLogger("r3p_mqtt")

DATA_TIMEOUT = 60.0
MQTT_RECONNECT_INTERVAL = 30.0

_last_status_hash = None


def log_device_status(device) -> None:
    """Print current device status to log, only when values change."""
    global _last_status_hash
    values = []
    for field_name in PUBLISH_FIELDS:
        value = getattr(device, field_name, None)
        if value is not None:
            values.append(f"{field_name}={value}")
    if not values:
        return
    h = hash(tuple(values))
    if h == _last_status_hash:
        return
    _last_status_hash = h
    log.debug("Device status: %s", ", ".join(values))


async def disconnect_stale_bluez(target_address: str | None = None) -> None:
    """Force-disconnect stale BlueZ connections to EcoFlow devices."""
    if sys.platform != "linux":
        return
    try:
        proc = await asyncio.create_subprocess_exec(
            "bluetoothctl",
            "devices",
            "Connected",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        for line in stdout.decode().strip().splitlines():
            parts = line.split(maxsplit=2)
            if len(parts) < 3:
                continue
            addr, name = parts[1], parts[2]
            if not (addr == target_address or name.startswith("EF-")):
                continue
            log.info("Cleaning up stale BlueZ connection: %s (%s)", name, addr)
            dc = await asyncio.create_subprocess_exec(
                "bluetoothctl",
                "disconnect",
                addr,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(dc.communicate(), timeout=5)
    except FileNotFoundError:
        log.debug("bluetoothctl not found, skipping stale connection cleanup")
    except Exception as e:
        log.debug("BlueZ cleanup failed: %s", e)


async def connect_mqtt(config: Config) -> MqttPublisher | None:
    mqtt = MqttPublisher(config.mqtt)
    try:
        await mqtt.connect()
        return mqtt
    except Exception as e:
        log.warning("MQTT unavailable (%s), running without MQTT", e)
        return None


async def run(config: Config) -> None:
    mqtt = await connect_mqtt(config)
    last_known_address: str | None = None

    backoff = 1.0
    try:
        while True:
            await disconnect_stale_bluez(last_known_address)

            log.info("Scanning for River 3 Plus...")
            result = await discover_device(
                target_serial=config.device_serial,
                timeout=30.0,
            )
            if result is None:
                log.warning("Device not found, retrying in %.0fs...", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
                continue

            ble_dev, adv_data = result
            last_known_address = ble_dev.address
            device = NewDevice(ble_dev, adv_data)
            if device is None:
                log.error("Failed to create device instance")
                continue

            backoff = 1.0
            device.with_update_period(int(config.publish_interval))
            log.info("Connecting to %s...", device.serial_number)

            disconnected = asyncio.Event()
            last_data_time = time.monotonic()

            def on_disconnect(exc=None):
                if exc:
                    log.warning("BLE disconnected: %s", exc)
                else:
                    log.info("BLE disconnected")
                disconnected.set()

            def on_state_change(state: ConnectionState):
                log.info("Connection state: %s", state.name)

            device.on_disconnect(on_disconnect)
            device.on_connection_state_change(on_state_change)

            def on_update():
                nonlocal last_data_time
                last_data_time = time.monotonic()
                log_device_status(device)
                if mqtt and mqtt.is_connected:
                    asyncio.create_task(mqtt.publish_changed(device))

            device.register_callback(on_update)

            async def watchdog():
                """Detect silent BLE death and force reconnect."""
                nonlocal mqtt
                while not disconnected.is_set():
                    await asyncio.sleep(DATA_TIMEOUT / 2)
                    silence = time.monotonic() - last_data_time
                    if silence > DATA_TIMEOUT:
                        log.warning(
                            "No BLE data for %.0fs, forcing reconnect",
                            silence,
                        )
                        disconnected.set()
                        return
                    # Reconnect MQTT if it dropped during a stable BLE session
                    if mqtt is not None and not mqtt.is_connected:
                        log.info("MQTT disconnected, attempting reconnect...")
                        mqtt = await connect_mqtt(config)
                    elif mqtt is None:
                        mqtt = await connect_mqtt(config)

            try:
                await device.connect(user_id=config.user_id)
                await device.wait_connected(timeout=30)
                log.info("Authenticated with %s", device.serial_number)

                if mqtt is None:
                    mqtt = await connect_mqtt(config)

                watchdog_task = asyncio.create_task(watchdog())
                try:
                    await disconnected.wait()
                finally:
                    watchdog_task.cancel()
            except Exception as e:
                log.error("Connection failed: %s", e)
            finally:
                try:
                    await device.disconnect()
                except Exception:
                    pass

            log.info("Reconnecting in %.0fs...", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
    finally:
        if mqtt:
            await mqtt.disconnect()
        log.info("Shutdown complete")


def main() -> None:
    config_path = Path("config.json")
    if not config_path.exists():
        print(f"Error: {config_path} not found", file=sys.stderr)
        sys.exit(1)

    config = Config.load(config_path)
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        asyncio.run(run(config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
