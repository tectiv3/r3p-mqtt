from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .devicebase import DeviceBase
from .devices import devices, unsupported

__all__ = ["DeviceBase", "NewDevice", "sn_from_advertisement"]

MANUFACTURER_KEY = 0xB5B5


def sn_from_advertisement(adv_data: AdvertisementData) -> bytes | None:
    if not adv_data.manufacturer_data:
        return None
    data = adv_data.manufacturer_data.get(MANUFACTURER_KEY)
    if data is None:
        return None
    return bytes(data[1:17])


def NewDevice(ble_dev: BLEDevice, adv_data: AdvertisementData) -> DeviceBase | None:
    sn = sn_from_advertisement(adv_data)
    if sn is None:
        return None
    for dev_cls in devices:
        if dev_cls.check(sn):
            return dev_cls(ble_dev, adv_data, sn.decode("ascii"))
    return unsupported.UnsupportedDevice(ble_dev, adv_data, sn.decode("ascii"))
