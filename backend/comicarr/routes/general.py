"""General API routes."""

from __future__ import annotations

import os
import signal

import structlog
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse

from comicarr.core.tracing import get_trace_id

router = APIRouter(prefix="/api")
logger = structlog.get_logger("comicarr.routes.general")


@router.get("/")
async def root() -> JSONResponse:
    """Root endpoint - hello world.

    All logs in this function will automatically include the trace_id from context.
    """
    trace_id = get_trace_id()
    logger.info("Root endpoint accessed", trace_id=trace_id)
    return JSONResponse(
        {
            "message": "Hello, Comicarr!",
            "version": "0.1.0",
            "status": "ok",
            "trace_id": trace_id,  # Include trace_id in response for debugging
        }
    )


@router.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint."""
    trace_id = get_trace_id()
    logger.debug("Health check", trace_id=trace_id)
    return JSONResponse(
        {
            "status": "healthy",
            "trace_id": trace_id,
        }
    )


@router.get("/config")
async def get_config() -> JSONResponse:
    """Get frontend configuration (base_url, etc.)."""
    from comicarr.core.config import get_settings

    settings = get_settings()
    trace_id = get_trace_id()
    logger.debug("Config endpoint accessed", trace_id=trace_id)
    return JSONResponse(
        {
            "base_url": settings.host_base_url or "",
            "trace_id": trace_id,
        }
    )


def _trigger_restart() -> None:
    """Trigger server restart by sending SIGTERM to current process.

    This will cause uvicorn to gracefully shutdown, and a process manager
    (like systemd, supervisor, or a wrapper script) should restart it.
    """
    logger.info("Triggering server restart...")
    # Send SIGTERM to current process for graceful shutdown
    os.kill(os.getpid(), signal.SIGTERM)


@router.post("/system/restart")
async def restart_server(background_tasks: BackgroundTasks) -> JSONResponse:
    """Restart the server.

    This endpoint triggers a graceful shutdown. The server will restart
    if managed by a process manager (systemd, supervisor, etc.) or
    a wrapper script that monitors the process.
    """
    trace_id = get_trace_id()
    logger.info("Server restart requested", trace_id=trace_id)

    # Schedule restart in background after response is sent
    background_tasks.add_task(_trigger_restart)

    return JSONResponse(
        {
            "message": "Server restart initiated",
            "trace_id": trace_id,
        }
    )
