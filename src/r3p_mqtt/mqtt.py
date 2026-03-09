import json
import logging

import aiomqtt

from .config import MqttConfig

log = logging.getLogger(__name__)

# Fields to publish and their types for JSON serialization
PUBLISH_FIELDS = {
    "battery_level": float,
    "ac_input_power": float,
    "ac_output_power": float,
    "dc_input_power": float,
    "dc12v_output_power": float,
    "usba_output_power": float,
    "usbc_output_power": float,
    "cell_temperature": float,
    "plugged_in_ac": bool,
    "energy_backup": bool,
    "input_power": float,
    "output_power": float,
    "battery_charge_limit_min": int,
    "battery_charge_limit_max": int,
    "ac_charging_speed": int,
    "remaining_time_charging": int,
    "remaining_time_discharging": int,
}


class MqttPublisher:
    def __init__(self, config: MqttConfig) -> None:
        self._config = config
        self._client: aiomqtt.Client | None = None
        self._last_values: dict[str, object] = {}

    async def connect(self) -> None:
        self._client = aiomqtt.Client(
            hostname=self._config.host,
            port=self._config.port,
            username=self._config.username,
            password=self._config.password,
            will=aiomqtt.Will(
                topic=f"{self._config.topic_prefix}/online",
                payload="false",
                retain=True,
            ),
        )
        await self._client.__aenter__()
        await self._client.publish(
            f"{self._config.topic_prefix}/online",
            payload="true",
            retain=True,
        )
        log.info("Connected to MQTT broker at %s:%d", self._config.host, self._config.port)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.publish(
                f"{self._config.topic_prefix}/online",
                payload="false",
                retain=True,
            )
            await self._client.__aexit__(None, None, None)
            self._client = None

    async def publish_changed(self, device) -> None:
        """Publish only fields that changed since last call."""
        if not self._client:
            return
        for field_name, field_type in PUBLISH_FIELDS.items():
            value = getattr(device, field_name, None)
            if value is None:
                continue
            if field_name in self._last_values and self._last_values[field_name] == value:
                continue
            self._last_values[field_name] = value
            topic = f"{self._config.topic_prefix}/{field_name}"
            if field_type is bool:
                payload = "true" if value else "false"
            elif field_type is float:
                payload = f"{value:.2f}"
            else:
                payload = str(value)
            await self._client.publish(topic, payload=payload, retain=True)
            log.debug("Published %s = %s", topic, payload)

    async def publish_fault(self, fault_data: dict) -> None:
        """Publish fault event."""
        if not self._client:
            return
        topic = f"{self._config.topic_prefix}/fault"
        await self._client.publish(topic, payload=json.dumps(fault_data))
        log.warning("Published fault: %s", fault_data)
