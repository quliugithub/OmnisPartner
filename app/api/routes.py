"""API routes for the FastAPI rewrite."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Health probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}
