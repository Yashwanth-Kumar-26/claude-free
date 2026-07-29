"""FastAPI route definitions for the Anthropic-compatible gateway."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from loguru import logger

from .auth import require_auth
from .schemas import (
    MessagesRequest,
    ModelInfo,
    ModelListResponse,
    TokenCountRequest,
)
from .service import GatewayService
from .stats import get_stats

router = APIRouter()


def _get_service(request: Request) -> GatewayService:
    return request.app.state.service


# ── /v1/messages ─────────────────────────────────────────────────────────────


@router.post(
    "/v1/messages",
    dependencies=[Depends(require_auth)],
    summary="Create a message (Anthropic-compatible)",
)
async def create_message(
    body: MessagesRequest,
    request: Request,
) -> StreamingResponse:
    svc = _get_service(request)
    rid = request.headers.get("x-request-id") or request.headers.get("request-id")

    async def _event_stream() -> AsyncIterator[bytes]:
        # Claude Code cancels an in-flight turn when Esc is pressed.  Make the
        # downstream connection authoritative: do not start (or keep) an
        # expensive upstream request after the client has gone away.
        if await request.is_disconnected():
            logger.info("STREAM CANCELLED before start rid={}", rid)
            return

        t0 = time.monotonic()
        chunks = 0
        cancelled = False
        stream = svc.stream(body, request_id=rid)
        try:
            async for chunk in stream:
                if await request.is_disconnected():
                    cancelled = True
                    logger.info("STREAM CANCELLED by client rid={}", rid)
                    return
                yield chunk.encode("utf-8")
                chunks += 1
        except asyncio.CancelledError:
            cancelled = True
            logger.info("STREAM CANCELLED by client rid={}", rid)
            raise
        finally:
            # Explicitly close the whole adapter chain.  This closes httpx
            # streaming responses too, so a cancelled turn cannot continue
            # consuming the old prompt in the background.
            await stream.aclose()
            logger.info(
                "STREAM {}: chunks={} elapsed={:.2f}s rid={}",
                "CANCELLED" if cancelled else "DONE",
                chunks,
                time.monotonic() - t0,
                rid,
            )

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ── /v1/messages/count_tokens ─────────────────────────────────────────────────


@router.post(
    "/v1/messages/count_tokens",
    dependencies=[Depends(require_auth)],
    summary="Count input tokens",
)
async def count_tokens_endpoint(
    body: TokenCountRequest,
    request: Request,
) -> JSONResponse:
    svc = _get_service(request)
    resp = svc.count_tokens(body)
    return JSONResponse(resp.model_dump())


# ── /v1/models ───────────────────────────────────────────────────────────────


@router.get(
    "/v1/models",
    dependencies=[Depends(require_auth)],
    summary="List available Claude model aliases",
)
async def list_models(request: Request) -> JSONResponse:
    models = [
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        "claude-3-7-sonnet-20250219",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
        "claude-opus-4-0",
    ]
    data = [ModelInfo(id=m) for m in models]
    return JSONResponse(ModelListResponse(data=data).model_dump())


# ── /v1/providers ────────────────────────────────────────────────────────────────


@router.get(
    "/v1/providers",
    dependencies=[Depends(require_auth)],
    summary="List available providers from models.dev",
)
async def list_providers(request: Request) -> JSONResponse:
    """List all available providers from models.dev."""
    from backends.provider_registry import get_registry

    registry = get_registry()
    try:
        providers = await registry.fetch_providers()
        provider_ids = list(providers.keys())
        return JSONResponse(
            {
                "providers": provider_ids,
                "count": len(provider_ids),
            }
        )
    except Exception as e:
        logger.error("Failed to fetch providers: {}", e)
        raise HTTPException(
            status_code=500, detail="Failed to fetch providers from models.dev"
        ) from e


# ── /v1/models/providers ─────────────────────────────────────────────────────────


@router.get(
    "/v1/models/providers",
    dependencies=[Depends(require_auth)],
    summary="Get models for a specific provider",
)
async def get_provider_models(provider_id: str, request: Request) -> JSONResponse:
    """Get all models available for a specific provider."""
    from backends.provider_registry import get_registry

    registry = get_registry()
    try:
        providers = await registry.fetch_providers()
        provider_data = providers.get(provider_id)

        if not provider_data:
            raise HTTPException(
                status_code=404, detail=f"Provider '{provider_id}' not found"
            )

        models = provider_data.get("models", {})
        model_list = list(models.keys())

        return JSONResponse(
            {
                "provider": provider_id,
                "provider_name": provider_data.get("name", provider_id),
                "models": model_list,
                "count": len(model_list),
                "api_url": provider_data.get("api"),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch provider models: {}", e)
        raise HTTPException(status_code=500, detail="Failed to fetch provider models") from e


# ── health & stats ────────────────────────────────────────────────────────────


@router.get("/health", include_in_schema=False)
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "claudefree"})


@router.get(
    "/stats", dependencies=[Depends(require_auth)], summary="Get gateway statistics"
)
async def stats_endpoint() -> JSONResponse:
    return JSONResponse(get_stats().get_summary())


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root_ui(request: Request) -> str:
    from backends.hub import BACKEND_DESCRIPTORS
    from settings.env import get_settings

    cfg = get_settings()
    summary = get_stats().get_summary()
    uptime = summary["uptime_seconds"]
    h = uptime // 3600
    m = (uptime % 3600) // 60
    s = uptime % 60

    backend_rows = ""
    for bid, desc in BACKEND_DESCRIPTORS.items():
        stats = summary["backends"].get(
            bid, {"requests": 0, "errors": 0, "avg_latency_ms": 0}
        )
        status_class = (
            "success"
            if stats["errors"] == 0
            else "warning"
            if stats["errors"] < stats["requests"] * 0.1
            else "error"
        )
        backend_rows += f"""
        <tr>
            <td><strong>{desc.label}</strong><br><small>{bid}</small></td>
            <td>{stats["requests"]}</td>
            <td><span class="status-{status_class}">{stats["errors"]}</span></td>
            <td>{stats["avg_latency_ms"]}ms</td>
            <td>{"healthy" if stats["requests"] > 0 and stats["errors"] == 0 else "idle"}</td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>claudefree gateway</title>
        <style>
            :root {{
                --bg: #0f172a;
                --card: #1e293b;
                --text: #f8fafc;
                --accent: #38bdf8;
                --success: #22c55e;
                --warning: #eab308;
                --error: #ef4444;
            }}
            body {{
                font-family: 'Inter', system-ui, -apple-system, sans-serif;
                background: var(--bg);
                color: var(--text);
                margin: 0;
                display: flex;
                flex-direction: column;
                align-items: center;
                min-height: 100vh;
            }}
            header {{
                width: 100%;
                padding: 2rem 0;
                text-align: center;
                background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
                border-bottom: 1px solid #334155;
            }}
            h1 {{ margin: 0; font-size: 2.5rem; letter-spacing: -0.025em; color: var(--accent); }}
            .container {{ width: 90%; max-width: 1000px; margin: 2rem 0; }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 1.5rem;
                margin-bottom: 2rem;
            }}
            .card {{
                background: var(--card);
                padding: 1.5rem;
                border-radius: 12px;
                border: 1px solid #334155;
                box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
            }}
            .card h3 {{ margin: 0 0 0.5rem 0; color: #94a3b8; font-size: 0.875rem; text-transform: uppercase; }}
            .card p {{ margin: 0; font-size: 1.5rem; font-weight: 700; }}

            table {{
                width: 100%;
                border-collapse: collapse;
                background: var(--card);
                border-radius: 12px;
                overflow: hidden;
                border: 1px solid #334155;
            }}
            th {{ background: #334155; color: #94a3b8; text-align: left; padding: 1rem; font-size: 0.75rem; text-transform: uppercase; }}
            td {{ padding: 1rem; border-bottom: 1px solid #334155; }}
            tr:last-child td {{ border-bottom: none; }}
            small {{ color: #64748b; }}
            .status-success {{ color: var(--success); }}
            .status-warning {{ color: var(--warning); }}
            .status-error {{ color: var(--error); }}
            .footer {{ margin-top: auto; padding: 2rem; color: #64748b; font-size: 0.875rem; }}
        </style>
    </head>
    <body>
        <header>
            <h1>claudefree <small style="color:white; font-size: 1rem;">v3.0.0</small></h1>
            <p>Anthropic-compatible Gateway</p>
        </header>

        <div class="container">
            <div class="stats-grid">
                <div class="card">
                    <h3>Uptime</h3>
                    <p>{h}h {m}m {s}s</p>
                </div>
                <div class="card">
                    <h3>Default Backend</h3>
                    <p>{cfg.default_backend_id}</p>
                </div>
                <div class="card">
                    <h3>Total Backends</h3>
                    <p>{len(BACKEND_DESCRIPTORS)}</p>
                </div>
                <div class="card">
                  <h3>Endpoint</h3>
                  <p>:{cfg.port}/v1/messages</p>
                </div>
            </div>

            <div class="card" style="padding: 0;">
                <table>
                    <thead>
                        <tr>
                            <th>Backend</th>
                            <th>Requests</th>
                            <th>Errors</th>
                            <th>Avg Latency</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {backend_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="footer">
            Running on {cfg.host}:{cfg.port} • Protecting your Claude Code quota since 2026
        </div>
    </body>
    </html>
    """
