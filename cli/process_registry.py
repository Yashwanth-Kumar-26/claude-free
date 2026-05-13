"""Process registry — track child processes for clean shutdown."""

from __future__ import annotations

import os
import signal
from collections import OrderedDict

from loguru import logger

_registry: OrderedDict[int, str] = OrderedDict()


def register(pid: int, label: str = "") -> None:
    _registry[pid] = label
    logger.debug("ProcessRegistry: registered pid={} label={!r}", pid, label)


def unregister(pid: int) -> None:
    _registry.pop(pid, None)


def kill_all_best_effort() -> None:
    for pid, label in list(_registry.items()):
        try:
            os.kill(pid, signal.SIGTERM)
            logger.info("ProcessRegistry: SIGTERM pid={} ({})", pid, label)
        except ProcessLookupError:
            pass
        except Exception as exc:
            logger.warning("ProcessRegistry: failed to kill {}: {}", pid, exc)
    _registry.clear()
