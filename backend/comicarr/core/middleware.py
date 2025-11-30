"""FastAPI middleware for request/response handling."""

from __future__ import annotations

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from comicarr.core.tracing import generate_trace_id, trace_context

logger = structlog.get_logger("comicarr.middleware")


class TracingMiddleware(BaseHTTPMiddleware):
    """Middleware to add trace IDs to all requests."""

    async def dispatch(self, request: Request, call_next):
        """Process request and add trace ID to context.

        Extracts trace ID from X-Trace-ID header if present, otherwise generates a new one.
        All logs during request processing will include this trace_id.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response with X-Trace-ID header added
        """
        # Check for existing trace ID in headers (for distributed tracing)
        trace_id = request.headers.get("X-Trace-ID")
        if not trace_id:
            trace_id = generate_trace_id()

        # Set trace ID in context for all logs during this request
        with trace_context(trace_id):
            logger.debug(
                "Processing request",
                method=request.method,
                path=request.url.path,
                trace_id=trace_id,
            )

            response = await call_next(request)

            # Add trace ID to response headers for client tracking
            response.headers["X-Trace-ID"] = trace_id

            logger.debug(
                "Request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                trace_id=trace_id,
            )

            return response
