from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from ..commands import TimeCommands
from ..devicebase import DeviceBase
from ..packet import Packet


class UnsupportedDevice(DeviceBase):
    collecting_data: str = "connecting"

    @property
    def NAME_PREFIX(self):
        return f"u-EF-{self._sn[:2]}"

    def __init__(
        self, ble_dev: BLEDevice, adv_data: AdvertisementData, sn: str
    ) -> None:
        super().__init__(ble_dev, adv_data, sn)
        self._time_commands = TimeCommands(self)
        self._diagnostics.enabled()

    @classmethod
    def check(cls, sn: bytes) -> bool:
        return True

    @property
    def device(self):
        return f"[Unsupported] EF-{self._sn[:4]}"

    @property
    def packet_version(self):
        return 0x03

    def with_update_period(self, period: int):
        # NOTE(gnox): as unsupported devices do not have any sensors, we leave update
        # period to default, otherwise collection sensor would lag
        return self

    async def packet_parse(self, data: bytes) -> Packet:
        self.collecting_data = "collecting"

        if self._diagnostics.packet_target_reached:
            self.collecting_data = "done"
        else:
            self.collecting_data = f"{self._diagnostics.packets_collected}/{self._diagnostics.packet_buffer_size}"

        packet = Packet.fromBytes(data)
        if Packet.is_invalid(packet):
            self.collecting_data = "error"

        self.update_callback("collecting_data")
        return packet

    async def data_parse(self, packet: Packet) -> bool:
        processed = False

        if (
            packet.src == 0x35
            and packet.cmdSet == 0x01
            and packet.cmdId == Packet.NET_BLE_COMMAND_CMD_SET_RET_TIME
        ):
            if len(packet.payload) == 0:
                self._time_commands.async_send_all()
            processed = True

        return processed
