"""Scoped rolling-window rate limiter with concurrency cap and 429 back-off."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any, ClassVar

from loguru import logger


class GlobalRateLimiter:
    """
    Per-backend rate limiter.

    - Proactive rolling window: enforces LIMIT req/WINDOW sec before sending.
    - Reactive 429 back-off: exponential sleep on upstream 429.
    - Concurrency cap: limits simultaneous open streams.
    """

    _instances: ClassVar[dict[str, GlobalRateLimiter]] = {}

    def __init__(
        self,
        name:            str,
        rate_limit:      int,
        rate_window:     int,
        max_concurrency: int,
    ) -> None:
        self._name            = name
        self._limit           = rate_limit
        self._window          = rate_window
        self._max_concurrency = max_concurrency
        self._timestamps:  deque[float]   = deque()
        self._lock:        asyncio.Lock   = asyncio.Lock()
        self._sem:         asyncio.Semaphore = asyncio.Semaphore(max_concurrency)
        self._backoff_until: float = 0.0
        self._backoff_delay: float = 1.0

    @classmethod
    def scoped(
        cls,
        name:            str,
        rate_limit:      int,
        rate_window:     int,
        max_concurrency: int,
    ) -> GlobalRateLimiter:
        if name not in cls._instances:
            cls._instances[name] = cls(name, rate_limit, rate_window, max_concurrency)
        return cls._instances[name]

    def signal_upstream_429(self) -> None:
        self._backoff_until = time.monotonic() + self._backoff_delay
        self._backoff_delay = min(self._backoff_delay * 2, 60.0)

    def _reset_backoff(self) -> None:
        self._backoff_delay = 1.0

    async def _wait_for_slot(self) -> None:
        async with self._lock:
            now = time.monotonic()

            # reactive back-off
            if now < self._backoff_until:
                wait = self._backoff_until - now
                logger.warning("{} rate-limiter: 429 backoff {:.1f}s", self._name, wait)
                await asyncio.sleep(wait)

            # proactive rolling window
            cutoff = now - self._window
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()

            if len(self._timestamps) >= self._limit:
                oldest = self._timestamps[0]
                sleep  = (oldest + self._window) - time.monotonic() + 0.05
                if sleep > 0:
                    logger.info("{} rate-limiter: proactive wait {:.2f}s", self._name, sleep)
                    await asyncio.sleep(sleep)

            self._timestamps.append(time.monotonic())
            self._reset_backoff()

    async def execute_with_retry(
        self,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        await self._wait_for_slot()
        return await fn(*args, **kwargs)

    @asynccontextmanager
    async def concurrency_slot(self):
        async with self._sem:
            yield
