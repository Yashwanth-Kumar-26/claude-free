"""Auth dependency — Bearer token validation."""

from __future__ import annotations

from fastapi import Header, HTTPException, Request
from loguru import logger


async def require_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    """Validate Bearer token if ANTHROPIC_AUTH_TOKEN is configured."""
    from settings.env import get_settings

    token = get_settings().auth_token
    if not token:
        return  # auth disabled

    provided: str | None = None
    if authorization:
        auth_lower = authorization.lower().strip()
        provided = (
            authorization[7:].strip()
            if auth_lower.startswith("bearer ")
            else authorization.strip()
        )

    # Fallback to x-api-key header
    if not provided:
        provided = request.headers.get("x-api-key", "").strip()

    if provided != token:
        # Strip surrounding quotes that some clients include (e.g. '"fr"' → 'fr')
        provided_stripped = provided.strip('"\'') if provided else provided
        if provided_stripped == token:
            logger.debug("AUTH: request authorized (quoted token stripped)")
            return
        logger.warning(
            "AUTH: rejected - provided='{}' ({}) vs token='{}' ({})",
            provided,
            len(provided) if provided else 0,
            token,
            len(token) if token else 0,
        )
        raise HTTPException(status_code=401, detail="Invalid auth token")

    logger.debug("AUTH: request authorized")
