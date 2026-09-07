import asyncio
import json
import os
import platform
import socket
import sys

import websockets


# ---------------------------------------------------------
# Make the Solution AI project root importable.
# ---------------------------------------------------------

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ---------------------------------------------------------
# Solution AI backend imports
# ---------------------------------------------------------

from backend.security.permissions import ConfirmationRequired
from backend.tools.register_all import register_all_tools
from backend.tools.registry import registry


WS_URL = "ws://127.0.0.1:8000/ws/laptop"


async def execute_laptop_tool(
    command: str,
    arguments: dict,
):
    """
    Execute a laptop command through the central
    Solution AI ToolRegistry.
    """

    try:
        result = await registry.execute(
            tool_name=command,
            arguments=arguments,
            pre_confirmed=True,
        )

        return result.to_dict()

    except ConfirmationRequired:
        return {
            "success": False,
            "data": None,
            "error": "This action requires confirmation.",
            "error_code": "CONFIRMATION_REQUIRED",
        }

    except Exception as exc:
        return {
            "success": False,
            "data": None,
            "error": str(exc),
            "error_code": "LAPTOP_AGENT_ERROR",
        }


async def main():
    print("=" * 50)
    print("SOLUTION AI LAPTOP AGENT")
    print("=" * 50)

    print(f"Computer: {socket.gethostname()}")
    print(f"Operating System: {platform.system()}")
    print(f"OS Version: {platform.version()}")
    print()

    # Register all local tools inside the laptop-agent process.
    register_all_tools()

    print("Local tool registry initialized.")
    print()

    print(f"Connecting to: {WS_URL}")

    try:
        async with websockets.connect(WS_URL) as websocket:
            print("Connected to Solution AI backend.")
            print("Waiting for server events...")
            print()

            # Receive connection event
            message = await websocket.recv()
            data = json.loads(message)

            print("SERVER EVENT:")
            print(data)
            print()

            # Register this laptop
            await websocket.send(
                json.dumps(
                    {
                        "type": "register",
                        "hostname": socket.gethostname(),
                        "os": platform.system(),
                        "os_version": platform.version(),
                    }
                )
            )

            print("Laptop registration sent.")
            print()

            # Send ping
            await websocket.send(
                json.dumps(
                    {
                        "type": "ping"
                    }
                )
            )

            print("Ping sent to backend.")
            print()

            # Listen for server messages
            while True:
                message = await websocket.recv()
                data = json.loads(message)

                print("SERVER MESSAGE:")
                print(data)

                # Handle commands from backend
                if data.get("event") == "laptop.command":
                    command = data.get("command")
                    arguments = data.get("arguments", {})

                    print()
                    print("COMMAND RECEIVED:")
                    print(f"Tool: {command}")
                    print(f"Arguments: {arguments}")
                    print()

                    # Execute using the central ToolRegistry.
                    result = await execute_laptop_tool(
                        command=command,
                        arguments=arguments,
                    )

                    # Send structured result back to backend.
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "command_result",
                                "command_id": data.get("command_id"),
                                "command": command,
                                **result,
                            }
                        )
                    )

                    print("COMMAND RESULT:")
                    print(result)
                    print()

    except ConnectionRefusedError:
        print()
        print("ERROR: Could not connect to Solution AI backend.")
        print("Make sure the FastAPI backend is running.")

    except Exception as exc:
        print()
        print(f"ERROR: {exc}")


if __name__ == "__main__":
    asyncio.run(main())