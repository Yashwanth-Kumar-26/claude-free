"""FastAPI application factory for claudefree."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from backends.hub import get_hub
from settings.env import get_settings
from settings.logging import configure_logging

from .router import router
from .selector import ModelSelector
from .service import GatewayService
from .shortcuts import ShortcutHandler


@asynccontextmanager
async def _lifespan(app: FastAPI):
    cfg = get_settings()
    configure_logging(cfg.log_file)

    logger.info(
        "claudefree starting — host={}  port={}  default_backend={}",
        cfg.host,
        cfg.port,
        cfg.default_backend_id,
    )

    hub = get_hub()

    # Initialize dynamic providers from config.json
    await hub.async_init()

    selector = ModelSelector(cfg)
    shortcuts = ShortcutHandler(enabled=cfg.enable_shortcuts)
    svc = GatewayService(cfg, hub, selector, shortcuts)
    app.state.service = svc

    logger.success("claudefree ready ✓")
    yield

    # ── shutdown ──────────────────────────────────────────────────────────
    logger.info("claudefree shutting down…")
    await hub.cleanup_all()


def create_app() -> FastAPI:
    application = FastAPI(
        title="claudefree",
        description="Anthropic-compatible proxy to 8 LLM backends",
        version="3.0.0",
        lifespan=_lifespan,
    )

    application.include_router(router)

    @application.exception_handler(Exception)
    async def _generic_error(req: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled error: {}: {}", type(exc).__name__, exc)
        return JSONResponse(
            status_code=500,
            content={
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": f"Internal gateway error: {exc!s}",
                },
            },
        )

    return application


app = create_app()
