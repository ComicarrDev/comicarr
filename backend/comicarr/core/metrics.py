"""Prometheus metrics configuration."""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

logger = structlog.get_logger("comicarr.metrics")

# Track if metrics have been set up to prevent duplicate registration
_metrics_setup = False

# Application info
app_info = Gauge(
    "app_info",
    "Application information",
    ["version"],
)

# Database connection pool metrics
db_connections_active = Gauge(
    "db_connections_active",
    "Number of active database connections",
)
db_connections_idle = Gauge(
    "db_connections_idle",
    "Number of idle database connections in pool",
)
db_connections_overflow = Gauge(
    "db_connections_overflow",
    "Number of overflow database connections beyond pool size",
)
db_pool_size = Gauge(
    "db_pool_size",
    "Configured database connection pool size",
)
db_pool_max_overflow = Gauge(
    "db_pool_max_overflow",
    "Configured maximum overflow connections for database pool",
)

# Database retry operation metrics
db_retry_attempts_total = Counter(
    "db_retry_attempts_total",
    "Total number of database operation retry attempts",
    ["operation_type"],
)
db_lock_errors_total = Counter(
    "db_lock_errors_total",
    "Total number of database lock errors encountered",
)
db_retries_succeeded_total = Counter(
    "db_retries_succeeded_total",
    "Total number of database operations that succeeded after retry",
    ["operation_type"],
)
db_retries_failed_total = Counter(
    "db_retries_failed_total",
    "Total number of database operations that failed after all retries",
    ["operation_type"],
)
db_retry_duration_seconds = Histogram(
    "db_retry_duration_seconds",
    "Duration of database retry operations in seconds",
    ["operation_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# Authentication metrics
auth_login_failures_total = Counter(
    "auth_login_failures_total",
    "Total number of failed login attempts (security metric)",
    [
        "reason"
    ],  # reason: invalid_username, invalid_password, not_configured, not_properly_configured
)


def setup_metrics(app: FastAPI, app_version: str) -> None:
    """Setup Prometheus metrics using prometheus-fastapi-instrumentator.

    Args:
        app: FastAPI application instance
        app_version: Application version
    """
    # Check if metrics are already set up on this app instance
    if hasattr(app.state, "_metrics_initialized") and app.state._metrics_initialized:
        logger.debug("Metrics already initialized for this app instance, skipping")
        return

    # Check if instrumentator middleware is already present
    # The instrumentator adds middleware with a specific pattern we can detect
    if hasattr(app, "user_middleware"):
        for middleware in app.user_middleware:
            # Check if PrometheusInstrumentator middleware is already present
            if (
                "prometheus" in str(type(middleware)).lower()
                or "instrumentator" in str(type(middleware)).lower()
            ):
                logger.debug("Instrumentator middleware already present, skipping setup")
                app.state._metrics_initialized = True
                return

    # Create instrumentator with configuration
    instrumentator = Instrumentator(
        should_group_status_codes=False,  # Don't group status codes (keep individual codes)
        should_ignore_untemplated=True,  # Ignore untemplated routes
        should_instrument_requests_inprogress=True,  # Track in-progress requests
        excluded_handlers=[
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
        ],  # Exclude docs and metrics
    )

    # Instrument the app (this adds middleware automatically)
    instrumentator.instrument(app).expose(app, endpoint="/metrics")

    # Mark this app instance as having metrics initialized
    app.state._metrics_initialized = True

    # Set application info metric
    app_info.labels(version=app_version).set(1)

    logger.info("Metrics initialized", version=app_version)
