"""Shared ComicVine API client with rate limiting, retry logic, and caching."""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from collections import deque
from pathlib import Path
from typing import Any
from urllib import parse as urllib_parse

import httpx
import structlog

logger = structlog.get_logger("comicarr.core.comicvine.client")


class ComicVineClient:
    """Shared ComicVine API client with rate limiting, retry logic, and caching.

    Features:
    - Rate limiting with configurable limits
    - Exponential backoff retry on rate limit errors (HTTP 420, 429)
    - Response caching to disk
    - Consistent error handling
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://comicvine.gamespot.com/api",
        rate_limit: int = 40,  # requests per period
        rate_limit_period: int = 60,  # seconds
        max_retries: int = 3,
        cache_dir: Path | None = None,
        cache_enabled: bool = True,
        burst_prevention_enabled: bool = True,
        min_gap_seconds: float | None = None,
    ):
        """Initialize ComicVine client.

        Args:
            api_key: ComicVine API key
            base_url: ComicVine API base URL
            rate_limit: Maximum requests per rate_limit_period
            rate_limit_period: Time window in seconds for rate limiting
            max_retries: Maximum number of retries on rate limit errors
            cache_dir: Directory for caching responses (default: data/cache/comicvine)
            cache_enabled: Whether to enable response caching
            burst_prevention_enabled: Whether to enable burst prevention during slow start
            min_gap_seconds: Minimum gap between requests during burst prevention.
                           If None, auto-calculates as rate_limit_period / rate_limit
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.rate_limit = rate_limit
        self.rate_limit_period = rate_limit_period
        self.max_retries = max_retries
        self.cache_enabled = cache_enabled
        self.burst_prevention_enabled = burst_prevention_enabled
        self.min_gap_seconds = min_gap_seconds

        # Rate limiting: track request timestamps
        # Initialize as empty - will be populated as requests come in
        self._request_times: deque[float] = deque()
        self._rate_limit_lock = asyncio.Lock()

        # Setup cache directory
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent.parent / "data" / "cache" / "comicvine"
        self.cache_dir = cache_dir
        if self.cache_enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, endpoint: str, params: dict[str, Any]) -> str:
        """Generate cache key from endpoint and params."""
        # Sort params for consistent hashing
        sorted_params = sorted(params.items())
        cache_data = f"{endpoint}:{json.dumps(sorted_params, sort_keys=True)}"
        return hashlib.sha256(cache_data.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get cache file path for a cache key."""
        return self.cache_dir / f"{cache_key}.json"

    def is_cached(self, endpoint: str, params: dict[str, Any]) -> bool:
        """Check if a request is cached without loading it.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            True if cached, False otherwise
        """
        if not self.cache_enabled:
            return False

        cache_key = self._get_cache_key(endpoint, params)
        cache_path = self._get_cache_path(cache_key)
        return cache_path.exists()

    async def _load_from_cache(self, cache_key: str) -> dict[str, Any] | None:
        """Load response from cache if available."""
        if not self.cache_enabled:
            return None

        cache_path = self._get_cache_path(cache_key)
        if not cache_path.exists():
            return None

        try:
            with open(cache_path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load cache", cache_key=cache_key, error=str(e))
            return None

    def _save_to_cache(self, cache_key: str, data: dict[str, Any]) -> None:
        """Save response to cache."""
        if not self.cache_enabled:
            return

        try:
            cache_path = self._get_cache_path(cache_key)
            with open(cache_path, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning("Failed to save cache", cache_key=cache_key, error=str(e))

    async def _wait_for_rate_limit(self) -> None:
        """Wait if rate limit would be exceeded.

        Uses a "slow start" approach: applies spacing only when we have
        few requests in the window (startup phase), then transitions to
        normal rate limiting once we have enough history.

        This method ensures that:
        1. We never exceed the rate limit (requests per period)
        2. Startup bursts are prevented without slowing down the entire queue
        3. Concurrent requests are properly serialized via the lock
        """
        async with self._rate_limit_lock:
            now = time.time()

            # Remove old timestamps outside the rate limit window
            while self._request_times and self._request_times[0] < now - self.rate_limit_period:
                self._request_times.popleft()

            # Check if we need to wait before making this request
            # We check BEFORE recording to prevent going over the limit
            if len(self._request_times) >= self.rate_limit:
                # We're at the limit - wait until the oldest request expires
                oldest_time = self._request_times[0]
                wait_time = oldest_time + self.rate_limit_period - now + 0.1  # Add small buffer
                if wait_time > 0:
                    logger.debug(
                        "Rate limit reached, waiting",
                        wait_seconds=wait_time,
                        current_count=len(self._request_times),
                    )
                    await asyncio.sleep(wait_time)
                    # Clean up again after waiting
                    now = time.time()
                    while (
                        self._request_times
                        and self._request_times[0] < now - self.rate_limit_period
                    ):
                        self._request_times.popleft()

            # Burst prevention: apply spacing to prevent bursts during slow start
            # Only applies if burst_prevention_enabled is True
            if self.burst_prevention_enabled and self._request_times:
                time_since_last = now - self._request_times[-1]
                window_age = now - self._request_times[0]

                # Calculate minimum spacing (use configured value or auto-calculate)
                if self.min_gap_seconds is not None:
                    min_spacing = self.min_gap_seconds
                else:
                    min_spacing = self.rate_limit_period / self.rate_limit

                # Apply spacing only during first 50% of window period
                # This prevents bursts at startup without slowing down regular execution
                if window_age < (self.rate_limit_period * 0.5):
                    # Spacing decreases linearly from 100% to 20% as window ages
                    age_factor = window_age / (self.rate_limit_period * 0.5)
                    # Start at 100% spacing, reduce to 20% as window ages
                    effective_spacing = min_spacing * (1.0 - age_factor * 0.8)  # 100% to 20%

                    # Enforce spacing if we're too close to the last request
                    if time_since_last < effective_spacing:
                        spacing_delay = effective_spacing - time_since_last
                        if spacing_delay > 0.01:  # Only wait if significant (>10ms)
                            logger.debug(
                                "Burst prevention: spacing out requests",
                                delay_seconds=spacing_delay,
                                requests_in_window=len(self._request_times),
                                window_age=window_age,
                                min_spacing=min_spacing,
                            )
                            await asyncio.sleep(spacing_delay)
                            now = time.time()  # Update now after delay

            # Record this request BEFORE releasing the lock
            # This ensures the next request will see this one in the queue
            self._request_times.append(now)

    def _build_url(self, endpoint: str, params: dict[str, Any]) -> str:
        """Build ComicVine API URL."""
        endpoint_path = endpoint.strip("/")
        url = f"{self.base_url}/{endpoint_path}/"
        request_params = {"format": "json", **params}
        request_params["api_key"] = self.api_key
        query = urllib_parse.urlencode(request_params)
        return f"{url}?{query}"

    async def fetch(
        self,
        endpoint: str,
        params: dict[str, Any],
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Fetch data from ComicVine API with rate limiting, retry, and caching.

        Args:
            endpoint: API endpoint (e.g., "volume/4050-12345" or "search")
            params: Query parameters (api_key will be added automatically)
            use_cache: Whether to use cached responses if available

        Returns:
            JSON response from ComicVine API

        Raises:
            httpx.HTTPStatusError: For HTTP errors (after retries)
            httpx.RequestError: For network errors
        """
        # Check cache first - if cached, return immediately without rate limit wait
        cache_key = self._get_cache_key(endpoint, params)
        if use_cache:
            cached = await self._load_from_cache(cache_key)
            if cached is not None:
                logger.debug("Using cached response", endpoint=endpoint, cache_key=cache_key[:8])
                return cached

        # Only wait for rate limit if we need to make an API call
        await self._wait_for_rate_limit()

        url = self._build_url(endpoint, params)
        safe_url = url.split("api_key=")[0] + "api_key=***" if "api_key=" in url else url
        logger.debug("Calling ComicVine API", endpoint=endpoint, url=safe_url)

        # Retry logic with exponential backoff
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(
                        url,
                        headers={
                            "User-Agent": "Comicarr/0.1 (+https://github.com/agnlopes/comicarr)",
                            "Accept": "application/json",
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                    # Save to cache
                    if use_cache:
                        self._save_to_cache(cache_key, data)

                    return data

            except httpx.HTTPStatusError as e:
                last_exception = e
                # Retry on rate limit errors (420, 429)
                if e.response.status_code in (420, 429) and attempt < self.max_retries:
                    # Exponential backoff: 2^attempt seconds
                    # Add jitter to prevent thundering herd: random 0-50% of wait time
                    base_wait = 2**attempt
                    jitter = random.uniform(0, base_wait * 0.5)
                    wait_time = base_wait + jitter
                    logger.warning(
                        "Rate limited by ComicVine, retrying",
                        status_code=e.response.status_code,
                        attempt=attempt + 1,
                        wait_seconds=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    # Also wait for our rate limit window (this will apply slow start if needed)
                    await self._wait_for_rate_limit()
                    continue
                # For other HTTP errors, don't retry
                raise

            except httpx.RequestError as e:
                last_exception = e
                # Retry on network errors
                if attempt < self.max_retries:
                    wait_time = 2**attempt
                    logger.warning(
                        "Network error, retrying",
                        error=str(e),
                        attempt=attempt + 1,
                        wait_seconds=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise

        # Should never reach here, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected error in ComicVine client")


# Global client instance (will be initialized on first use)
_client: ComicVineClient | None = None


def get_comicvine_client(settings: dict[str, Any] | None = None) -> ComicVineClient:
    """Get or create the global ComicVine client instance.

    Args:
        settings: ComicVine settings dict with api_key, base_url, rate_limit, etc.
                  If None, will fetch from settings.

    Returns:
        ComicVineClient instance
    """
    global _client

    if settings is None:
        from comicarr.routes.comicvine import normalize_comicvine_payload
        from comicarr.routes.settings import _get_external_apis

        external_apis = _get_external_apis()
        settings = normalize_comicvine_payload(external_apis.get("comicvine", {}))

    # Check if we need to recreate the client (settings changed)
    if _client is None or (
        _client.api_key != settings.get("api_key")
        or _client.base_url != settings.get("base_url", "https://comicvine.gamespot.com/api")
        or _client.rate_limit != settings.get("rate_limit", 40)
        or _client.rate_limit_period != settings.get("rate_limit_period", 60)
        or _client.burst_prevention_enabled != settings.get("burst_prevention_enabled", True)
        or _client.min_gap_seconds != settings.get("min_gap_seconds")
    ):
        _client = ComicVineClient(
            api_key=settings.get("api_key", ""),
            base_url=settings.get("base_url", "https://comicvine.gamespot.com/api"),
            rate_limit=settings.get("rate_limit", 40),
            rate_limit_period=settings.get("rate_limit_period", 60),
            max_retries=settings.get("max_retries", 3),
            cache_enabled=settings.get("cache_enabled", True),
            burst_prevention_enabled=settings.get("burst_prevention_enabled", True),
            min_gap_seconds=settings.get("min_gap_seconds"),
        )
        # Reset request times when creating new client to clear any stale state
        _client._request_times.clear()

    return _client
