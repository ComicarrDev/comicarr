"""Logging configuration."""

from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from structlog.types import EventDict

# Type for exception info tuple (from sys.exc_info())
ExcInfo = tuple[type[BaseException] | None, BaseException | None, TracebackType | None]

# Type for traceback frame information
TracebackFrame = dict[str, str | int | None]

# Type for structured exception details - using explicit Dict structure
ExceptionDetails = dict[
    str,
    None | str | list[TracebackFrame],
]


def format_exception_for_json(
    exc_info: ExcInfo | None,
) -> ExceptionDetails:
    """Format exception information for JSON logging.

    Extracts exception details into a structured format that's easier to read
    in JSON logs than a raw traceback string.

    Args:
        exc_info: Exception info tuple from sys.exc_info() or None

    Returns:
        Dictionary with exception details:
        - exception_type: Exception class name (str or None)
        - exception_message: Exception message (str or None)
        - exception_module: Module where exception occurred (str or None)
        - traceback_frames: List of traceback frames
        - traceback_text: Full traceback as text (for reference)
    """
    if exc_info is None or exc_info == (None, None, None):
        return {}

    exc_type, exc_value, exc_tb = exc_info

    exception_details: ExceptionDetails = {
        "exception_type": exc_type.__name__ if exc_type else None,
        "exception_message": str(exc_value) if exc_value else None,
        "exception_module": exc_type.__module__ if exc_type else None,
    }

    # Extract structured traceback information
    if exc_tb:
        tb_frames: list[TracebackFrame] = []
        current_tb: TracebackType | None = exc_tb

        while current_tb is not None:
            frame = current_tb.tb_frame
            frame_info: TracebackFrame = {
                "filename": frame.f_code.co_filename,
                "lineno": current_tb.tb_lineno,
                "function": frame.f_code.co_name,
            }

            # Try to get source line if available
            try:
                import linecache

                line = linecache.getline(frame.f_code.co_filename, current_tb.tb_lineno)
                if line:
                    frame_info["source_line"] = line.strip()
            except Exception:
                pass

            tb_frames.append(frame_info)
            current_tb = current_tb.tb_next

        exception_details["traceback_frames"] = tb_frames

        # Also include full traceback as text for reference
        exception_details["traceback_text"] = "".join(
            traceback.format_exception(exc_type, exc_value, exc_tb)
        )

    return exception_details


def exception_processor(
    logger: structlog.BoundLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Custom exception processor for better JSON exception formatting.

    Extracts exception information into structured fields instead of embedding
    the full traceback as a string, making exceptions easier to read in JSON logs.

    Args:
        logger: Logger instance (structlog BoundLogger)
        method_name: Logging method name
        event_dict: Event dictionary from structlog

    Returns:
        Modified event dictionary with structured exception information
    """
    # Check if exc_info is in the event dict (from logger.exception() or exc_info=True)
    exc_info = event_dict.pop("exc_info", None)  # type: ignore[assignment]

    # Handle case where exc_info is True (from logger.exception() or exc_info=True)
    # In this case, we need to get the exception info from sys.exc_info()
    if exc_info is True:
        import sys

        exc_info = sys.exc_info()  # type: ignore[assignment]

    if exc_info and exc_info != (None, None, None):
        # Format exception into structured format
        exception_details = format_exception_for_json(exc_info)  # type: ignore[arg-type]
        if exception_details:
            event_dict["exception"] = exception_details

            # Add a readable exception summary for quick scanning
            exc_type = exception_details.get("exception_type")
            exc_msg = exception_details.get("exception_message")
            if exc_type and exc_msg:
                event_dict["exception_summary"] = f"{exc_type}: {exc_msg}"

    # Also handle the case where exception might be passed directly
    if "exception" in event_dict and isinstance(event_dict["exception"], BaseException):
        exc = event_dict.pop("exception")
        exc_info = (type(exc), exc, exc.__traceback__)
        exception_details = format_exception_for_json(exc_info)
        if exception_details:
            event_dict["exception"] = exception_details

    return event_dict


class JSONFormatter(logging.Formatter):
    """JSON formatter for standard library logging (used for database logs)."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            log_data["exception"] = format_exception_for_json((exc_type, exc_value, exc_tb))

        # Add extra fields from record
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data, ensure_ascii=False)


