"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY


@pytest.fixture(autouse=True)
def reset_prometheus_registry():
    """Reset Prometheus registry before each test to avoid duplicate metric registration.

    This is needed because setup_metrics() registers metrics in the global Prometheus
    registry, and when multiple tests create apps, they would try to register the same
    metrics multiple times, causing "Duplicated timeseries" errors.
    """
    # Clear all collectors before each test
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)

    yield

    # Clean up after test as well
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
