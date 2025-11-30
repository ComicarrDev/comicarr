"""Distributed tracing support using structlog contextvars."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager

import structlog
import structlog.contextvars as contextvars

logger = structlog.get_logger("comicarr.tracing")


def generate_trace_id() -> str:
    """Generate a unique trace ID.

    Returns:
        Hexadecimal trace ID (32 characters)
    """
    return uuid.uuid4().hex


def get_trace_id() -> str | None:
    """Get the current trace ID from context.

    Returns:
        Current trace ID or None if not set
    """
    return contextvars.get_contextvars().get("trace_id")


def set_trace_id(trace_id: str) -> None:
    """Set trace ID in context.

    Args:
        trace_id: Trace ID to set
    """
    contextvars.bind_contextvars(trace_id=trace_id)


def clear_trace_id() -> None:
    """Clear trace ID from context."""
    contextvars.clear_contextvars()


@contextmanager
def trace_context(trace_id: str | None = None) -> Generator[str]:
    """Context manager for trace ID.

    Sets trace_id in context, yields it, then clears context on exit.

    Args:
        trace_id: Optional trace ID to use. If None, generates a new one.

    Yields:
        The trace ID being used

    Example:
        >>> with trace_context() as trace_id:
        ...     logger.info("Processing request")  # Will include trace_id
    """
    old_context = dict(contextvars.get_contextvars())

    if trace_id is None:
        trace_id = generate_trace_id()

    contextvars.clear_contextvars()
    contextvars.bind_contextvars(trace_id=trace_id)

    try:
        yield trace_id
    finally:
        contextvars.clear_contextvars()
        # Restore old context if any
        if old_context:
            contextvars.bind_contextvars(**old_context)


def with_trace_id(trace_id: str):
    """Decorator to add trace ID to function context.

    Args:
        trace_id: Trace ID to use

    Example:
        >>> @with_trace_id("abc123")
        >>> async def process_job(job_id: str):
        ...     logger.info("Processing")  # Will include trace_id=abc123
    """

    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            with trace_context(trace_id):
                return await func(*args, **kwargs)

        def sync_wrapper(*args, **kwargs):
            with trace_context(trace_id):
                return func(*args, **kwargs)

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
