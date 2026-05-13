"""Loguru-based logging configuration."""

from __future__ import annotations

import sys

from loguru import logger


def configure_logging(log_file: str = "claudefree.log") -> None:
    logger.remove()

    # Console — colorful, compact
    logger.add(
        sys.stderr,
        level="DEBUG",
        colorize=True,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
    )

    # Rotating file — verbose
    if log_file:
        logger.add(
            log_file,
            level="DEBUG",
            rotation="100 MB",
            retention="7 days",
            compression="gz",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} — {message}",
            enqueue=True,
        )

    logger.info("Logging configured — file={}", log_file)
