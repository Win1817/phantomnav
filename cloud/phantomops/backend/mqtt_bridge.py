"""
PhantomOps™ — MQTT Bridge
Subscribes to all phantom/{id}/* topics and relays to WebSocket clients.
Also provides publish capability for commands/missions.
"""

import asyncio
import aiomqtt
import json
import logging
import time
from typing import Optional
from ws_manager import ConnectionManager

log = logging.getLogger("phantomops.mqtt")

# In-memory cache of latest state per drone
_drone_cache: dict = {}


class MQTTBridge:
    """
    Persistent async MQTT subscriber.
    Reconnects automatically on disconnect.
    Relays all phantom/* messages to WebSocket clients.
    """

    def __init__(self, host: str, port: int, ws_manager: ConnectionManager):
        self.host = host
        self.port = port
        self.ws_manager = ws_manager
        self.connected = False
        self.messages_relayed = 0
        self._client: Optional[aiomqtt.Client] = None
        self._publish_queue: asyncio.Queue = asyncio.Queue()

    async def run(self):
        """Main loop — reconnects on failure."""
        retry_delay = 5
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=self.host,
                    port=self.port,
                ) as client:
                    self._client = client
                    self.connected = True
                    log.info(f"MQTT bridge connected to {self.host}:{self.port}")

                    # Subscribe to all PhantomNav topics
                    await client.subscribe("phantom/+/telemetry",  qos=0)
                    await client.subscribe("phantom/+/confidence", qos=0)
                    await client.subscribe("phantom/+/status",     qos=1)
                    await client.subscribe("phantom/+/alerts",     qos=1)

                    await self.ws_manager.send_system("mqtt_connected", {
                        "broker": f"{self.host}:{self.port}"
                    })

                    # Process incoming + outgoing concurrently
                    await asyncio.gather(
                        self._ingest_loop(client),
                        self._publish_loop(client),
                    )

            except Exception as e:
                self.connected = False
                self._client = None
                log.warning(f"MQTT bridge disconnected: {e}. Retrying in {retry_delay}s...")
                await self.ws_manager.send_system("mqtt_disconnected", {"reason": str(e)})
                await asyncio.sleep(retry_delay)

    async def _ingest_loop(self, client: aiomqtt.Client):
        """Process all incoming MQTT messages."""
        async for message in client.messages:
            try:
                topic = str(message.topic)
                parts = topic.split("/")  # phantom/{drone_id}/{msg_type}
                if len(parts) < 3:
                    continue

                drone_id = parts[1]
                msg_type = parts[2]
                payload  = json.loads(message.payload.decode())

                # Update in-memory cache
                if drone_id not in _drone_cache:
                    _drone_cache[drone_id] = {"drone_id": drone_id, "first_seen": time.time()}
                _drone_cache[drone_id]["last_seen"] = time.time()

                if msg_type == "telemetry":
                    _drone_cache[drone_id]["telemetry"]   = payload
                    _drone_cache[drone_id]["gnss_valid"]  = payload.get("gnss_valid", False)
                elif msg_type == "confidence":
                    _drone_cache[drone_id]["confidence"]  = payload.get("score", 0)
                    _drone_cache[drone_id]["conf_level"]  = payload.get("level", "")
                    _drone_cache[drone_id]["sub_scores"]  = payload.get("sub_scores", {})
                elif msg_type == "status":
                    _drone_cache[drone_id]["nav_mode"]    = payload.get("nav_mode_name", "")
                    _drone_cache[drone_id]["gnss_avail"]  = payload.get("gnss_available", False)
                    _drone_cache[drone_id]["slam_avail"]  = payload.get("slam_available", False)

                # Relay to WebSocket subscribers
                await self.ws_manager.broadcast(drone_id, f"phantom_{msg_type}", payload)
                self.messages_relayed += 1

            except Exception as e:
                log.debug(f"MQTT ingest error: {e}")

    async def _publish_loop(self, client: aiomqtt.Client):
        """Drain the outbound publish queue."""
        while True:
            topic, payload, qos = await self._publish_queue.get()
            try:
                await client.publish(topic, json.dumps(payload), qos=qos)
                log.info(f"MQTT published → {topic}")
            except Exception as e:
                log.warning(f"MQTT publish failed: {e}")

    async def publish(self, topic: str, payload: dict, qos: int = 1):
        """Enqueue a message for publishing (non-blocking)."""
        await self._publish_queue.put((topic, payload, qos))

    async def send_command(self, drone_id: str, command: dict):
        await self.publish(f"phantom/{drone_id}/command", command, qos=1)

    async def send_mission(self, drone_id: str, mission: dict):
        await self.publish(f"phantom/{drone_id}/mission", mission, qos=1)


def get_drone_cache() -> dict:
    """Return the in-memory drone state cache."""
    return _drone_cache


def get_drone_state(drone_id: str) -> Optional[dict]:
    return _drone_cache.get(drone_id)
