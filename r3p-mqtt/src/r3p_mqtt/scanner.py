import asyncio
import logging

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .eflib import NewDevice, sn_from_advertisement, DeviceBase

log = logging.getLogger(__name__)

MANUFACTURER_KEY = 0xB5B5


async def discover_device(
    target_serial: str | None = None,
    timeout: float = 30.0,
) -> tuple[BLEDevice, AdvertisementData] | None:
    """Scan for EcoFlow River 3 Plus device."""
    found: asyncio.Future[tuple[BLEDevice, AdvertisementData]] = asyncio.get_event_loop().create_future()

    def on_detection(device: BLEDevice, adv_data: AdvertisementData) -> None:
        if found.done():
            return
        sn = sn_from_advertisement(adv_data)
        if sn is None:
            return
        sn_str = sn.decode("ascii", errors="ignore")
        if target_serial and sn_str != target_serial:
            return
        # Only accept River 3 Plus prefixes
        if not sn_str.startswith(("R631", "R634", "R635")):
            log.debug("Skipping non-R3P device: %s", sn_str)
            return
        log.info("Found River 3 Plus: %s (%s)", sn_str, device.address)
        found.set_result((device, adv_data))

    scanner = BleakScanner(detection_callback=on_detection)
    await scanner.start()
    try:
        return await asyncio.wait_for(asyncio.shield(found), timeout=timeout)
    except TimeoutError:
        log.warning("BLE scan timed out after %.0fs", timeout)
        return None
    finally:
        await scanner.stop()
