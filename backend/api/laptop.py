import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.laptop_manager import laptop_manager
from backend.core.logging import logger


router = APIRouter()


@router.websocket("/ws/laptop")
async def laptop_ws(websocket: WebSocket):
    await websocket.accept()

    device_id = str(uuid.uuid4())

    logger.info(
        f"[LAPTOP AGENT] Connected: {device_id}"
    )

    await websocket.send_text(
        json.dumps(
            {
                "event": "laptop.connected",
                "device_id": device_id,
                "status": "online",
            }
        )
    )

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)

            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps(
                        {
                            "event": "laptop.error",
                            "error": "Malformed JSON.",
                        }
                    )
                )
                continue

            logger.info(
                f"[LAPTOP AGENT] Message: {data}"
            )

            message_type = data.get("type")

            # -----------------------------------------
            # LAPTOP REGISTRATION
            # -----------------------------------------

            if message_type == "register":

                hostname = data.get("hostname")
                os_name = data.get("os")
                os_version = data.get("os_version")

                await laptop_manager.register(
                    device_id=device_id,
                    websocket=websocket,
                    hostname=hostname,
                    os_name=os_name,
                    os_version=os_version,
                )

                await laptop_manager.update_last_seen(
                    device_id
                )

                logger.info(
                    f"[LAPTOP AGENT] Registered: "
                    f"{hostname} ({device_id})"
                )

                await websocket.send_text(
                    json.dumps(
                        {
                            "event": "laptop.acknowledged",
                            "device_id": device_id,
                            "status": "registered",
                        }
                    )
                )

            # -----------------------------------------
            # PING
            # -----------------------------------------

            elif message_type == "ping":

                await laptop_manager.update_last_seen(
                    device_id
                )

                await websocket.send_text(
                    json.dumps(
                        {
                            "event": "laptop.pong",
                            "device_id": device_id,
                        }
                    )
                )

                # Safe test command
                command_id = await laptop_manager.send_command(
                    device_id=device_id,
                    command="computer.get_screen_size",
                    arguments={},
                )

                logger.info(
                    f"[LAPTOP AGENT] Test command sent: "
                    f"{command_id}"
                )

            # -----------------------------------------
            # COMMAND RESULT
            # -----------------------------------------

            elif message_type == "command_result":

                await laptop_manager.update_last_seen(
                    device_id
                )

                command_id = data.get("command_id")

                completed = await laptop_manager.complete_command(
                    device_id=device_id,
                    command_id=command_id,
                    result=data,
                )

                if completed:

                    logger.info(
                        f"[LAPTOP AGENT] Command completed: "
                        f"{completed}"
                    )

                    await websocket.send_text(
                        json.dumps(
                            {
                                "event": "laptop.command_acknowledged",
                                "device_id": device_id,
                                "command_id": command_id,
                                "command": completed["command"],
                                "success": data.get("success"),
                                "data": data.get("data"),
                            }
                        )
                    )

                else:

                    logger.warning(
                        f"[LAPTOP AGENT] Unknown command result: "
                        f"{command_id}"
                    )

            # -----------------------------------------
            # UNKNOWN MESSAGE
            # -----------------------------------------

            else:

                await laptop_manager.update_last_seen(
                    device_id
                )

                await websocket.send_text(
                    json.dumps(
                        {
                            "event": "laptop.acknowledged",
                            "device_id": device_id,
                        }
                    )
                )

    except WebSocketDisconnect:

        await laptop_manager.unregister(
            device_id
        )

        logger.info(
            f"[LAPTOP AGENT] Disconnected: {device_id}"
        )