def _close_handlers(logger: logging.Logger) -> None:
    """Close all handlers for a logger before clearing them.

    This prevents ResourceWarnings about unclosed file handles.
    """
    for handler in logger.handlers[:]:
        try:
            handler.close()
        except Exception:
            pass  # Ignore errors when closing handlers


def setup_logging(debug: bool = False, logs_dir: Path | None = None) -> None:
    """Setup structured logging with structlog.

    Configures:
    - Application logs: stdout (pretty in debug, JSON in production) + JSON file
    - Database logs (SQLite/SQLAlchemy): Separate JSON file only (WARNING level to reduce noise)

    Args:
        debug: Enable debug logging
        logs_dir: Optional directory for log files. If provided, logs will be written to files in JSON format.
    """
    log_level = logging.DEBUG if debug else logging.INFO

    # Setup handlers for application logs
    app_handlers: list[logging.Handler] = []

    # Setup stdout handler for Uvicorn logs (server status, HTTP access logs)
    # This will be used by Uvicorn loggers, not application loggers
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(log_level)

    # Also log to file if logs_dir is provided
    app_file_handler = None
    db_file_handler = None
    http_file_handler = None
    if logs_dir:
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)

            # Application log file (JSON structured)
            # When file logging is enabled, structured logs go ONLY to file, not stdout
            app_log_file = logs_dir / "comicarr.json.log"
            app_file_handler = logging.FileHandler(app_log_file, encoding="utf-8")
            app_file_handler.setLevel(log_level)
            app_handlers.append(app_file_handler)

            # Database log file (SQLite/SQLAlchemy) - separate file, WARNING level to reduce noise
            db_log_file = logs_dir / "comicarr.db.json.log"
            db_file_handler = logging.FileHandler(db_log_file, encoding="utf-8")
            # Handler accepts all levels - logger level controls what gets logged
            db_file_handler.setLevel(logging.DEBUG)
            # Note: We'll configure this separately for SQLAlchemy/SQLite loggers

            # HTTP client log file (httpx/httpcore) - separate file for external API calls
            http_log_file = logs_dir / "comicarr.http.json.log"
            http_file_handler = logging.FileHandler(http_log_file, encoding="utf-8")
            http_file_handler.setLevel(logging.DEBUG)
            # Use JSON formatter for HTTP logs
            json_formatter = JSONFormatter()
            http_file_handler.setFormatter(json_formatter)

        except Exception as e:
            # If file logging fails, log to stderr but don't crash
            sys.stderr.write(f"Warning: Failed to setup file logging: {e}\n")

    # If no file logging, fall back to stdout for application logs
    if not app_file_handler:
        app_handlers.append(stdout_handler)

    # Configure standard library logging for application logs
    # When file logging is enabled, this only has the file handler (no stdout)
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=app_handlers,
        force=True,  # Override any existing configuration
    )

    # Configure Uvicorn loggers to only write to stdout, not the file
    # Uvicorn logs are too verbose and not structured, so we exclude them from the JSON log file
    # These will always go to stdout for server status visibility
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.propagate = False  # Don't propagate to root logger (which has file handler)
    _close_handlers(uvicorn_logger)
    uvicorn_logger.handlers.clear()
    uvicorn_logger.addHandler(stdout_handler)  # Only stdout

    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.propagate = False
    _close_handlers(uvicorn_access_logger)
    uvicorn_access_logger.handlers.clear()
    uvicorn_access_logger.addHandler(stdout_handler)  # Only stdout

    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    uvicorn_error_logger.propagate = False
    _close_handlers(uvicorn_error_logger)
    uvicorn_error_logger.handlers.clear()
    uvicorn_error_logger.addHandler(stdout_handler)  # Only stdout

    # Configure separate loggers for SQLite and SQLAlchemy
    # These are too chatty, so we route them to a separate file
    # When echo=True (debug mode), SQLAlchemy logs at INFO level, so we need to handle that
    # Determine DB log level: INFO if debug mode (echo=True), WARNING otherwise
    db_log_level = logging.INFO if debug else logging.WARNING

    if db_file_handler:
        # Use JSON formatter for database logs
        json_formatter = JSONFormatter()
        db_file_handler.setFormatter(json_formatter)
        # Ensure handler flushes immediately (important for file logging)
        db_file_handler.setLevel(
            logging.DEBUG
        )  # Handler accepts all levels, logger controls filtering

        # SQLAlchemy logger (engine, pool, etc.)
        sqlalchemy_logger = logging.getLogger("sqlalchemy")
        sqlalchemy_logger.setLevel(db_log_level)
        sqlalchemy_logger.propagate = False  # Don't propagate to root logger
        # Remove any existing handlers to avoid duplicates
        _close_handlers(sqlalchemy_logger)
        sqlalchemy_logger.handlers.clear()
        sqlalchemy_logger.addHandler(db_file_handler)

        # SQLAlchemy engine logger (most verbose - this is where echo=True logs go)
        # This is the main logger that SQLAlchemy uses when echo=True
        sqlalchemy_engine_logger = logging.getLogger("sqlalchemy.engine")
        sqlalchemy_engine_logger.setLevel(db_log_level)
        sqlalchemy_engine_logger.propagate = False
        _close_handlers(sqlalchemy_engine_logger)
        sqlalchemy_engine_logger.handlers.clear()
        sqlalchemy_engine_logger.addHandler(db_file_handler)

        # SQLAlchemy engine.Engine logger (even more specific)
        sqlalchemy_engine_engine_logger = logging.getLogger("sqlalchemy.engine.Engine")
        sqlalchemy_engine_engine_logger.setLevel(db_log_level)
        sqlalchemy_engine_engine_logger.propagate = False
        _close_handlers(sqlalchemy_engine_engine_logger)
        sqlalchemy_engine_engine_logger.handlers.clear()
        sqlalchemy_engine_engine_logger.addHandler(db_file_handler)

        # SQLAlchemy pool logger
        sqlalchemy_pool_logger = logging.getLogger("sqlalchemy.pool")
        sqlalchemy_pool_logger.setLevel(db_log_level)
        sqlalchemy_pool_logger.propagate = False
        _close_handlers(sqlalchemy_pool_logger)
        sqlalchemy_pool_logger.handlers.clear()
        sqlalchemy_pool_logger.addHandler(db_file_handler)

        # SQLAlchemy dialect logger
        sqlalchemy_dialect_logger = logging.getLogger("sqlalchemy.dialects")
        sqlalchemy_dialect_logger.setLevel(db_log_level)
        sqlalchemy_dialect_logger.propagate = False
        _close_handlers(sqlalchemy_dialect_logger)
        sqlalchemy_dialect_logger.handlers.clear()
        sqlalchemy_dialect_logger.addHandler(db_file_handler)

        # SQLite logger
        sqlite_logger = logging.getLogger("sqlite3")
        sqlite_logger.setLevel(db_log_level)
        sqlite_logger.propagate = False
        _close_handlers(sqlite_logger)
        sqlite_logger.handlers.clear()
        sqlite_logger.addHandler(db_file_handler)

        # aiosqlite logger
        aiosqlite_logger = logging.getLogger("aiosqlite")
        aiosqlite_logger.setLevel(db_log_level)
        aiosqlite_logger.propagate = False
        _close_handlers(aiosqlite_logger)
        aiosqlite_logger.handlers.clear()
        aiosqlite_logger.addHandler(db_file_handler)

    # Configure HTTP client loggers (httpx, httpcore) - separate file for external API calls
    # These are verbose and should not pollute the main application log
    if http_file_handler:
        http_log_level = logging.WARNING  # Only log warnings/errors from HTTP clients by default

        # httpx logger
        httpx_logger = logging.getLogger("httpx")
        httpx_logger.setLevel(http_log_level)
        httpx_logger.propagate = False
        _close_handlers(httpx_logger)
        httpx_logger.handlers.clear()
        httpx_logger.addHandler(http_file_handler)

        # httpcore logger (used by httpx internally)
        httpcore_logger = logging.getLogger("httpcore")
        httpcore_logger.setLevel(http_log_level)
        httpcore_logger.propagate = False
        _close_handlers(httpcore_logger)
        httpcore_logger.handlers.clear()
        httpcore_logger.addHandler(http_file_handler)

        # httpcore.connection logger (very verbose)
        httpcore_connection_logger = logging.getLogger("httpcore.connection")
        httpcore_connection_logger.setLevel(http_log_level)
        httpcore_connection_logger.propagate = False
        _close_handlers(httpcore_connection_logger)
        httpcore_connection_logger.handlers.clear()
        httpcore_connection_logger.addHandler(http_file_handler)

        # httpcore.http11 logger (very verbose)
        httpcore_http11_logger = logging.getLogger("httpcore.http11")
        httpcore_http11_logger.setLevel(http_log_level)
        httpcore_http11_logger.propagate = False
        _close_handlers(httpcore_http11_logger)
        httpcore_http11_logger.handlers.clear()
        httpcore_http11_logger.addHandler(http_file_handler)

        # Test that the handler works
        test_http_logger = logging.getLogger("comicarr.logging.http_test")
        test_http_logger.setLevel(logging.INFO)
        test_http_logger.propagate = False
        test_http_logger.addHandler(http_file_handler)
        test_msg = f"HTTP client logging configured - level: {logging.getLevelName(http_log_level)}"
        test_http_logger.info(test_msg)
        _close_handlers(test_http_logger)  # Clean up test logger
        test_http_logger.handlers.clear()

        # Test that the handler works by writing a test log entry
        # Use a simple message since stdlib logger doesn't support keyword args
        if db_file_handler:
            test_logger = logging.getLogger("comicarr.logging.db_test")
            test_logger.setLevel(logging.INFO)
            test_logger.propagate = False
            test_logger.addHandler(db_file_handler)
            test_msg = f"Database logging configured - level: {logging.getLevelName(db_log_level)}, debug: {debug}"
            test_logger.info(test_msg)
            _close_handlers(test_logger)  # Clean up test logger
            test_logger.handlers.clear()

    # Build processors list
    processors = [
        structlog.contextvars.merge_contextvars,  # Merge trace_id and other context
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    # Add custom exception processor BEFORE format_exc_info
    # This gives us structured exception info
    processors.append(exception_processor)

    # Also keep format_exc_info for backwards compatibility and full traceback
    processors.append(structlog.processors.format_exc_info)  # type: ignore[arg-type]

    # Choose renderer based on environment
    # File logs are ALWAYS JSON (structured)
    # Console: pretty in debug mode, JSON in production
    if app_file_handler:
        # File logging enabled: use JSON for both stdout and file
        # This makes it easier to query logs with jq
        final_processors = processors + [structlog.processors.JSONRenderer()]
    else:
        # No file logging: use appropriate renderer for stdout
        if debug:
            final_processors = processors + [structlog.dev.ConsoleRenderer(colors=True)]
        else:
            final_processors = processors + [structlog.processors.JSONRenderer()]

    # Configure structlog
    # Use stdlib.LoggerFactory to integrate with Python's logging system
    # This ensures logs go to both stdout AND file handlers we configured
    # The loggers created will propagate to the root logger which has our handlers
    structlog.configure(
        processors=final_processors,
        wrapper_class=structlog.stdlib.BoundLogger,  # Use BoundLogger for stdlib integration
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    # Ensure root logger has the correct level so structlog loggers can propagate
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Log configuration
    logger = structlog.get_logger("comicarr.logging")
    app_log_file_path = logs_dir / "comicarr.json.log" if logs_dir else None
    db_log_file_path = logs_dir / "comicarr.db.json.log" if logs_dir else None
    http_log_file_path = logs_dir / "comicarr.http.json.log" if logs_dir else None

    # Verify database logger configuration
    db_loggers_configured = []
    if db_file_handler:
        db_loggers_configured = [
            "sqlalchemy",
            "sqlalchemy.engine",
            "sqlalchemy.engine.Engine",
            "sqlalchemy.pool",
            "sqlalchemy.dialects",
            "sqlite3",
            "aiosqlite",
        ]

    # Verify HTTP logger configuration
    http_loggers_configured = []
    if http_file_handler:
        http_loggers_configured = [
            "httpx",
            "httpcore",
            "httpcore.connection",
            "httpcore.http11",
        ]

    logger.info(
        "Logging configured",
        level=logging.getLevelName(log_level),
        debug=debug,
        app_file_logging=app_file_handler is not None,
        app_log_file=str(app_log_file_path) if app_log_file_path else None,
        db_file_logging=db_file_handler is not None,
        db_log_file=str(db_log_file_path) if db_log_file_path else None,
        db_log_level=logging.getLevelName(logging.INFO if debug else logging.WARNING),
        db_loggers_configured=db_loggers_configured,
        http_file_logging=http_file_handler is not None,
        http_log_file=str(http_log_file_path) if http_log_file_path else None,
        http_log_level=logging.getLevelName(logging.WARNING),
        http_loggers_configured=http_loggers_configured,
        note="Database logs will only appear if echo=True (debug mode) or if WARNING/ERROR occur. HTTP logs only show WARNING/ERROR by default.",
    )
