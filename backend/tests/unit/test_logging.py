"""Tests for logging functionality."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import structlog

from comicarr.core.logging import (
    ExcInfo,
    format_exception_for_json,
    setup_logging,
)

if TYPE_CHECKING:
    pass


def test_format_exception_for_json_with_exception() -> None:
    """Test format_exception_for_json with a real exception."""
    try:
        raise ValueError("Test error message")
    except ValueError:
        exc_info: ExcInfo = sys.exc_info()  # type: ignore[assignment]

    result = format_exception_for_json(exc_info)

    assert isinstance(result, dict)
    assert result["exception_type"] == "ValueError"
    assert result["exception_message"] == "Test error message"
    assert result["exception_module"] == "builtins"
    assert "traceback_frames" in result
    assert isinstance(result["traceback_frames"], list)
    assert len(result["traceback_frames"]) > 0

    # Check traceback frame structure
    frame = result["traceback_frames"][0]
    assert "filename" in frame
    assert "lineno" in frame
    assert "function" in frame
    assert isinstance(frame["filename"], str)
    assert isinstance(frame["lineno"], int)
    assert isinstance(frame["function"], str)

    # Check traceback text is present
    assert "traceback_text" in result
    assert isinstance(result["traceback_text"], str)
    assert "ValueError: Test error message" in result["traceback_text"]


def test_format_exception_for_json_with_none() -> None:
    """Test format_exception_for_json with None."""
    result = format_exception_for_json(None)
    assert result == {}


def test_format_exception_for_json_with_empty_tuple() -> None:
    """Test format_exception_for_json with empty exception tuple."""
    result = format_exception_for_json((None, None, None))
    assert result == {}


def test_setup_logging_debug_mode() -> None:
    """Test setup_logging in debug mode."""
    setup_logging(debug=True)

    logger = structlog.get_logger("test.logger")
    logger.info("Test message", key="value")

    # In debug mode, we should have console renderer
    # This is harder to test directly, so we just verify it doesn't crash


def test_setup_logging_production_mode() -> None:
    """Test setup_logging in production mode."""
    setup_logging(debug=False)

    logger = structlog.get_logger("test.logger")
    logger.info("Test message", key="value")

    # In production mode, we should have JSON renderer
    # This is harder to test directly, so we just verify it doesn't crash


def test_exception_logging_in_json() -> None:
    """Test that exceptions are logged in structured JSON format."""
    import io
    import sys

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()

    try:
        setup_logging(debug=False)
        logger = structlog.get_logger("test.logger")

        try:
            raise ValueError("Test error")
        except ValueError:
            logger.exception("An error occurred", extra="context")

        # Get output
        output = sys.stdout.getvalue()

        # Parse JSON
        lines = output.strip().split("\n")
        json_lines = [line for line in lines if line.strip().startswith("{")]

        assert len(json_lines) > 0, "Should have at least one JSON log line"

        # Parse the last JSON line (should be the exception)
        log_data = json.loads(json_lines[-1])

        # Check structure
        assert "event" in log_data
        assert "exception" in log_data
        assert isinstance(log_data["exception"], dict)

        # Check exception details
        exc_details = log_data["exception"]
        assert exc_details["exception_type"] == "ValueError"
        assert exc_details["exception_message"] == "Test error"
        assert "traceback_frames" in exc_details
        assert "traceback_text" in exc_details

        # Check exception summary
        assert "exception_summary" in log_data
        assert "ValueError: Test error" in log_data["exception_summary"]

    finally:
        sys.stdout = old_stdout


def test_logging_with_trace_id() -> None:
    """Test that logging includes trace_id from context."""
    import io
    import sys

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()

    try:
        setup_logging(debug=False)

        # Set trace ID in context
        structlog.contextvars.bind_contextvars(trace_id="test-trace-123")

        logger = structlog.get_logger("test.logger")
        logger.info("Test message", key="value")

        # Get output
        output = sys.stdout.getvalue()

        # Parse JSON
        lines = output.strip().split("\n")
        json_lines = [line for line in lines if line.strip().startswith("{")]

        assert len(json_lines) > 0

        # Parse JSON
        log_data = json.loads(json_lines[-1])

        # Check trace_id is present
        assert "trace_id" in log_data
        assert log_data["trace_id"] == "test-trace-123"

    finally:
        sys.stdout = old_stdout
        structlog.contextvars.clear_contextvars()
