"""Application entry point for Comicarr."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession
from starlette.middleware.sessions import SessionMiddleware

from comicarr.core.bootstrap import bootstrap_security
from comicarr.core.config import get_settings
from comicarr.core.database import (
    check_database_schema,
    create_database_engine,
    create_session_factory,
)
from comicarr.core.logging import setup_logging
from comicarr.core.metrics import setup_metrics
from comicarr.core.middleware import TracingMiddleware
from comicarr.core.routes import create_app_router

logger = structlog.get_logger("comicarr.app")

# Frontend static files directory
FRONTEND_DIR = Path(__file__).parent / "static" / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    app_version = "0.1.0"
    # Get fresh settings for logging
    settings = get_settings()
    logger.info(
        "Starting Comicarr application",
        version=app_version,
        env=settings.env,
        host=settings.host_bind_address,
        port=settings.host_port,
    )

    # Database is already initialized in create_app()
    engine = app.state.engine

    # Check if migrations are needed (but don't run them automatically)
    logger.info("Checking database schema status...")
    migrations_needed = await check_database_schema(engine)
    if migrations_needed:
        logger.warning(
            "⚠️  Database migrations are pending! "
            "Please run 'alembic upgrade head' to apply migrations."
        )
    else:
        logger.info("Database schema is up to date")

    # Bootstrap security configuration
    logger.info("Bootstrapping security configuration...")
    bootstrap_security()

    # Bootstrap built-in indexers and libraries (after session factory is set)
    logger.info("Bootstrapping built-in indexers and libraries...")
    try:
        async_session_factory = app.state.async_session_factory
        async with async_session_factory() as session:
            from comicarr.core.bootstrap import bootstrap_indexers, bootstrap_libraries

            await bootstrap_indexers(session)
            await bootstrap_libraries(session)
    except Exception as e:
        # Log error without exc_info to avoid dev processor issues
        # The actual bootstrap error will be visible in the traceback above
        logger.error(
            "Failed to bootstrap indexers/libraries",
            error=str(e),
            error_type=type(e).__name__,
        )
        # Don't fail startup if bootstrap fails

    # Recover and restart any active jobs that were interrupted
    logger.info("Checking for active jobs to recover...")
    try:
        async_session_factory = app.state.async_session_factory
        async with async_session_factory() as session:
            from sqlmodel import col, select

            from comicarr.core.database import get_global_session_factory
            from comicarr.core.weekly_releases.job_processor import process_weekly_release_job
            from comicarr.core.weekly_releases.matching_job_processor import process_matching_job
            from comicarr.db.models import WeeklyReleaseMatchingJob, WeeklyReleaseProcessingJob

            # Find processing jobs that need recovery
            processing_jobs_result = await session.exec(
                select(WeeklyReleaseProcessingJob).where(
                    col(WeeklyReleaseProcessingJob.status).in_(["queued", "processing"])
                )
            )
            processing_jobs = processing_jobs_result.all()

            # Find matching jobs that need recovery
            matching_jobs_result = await session.exec(
                select(WeeklyReleaseMatchingJob).where(
                    col(WeeklyReleaseMatchingJob.status).in_(["queued", "processing"])
                )
            )
            matching_jobs = matching_jobs_result.all()

            if processing_jobs or matching_jobs:
                logger.info(
                    "Found jobs to recover",
                    processing_count=len(processing_jobs),
                    matching_count=len(matching_jobs),
                )

                # Restart processing jobs
                for job in processing_jobs:
                    # Reset status to queued if it was processing (in case it was stuck)
                    if job.status == "processing":
                        job.status = "queued"
                        await session.commit()

                    logger.info("Recovering processing job", job_id=job.id, week_id=job.week_id)
                    session_factory = get_global_session_factory()
                    if session_factory:

                        async def run_job(job_id: str):
                            async with session_factory() as bg_session:  # type: ignore[misc]
                                await process_weekly_release_job(bg_session, job_id)

                        asyncio.create_task(run_job(job.id))

                # Restart matching jobs
                for job in matching_jobs:
                    # Reset status to queued if it was processing
                    if job.status == "processing":
                        job.status = "queued"
                        await session.commit()

                    logger.info(
                        "Recovering matching job",
                        job_id=job.id,
                        week_id=job.week_id,
                        match_type=job.match_type,
                    )
                    session_factory = get_global_session_factory()
                    if session_factory:

                        async def run_job(job_id: str):
                            async with session_factory() as bg_session:  # type: ignore[misc]
                                await process_matching_job(bg_session, job_id)

                        asyncio.create_task(run_job(job.id))
            else:
                logger.info("No active jobs to recover")
    except Exception as e:
        logger.error(
            "Failed to recover jobs",
            error=str(e),
            error_type=type(e).__name__,
        )
        # Don't fail startup if job recovery fails

    # Setup scheduled tasks for weekly releases
    logger.info("Setting up scheduled tasks...")
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    from comicarr.core.settings_persistence import get_effective_settings
    from comicarr.core.weekly_releases.scheduled_fetch import fetch_current_week_releases

    scheduler = AsyncIOScheduler()
    app.state.scheduler = scheduler

    # Function to setup/update the scheduled job
    def setup_scheduled_fetch():
        """Setup or update the scheduled fetch job based on current settings."""
        # Remove existing job if it exists
        try:
            scheduler.remove_job("fetch_weekly_releases")
        except Exception:
            pass

        # Get settings
        settings = get_effective_settings()
        weekly_releases = settings.get("weekly_releases", {})

        if weekly_releases.get("auto_fetch_enabled", False):
            interval_hours = weekly_releases.get("auto_fetch_interval_hours", 12)

            async def scheduled_fetch_task():
                try:
                    async_session_factory = app.state.async_session_factory
                    async with async_session_factory() as session:
                        await fetch_current_week_releases(session)
                except Exception as e:
                    logger.error("Scheduled fetch task failed", error=str(e), exc_info=True)

            # Schedule the job
            scheduler.add_job(
                scheduled_fetch_task,
                trigger=IntervalTrigger(hours=interval_hours),
                id="fetch_weekly_releases",
                name="Fetch weekly releases from all sources",
                replace_existing=True,
            )
            logger.info(
                "Scheduled weekly release fetching",
                interval_hours=interval_hours,
            )
        else:
            logger.info("Automatic weekly release fetching is disabled")

    # Setup the scheduled job
    setup_scheduled_fetch()

    # Start scheduler
    scheduler.start()
    logger.info("Scheduler started")

    # Run initial fetch on startup (lazy, non-blocking)
    async def initial_fetch_task():
        """Run initial fetch after a short delay (non-blocking)."""
        await asyncio.sleep(5)  # Wait 5 seconds after startup
        try:
            async_session_factory = app.state.async_session_factory
            async with async_session_factory() as session:
                await fetch_current_week_releases(session)
        except Exception as e:
            logger.error("Initial fetch on startup failed", error=str(e), exc_info=True)

    # Only run if enabled
    settings = get_effective_settings()
    if settings.get("weekly_releases", {}).get("auto_fetch_enabled", False):
        asyncio.create_task(initial_fetch_task())
        logger.info("Initial fetch scheduled for startup")

    yield

    # Shutdown scheduler
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown()
        logger.info("Scheduler shut down")

    # Shutdown logic
    logger.info("Shutting down Comicarr application")
    if hasattr(app.state, "engine") and app.state.engine:
        await app.state.engine.dispose()
        logger.info("Database engine disposed")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app_version = "0.1.0"

    # Get fresh settings (not module-level cached)
    settings = get_settings()

    # Setup logging first (use settings)
    setup_logging(debug=settings.is_debug, logs_dir=settings.logs_dir)

    app = FastAPI(
        title="Comicarr",
        description="Comic book library management system",
        version=app_version,
        lifespan=lifespan,
    )

    # Initialize database SYNCHRONOUSLY (like experimentation branch)
    database_file = settings.database_dir / "comicarr.db"
    engine = create_database_engine(database_file, echo=settings.is_debug)
    async_session_factory = create_session_factory(engine)

    # Store in app.state immediately
    app.state.engine = engine
    app.state.async_session_factory = async_session_factory

    # Also store globally for access when app is mounted
    from comicarr.core.database import set_global_session_factory

    set_global_session_factory(async_session_factory)
    logger.info("Database engine and session factory created")

    # Create FastAPI dependency for database sessions (closure that captures async_session_factory)
    async def get_db_session() -> AsyncIterator[SQLModelAsyncSession]:
        """FastAPI dependency for database sessions."""
        async with async_session_factory() as session:
            yield session

    # Add session middleware (must be before other middleware that use sessions)
    # Generate a secret key from environment variable (for production)
    secret_key = os.getenv("COMICARR_SECRET_KEY", "dev-secret-key-change-in-production")
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_key,
        max_age=86400 * 7,  # 7 days
        same_site="lax",
    )

    # Add tracing middleware (before other middleware to capture all requests)
    app.add_middleware(TracingMiddleware)

    # Setup metrics (before routes to instrument all routes)
    # If base_url is set, metrics will be set up on root_app in main()
    # Otherwise, set them up here so they're available for tests and direct app usage
    # Note: We don't set up metrics here if base_url is set, to avoid duplicate registration
    # Metrics will be set up in main() on either root_app or app_instance
    if not settings.host_base_url:
        # Set up metrics for tests and direct app usage (when base_url is not set)
        app_version = "0.1.0"
        setup_metrics(app, app_version)

    # Register API routes (get_db_session is now available)
    app_router = create_app_router(app, get_db_session)
    app.include_router(app_router)

    # Serve static frontend files (if built)
    if FRONTEND_DIR.exists() and FRONTEND_INDEX.exists():
        # Serve static assets (JS, CSS, etc.)
        assets_dir = FRONTEND_DIR / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        # Serve root route (empty path) - serve index.html
        @app.get("/")
        async def serve_frontend_root():
            """Serve index.html for root of mounted app."""
            # If base_url is set, rewrite asset paths to include base_url
            if settings.host_base_url:
                import re

                from fastapi.responses import HTMLResponse

                html_content = FRONTEND_INDEX.read_text(encoding="utf-8")
                base_url_clean = settings.host_base_url.rstrip("/")

                def rewrite_path(match):
                    attr = match.group(1)
                    path = match.group(2)
                    if path.startswith(base_url_clean):
                        return match.group(0)
                    return f'{attr}="{base_url_clean}{path}"'

                html_content = re.sub(r'(src|href)="(/[^"]+)"', rewrite_path, html_content)
                return HTMLResponse(content=html_content)
            else:
                return FileResponse(FRONTEND_INDEX)

        # Serve other static files from frontend directory (logo, favicon, etc.)
        # Catch-all route for SPA: serve static files or index.html for all non-API routes
        # Note: This must be defined AFTER API routes so API routes are matched first
        # Only match GET requests to avoid intercepting POST/PUT/DELETE API calls
        @app.get("/{full_path:path}")
        async def serve_frontend(full_path: str):
            """Serve frontend SPA and static files for all non-API routes."""
            # Handle empty path (root of mounted app)
            if not full_path or full_path == "":
                full_path = ""

            # Explicitly exclude API routes - these should be handled by API routers above
            # This is a safety check in case a route wasn't matched
            # Note: This route only handles GET, so POST/PUT/DELETE API calls won't match here
            if (
                full_path.startswith("api/")
                or full_path.startswith("docs")
                or full_path.startswith("redoc")
                or full_path == "openapi.json"
                or full_path == "metrics"
            ):
                from fastapi import HTTPException

                raise HTTPException(status_code=404)

            # Try to serve static file if it exists (only if path is not empty)
            if full_path:
                static_file = FRONTEND_DIR / full_path
                if static_file.is_file() and static_file.exists():
                    return FileResponse(static_file)

            # Otherwise serve index.html for SPA routing
            # If base_url is set, rewrite asset paths to include base_url
            if settings.host_base_url:
                import re

                from fastapi.responses import HTMLResponse

                html_content = FRONTEND_INDEX.read_text(encoding="utf-8")
                # Rewrite absolute paths to include base_url
                # Match src="/assets/...", href="/assets/...", etc.
                # But don't rewrite if path already starts with base_url
                base_url_clean = settings.host_base_url.rstrip("/")

                def rewrite_path(match):
                    attr = match.group(1)  # src or href
                    path = match.group(2)  # /assets/... or /comicarr_favicon.ico
                    # Don't rewrite if already has base_url
                    if path.startswith(base_url_clean):
                        return match.group(0)
                    # Rewrite to include base_url
                    return f'{attr}="{base_url_clean}{path}"'

                html_content = re.sub(r'(src|href)="(/[^"]+)"', rewrite_path, html_content)
                logger.debug(
                    "Serving frontend with rewritten paths",
                    base_url=base_url_clean,
                    path=full_path,
                )
                return HTMLResponse(content=html_content)
            else:
                return FileResponse(FRONTEND_INDEX)

    else:
        logger.warning(
            "Frontend not found",
            frontend_dir=str(FRONTEND_DIR),
            message="Frontend build not found. Run 'make build-front' to build frontend.",
        )

    return app


def main() -> None:
    """Main entry point."""
    # Reload settings to ensure we have the latest values
    # This is important because settings might have been updated while server was running
    from comicarr.core.config import reload_settings

    current_settings = reload_settings()

    # Debug: Log what settings we're actually using
    logger.info(
        "Starting server with settings",
        host=current_settings.host_bind_address,
        port=current_settings.host_port,
        base_url=current_settings.host_base_url or "(empty)",
    )

    app_instance = create_app()

    # Setup metrics on the app that will be used
    app_version = "0.1.0"

    # If base_url is set, create a root app with metrics/health at root, and mount main app at base_url
    if current_settings.host_base_url:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse, RedirectResponse

        from comicarr.core.tracing import get_trace_id

        root_app = FastAPI()

        # Add tracing middleware to root_app so trace_id works
        from comicarr.core.middleware import TracingMiddleware

        root_app.add_middleware(TracingMiddleware)

        # Setup metrics on root_app (only once, to avoid duplicates)
        from comicarr.core.metrics import setup_metrics

        setup_metrics(root_app, app_version)

        # Add health endpoint at root level (not under base_url)
        @root_app.get("/health")
        async def root_health() -> JSONResponse:
            """Health check endpoint at root level."""
            trace_id = get_trace_id()
            return JSONResponse(
                {
                    "status": "healthy",
                    "trace_id": trace_id,
                }
            )

        # Serve favicon at root level (browsers look for it at /)
        favicon_file = FRONTEND_DIR / "comicarr_favicon.ico"
        if favicon_file.exists():

            @root_app.get("/comicarr_favicon.ico")
            async def serve_favicon():
                """Serve favicon at root level."""
                return FileResponse(favicon_file)

            # Also serve at /favicon.ico for browser default behavior
            @root_app.get("/favicon.ico")
            async def serve_favicon_default():
                """Serve favicon at default browser path."""
                return FileResponse(favicon_file)

        # Add redirect from root to base_url (with trailing slash for consistency)
        @root_app.get("/")
        async def redirect_to_base():
            """Redirect from root to base_url."""
            # Redirect to base_url with trailing slash for consistency
            redirect_url = current_settings.host_base_url.rstrip("/") + "/"
            return RedirectResponse(url=redirect_url, status_code=301)

        # Mount the main app at base_url (this includes UI, API, etc.)
        root_app.mount(current_settings.host_base_url, app_instance)
        app = root_app
        logger.info(
            "Application mounted at base URL",
            base_url=current_settings.host_base_url,
        )
    else:
        # No base_url - setup metrics on app_instance
        from comicarr.core.metrics import setup_metrics

        setup_metrics(app_instance, app_version)
        app = app_instance

    import uvicorn

    # Note: uvicorn reload requires an import string, not an app object
    # Since we create the app dynamically based on settings, we can't use reload
    # For development, manual restart is required for code changes
    # Settings changes already trigger restart via SIGTERM (or manual restart in dev)
    # Explicit logging of what we're passing to uvicorn
    logger.info(
        "Starting uvicorn server",
        host=current_settings.host_bind_address,
        port=current_settings.host_port,
        port_type=type(current_settings.host_port).__name__,
    )

    uvicorn.run(
        app,
        host=current_settings.host_bind_address,
        port=current_settings.host_port,
        log_config=None,  # We use structlog
        reload=False,  # Disabled - requires import string, not app object
    )


if __name__ == "__main__":
    main()
