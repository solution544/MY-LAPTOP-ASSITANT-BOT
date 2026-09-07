import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import WebSocket


class LaptopConnection:
    def __init__(
        self,
        device_id: str,
        websocket: WebSocket,
        hostname: Optional[str] = None,
        os_name: Optional[str] = None,
        os_version: Optional[str] = None,
    ):
        self.device_id = device_id
        self.websocket = websocket
        self.hostname = hostname
        self.os_name = os_name
        self.os_version = os_version

        self.connected_at = datetime.now(timezone.utc)
        self.last_seen = self.connected_at

        self.pending_commands = {}


class LaptopManager:
    """
    Manages connected Solution AI laptop agents.

    Responsibilities:
    - Track connected laptops
    - Remove disconnected laptops
    - Send commands to laptops
    - Track pending commands
    - Match command results
    """

    def __init__(self):
        self._connections: dict[str, LaptopConnection] = {}
        self._lock = asyncio.Lock()

    # --------------------------------------------------
    # REGISTER LAPTOP
    # --------------------------------------------------

    async def register(
        self,
        device_id: str,
        websocket: WebSocket,
        hostname: Optional[str] = None,
        os_name: Optional[str] = None,
        os_version: Optional[str] = None,
    ) -> LaptopConnection:

        connection = LaptopConnection(
            device_id=device_id,
            websocket=websocket,
            hostname=hostname,
            os_name=os_name,
            os_version=os_version,
        )

        async with self._lock:
            self._connections[device_id] = connection

        return connection

    # --------------------------------------------------
    # REMOVE LAPTOP
    # --------------------------------------------------

    async def unregister(self, device_id: str):
        async with self._lock:
            self._connections.pop(device_id, None)

    # --------------------------------------------------
    # GET LAPTOP
    # --------------------------------------------------

    async def get(self, device_id: str) -> Optional[LaptopConnection]:
        async with self._lock:
            return self._connections.get(device_id)

    # --------------------------------------------------
    # LIST CONNECTED LAPTOPS
    # --------------------------------------------------

    async def list_connected(self):
        async with self._lock:
            return list(self._connections.values())

    # --------------------------------------------------
    # UPDATE LAST SEEN
    # --------------------------------------------------

    async def update_last_seen(self, device_id: str):
        async with self._lock:
            connection = self._connections.get(device_id)

            if connection:
                connection.last_seen = datetime.now(timezone.utc)

    # --------------------------------------------------
    # SEND COMMAND
    # --------------------------------------------------

    async def send_command(
    self,
    device_id: str,
    command: str,
    arguments: Optional[dict] = None,
) -> str:

        connection = await self.get(device_id)

        if connection is None:
            raise RuntimeError(
                f"Laptop '{device_id}' is not connected."
            )

        command_id = __import__("uuid").uuid4().hex

        payload = {
            "event": "laptop.command",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "command_id": command_id,
            "command": command,
            "arguments": arguments or {},
        }

        await connection.websocket.send_text(
            json.dumps(payload)
        )

        connection.pending_commands[command_id] = {
            "command": command,
            "arguments": arguments or {},
            "sent_at": datetime.now(timezone.utc),
        }

        return command_id

    # --------------------------------------------------
    # COMPLETE COMMAND
    # --------------------------------------------------

    async def complete_command(
        self,
        device_id: str,
        command_id: str,
        result: dict,
    ):
        connection = await self.get(device_id)

        if connection is None:
            return None

        pending = connection.pending_commands.pop(
            command_id,
            None,
        )

        if pending is None:
            return None

        return {
            "command_id": command_id,
            "command": pending["command"],
            "arguments": pending["arguments"],
            "result": result,
        }

    # --------------------------------------------------
    # STATUS
    # --------------------------------------------------

    async def status(self, device_id: str):
        connection = await self.get(device_id)

        if connection is None:
            return {
                "online": False,
                "device_id": device_id,
            }

        return {
            "online": True,
            "device_id": connection.device_id,
            "hostname": connection.hostname,
            "os": connection.os_name,
            "os_version": connection.os_version,
            "connected_at": connection.connected_at.isoformat(),
            "last_seen": connection.last_seen.isoformat(),
            "pending_commands": len(
                connection.pending_commands
            ),
        }


# Global manager used by the backend
laptop_manager = LaptopManager()