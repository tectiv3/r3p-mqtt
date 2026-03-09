import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MqttConfig:
    host: str = "localhost"
    port: int = 1883
    username: str | None = None
    password: str | None = None
    topic_prefix: str = "ecoflow/r3p"


@dataclass(frozen=True)
class Config:
    user_id: str
    device_serial: str | None = None
    mqtt: MqttConfig = MqttConfig()
    log_level: str = "INFO"
    publish_interval: float = 1.0

    @staticmethod
    def load(path: Path) -> "Config":
        data = json.loads(path.read_text())
        mqtt_data = data.get("mqtt", {})
        return Config(
            user_id=data["user_id"],
            device_serial=data.get("device_serial"),
            mqtt=MqttConfig(**mqtt_data),
            log_level=data.get("log_level", "INFO"),
            publish_interval=data.get("publish_interval", 1.0),
        )
