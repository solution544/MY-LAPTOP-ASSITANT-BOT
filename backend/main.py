"""
Solution AI backend entrypoint.

Development:
uvicorn backend.main:app --reload --port 8000

Production:
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
"""

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import (
chat,
conversations,
laptop,
laptop_command,
laptop_status,
memory,
system,
tasks,
tools,
voice,
websocket,
)
from backend.core.config import get_settings
from backend.core.logging import logger
from backend.mcp.client import MCPServerConfig, mcp_manager
from backend.scheduler.scheduler import (
load_all_scheduled_tasks,
scheduler,
)
from backend.tools.register_all import register_all_tools

settings = get_settings()

app = FastAPI(
title="Solution AI",
description="Backend for the Solution AI personal agent.",
version="0.1.0",
)

# ---------------------------------------------------------

# CORS

# ---------------------------------------------------------

allowed_origins = [
"http://localhost:5173",
"http://127.0.0.1:5173",
]

# Production frontend URL.

# Example:

# FRONTEND_URL=https://solution-ai.vercel.app

frontend_url = getattr(settings, "frontend_url", None)

if isinstance(frontend_url, str) and frontend_url:
    allowed_origins.append(str(frontend_url))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------

# API ROUTES

# ---------------------------------------------------------

app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(system.router)
app.include_router(websocket.router)

app.include_router(laptop.router)
app.include_router(laptop_status.router)
app.include_router(laptop_command.router)

app.include_router(tools.router)
app.include_router(memory.router)
app.include_router(tasks.router)
app.include_router(tasks.scheduled_router)
app.include_router(voice.router)

# ---------------------------------------------------------

# ROOT

# ---------------------------------------------------------

@app.get("/")
def root():
    return {
        "name": "Solution AI",
        "status": "running",
        "env": settings.app_env,
    }

# ---------------------------------------------------------

# STARTUP

# ---------------------------------------------------------

@app.on_event("startup")
async def on_startup():
    logger.info(
        "Solution AI backend starting — "
        f"env={settings.app_env}, "
        f"provider={settings.ai_provider}"
    )

    # Register all Solution AI tools.
    register_all_tools()

    # Start scheduler.
    scheduler.start()

    # Load scheduled tasks.
    load_all_scheduled_tasks()

    # Start MCP servers if configured.
    try:
        server_configs = [
            MCPServerConfig(**cfg)
            for cfg in json.loads(settings.mcp_servers)
        ]

    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(
            "MCP_SERVERS is not valid JSON, "
            f"skipping MCP startup: {exc}"
        )
        server_configs = []

    if server_configs:
        await mcp_manager.connect_all(server_configs)


# ---------------------------------------------------------

# SHUTDOWN

# ---------------------------------------------------------

@app.on_event("shutdown")
async def on_shutdown():
    scheduler.shutdown(wait=False)
    await mcp_manager.shutdown()
