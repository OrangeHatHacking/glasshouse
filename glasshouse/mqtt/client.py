"""
Optional MQTT publisher using TLS 1.3. Disabled by default.

Reads config from the encrypted settings DB on each detection event.
Reconnects automatically if the broker drops.

Payload format (matches OUI-SPY for Home Assistant compatibility):
  {"mac": "AA:BB:CC:DD:EE:FF", "vendor": "Axon", "alias": "...", "rssi": -65,
   "match_type": "composite", "category": "bodycam"}
"""

import asyncio
import json
import logging
import ssl

log = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt_lib

    _MQTT_AVAILABLE = True
except ImportError:
    _MQTT_AVAILABLE = False
    log.debug("paho-mqtt not installed - MQTT disabled")


class MQTTClient:
    def __init__(self):
        self._client: object | None = None
        self._connected = False
        self._config: dict = {}

    def _load_config_sync(self) -> dict:
        """Read settings from the database."""
        # Import here to avoid circular at module load
        from glasshouse.storage.db import _get_setting_sync

        return {
            "enabled": _get_setting_sync("mqtt_enabled") == "1",
            "broker": _get_setting_sync("mqtt_broker") or "",
            "port": int(_get_setting_sync("mqtt_port") or 1883),
            "user": _get_setting_sync("mqtt_user") or "",
            "password": _get_setting_sync("mqtt_password") or "",
            "topic": _get_setting_sync("mqtt_topic") or "glasshouse/detection",
            "tls": _get_setting_sync("mqtt_tls") == "1",
        }

    async def _load_config(self) -> dict:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._load_config_sync)

    def _connect_sync(self, config: dict) -> None:
        if not _MQTT_AVAILABLE:
            return
        client = mqtt_lib.Client(client_id="glasshouse", clean_session=True)
        if config["user"]:
            client.username_pw_set(config["user"], config["password"])
        if config["tls"]:
            ctx = ssl.create_default_context()
            ctx.minimum_version = ssl.TLSVersion.TLSv1_3
            client.tls_set_context(ctx)

        def on_connect(c, userdata, flags, rc):
            if rc == 0:
                self._connected = True
                log.info("MQTT connected to %s:%s", config["broker"], config["port"])
            else:
                log.warning("MQTT connection failed: rc=%s", rc)

        def on_disconnect(c, userdata, rc):
            self._connected = False
            log.warning("MQTT disconnected: rc=%s", rc)

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.connect(config["broker"], config["port"], keepalive=120)
        client.loop_start()
        self._client = client

    async def connect(self) -> None:
        config = await self._load_config()
        if not config["enabled"] or not config["broker"]:
            return
        self._config = config
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._connect_sync, config)

    async def publish(self, event: dict) -> None:
        if not self._connected or not self._client:
            return
        payload = json.dumps(
            {
                "mac": event.get("mac"),
                "vendor": event.get("vendor"),
                "alias": event.get("alias"),
                "rssi": event.get("rssi"),
                "match_type": event.get("match_type"),
                "category": event.get("category"),
            }
        )
        topic = self._config.get("topic", "glasshouse/detection")
        try:
            self._client.publish(topic, payload, qos=1)
        except Exception as e:
            log.warning("MQTT publish failed: %s", e)

    async def on_detection(self, event: dict) -> None:
        """Publish a detection event, reconnecting if needed."""
        if not _MQTT_AVAILABLE:
            return
        config = await self._load_config()
        if not config["enabled"]:
            return
        if not self._connected:
            await self.connect()
        await self.publish(event)

    def disconnect(self) -> None:
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass


# Module-level singleton
_client = MQTTClient()


async def on_detection(event: dict) -> None:
    await _client.on_detection(event)


def disconnect() -> None:
    _client.disconnect()
