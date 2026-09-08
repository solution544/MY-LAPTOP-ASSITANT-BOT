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

from backend.database import models  # noqa: F401
from backend.database.session import Base, engine

from backend.mcp.client import MCPServerConfig, mcp_manager

from backend.scheduler.scheduler import (
    load_all_scheduled_tasks,
    scheduler,
)

from backend.tools.register_all import register_all_tools


# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------

settings = get_settings()


# ---------------------------------------------------------
# FASTAPI APP
# ---------------------------------------------------------

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

frontend_url = getattr(settings, "frontend_url", None)

if isinstance(frontend_url, str) and frontend_url.strip():
    frontend_url = frontend_url.strip().rstrip("/")

    if frontend_url not in allowed_origins:
        allowed_origins.append(frontend_url)


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# API ROUTERS
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
# ROOT ENDPOINT
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

    # -----------------------------------------------------
    # 1. REGISTER ALL TOOLS
    # -----------------------------------------------------

    register_all_tools()

    logger.info("Tool registry initialized successfully.")

    # -----------------------------------------------------
    # 2. INITIALIZE / VERIFY DATABASE
    # -----------------------------------------------------
    #
    # This is important for Render's fresh PostgreSQL
    # database. It creates any missing tables, including
    # scheduled_tasks, before the scheduler tries to load
    # scheduled jobs.
    #
    # Later, when the project is more mature, use Alembic
    # migrations instead of create_all() on every startup.
    #

    try:
        Base.metadata.create_all(bind=engine)

        logger.info(
            "Database tables verified/created successfully."
        )

    except Exception as exc:
        logger.exception(
            f"Database initialization failed: {exc}"
        )
        raise

    # -----------------------------------------------------
    # 3. START SCHEDULER
    # -----------------------------------------------------

    try:
        scheduler.start()

        logger.info("Scheduler started successfully.")

    except Exception as exc:
        logger.exception(
            f"Scheduler startup failed: {exc}"
        )
        raise

    # -----------------------------------------------------
    # 4. LOAD SCHEDULED TASKS
    # -----------------------------------------------------

    try:
        load_all_scheduled_tasks()

        logger.info(
            "Scheduled tasks loaded successfully."
        )

    except Exception as exc:
        logger.exception(
            f"Failed to load scheduled tasks: {exc}"
        )
        raise

    # -----------------------------------------------------
    # 5. MCP SERVERS
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # 6. CONNECT MCP SERVERS
    # -----------------------------------------------------

    if server_configs:
        try:
            await mcp_manager.connect_all(server_configs)

            logger.info(
                f"Connected to {len(server_configs)} MCP server(s)."
            )

        except Exception as exc:
            logger.exception(
                f"MCP startup failed: {exc}"
            )
            raise

    else:
        logger.info("No MCP servers configured.")


# ---------------------------------------------------------
# SHUTDOWN
# ---------------------------------------------------------

@app.on_event("shutdown")
async def on_shutdown():
    # Stop scheduler
    try:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped successfully.")

    except Exception as exc:
        logger.exception(
            f"Scheduler shutdown failed: {exc}"
        )

    # Shutdown MCP manager
    try:
        await mcp_manager.shutdown()
        logger.info("MCP manager shut down successfully.")

    except Exception as exc:
        logger.exception(
            f"MCP shutdown failed: {exc}"
        )