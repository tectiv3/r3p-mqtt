import asyncio
import logging
import sys
from pathlib import Path

from .config import Config
from .eflib import NewDevice
from .eflib.connection import ConnectionState
from .mqtt import MqttPublisher
from .scanner import discover_device

log = logging.getLogger("r3p_mqtt")


def log_device_status(device) -> None:
    """Print current device status to log."""
    from .mqtt import PUBLISH_FIELDS

    values = []
    for field_name in PUBLISH_FIELDS:
        value = getattr(device, field_name, None)
        if value is not None:
            values.append(f"{field_name}={value}")
    if values:
        log.info("Device status: %s", ", ".join(values))


async def run(config: Config) -> None:
    mqtt = MqttPublisher(config.mqtt)
    try:
        await mqtt.connect()
    except Exception as e:
        log.warning("MQTT unavailable (%s), running without MQTT", e)
        mqtt = None

    backoff = 1.0
    try:
        while True:
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
            device = NewDevice(ble_dev, adv_data)
            if device is None:
                log.error("Failed to create device instance")
                continue

            backoff = 1.0
            device.with_update_period(int(config.publish_interval))
            log.info("Connecting to %s...", device.serial_number)

            disconnected = asyncio.Event()

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
                log_device_status(device)
                if mqtt:
                    asyncio.ensure_future(mqtt.publish_changed(device))

            device.register_callback(on_update)

            try:
                await device.connect(user_id=config.user_id)
                await device.wait_connected(timeout=30)
                log.info("Authenticated with %s", device.serial_number)
                await disconnected.wait()
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
