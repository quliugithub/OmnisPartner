"""Wrapper exposing the AlertInfoCache implementation to the service container."""

from __future__ import annotations

from app.modules.alertmanager.cache import AlertInfoCache as AlertInfoCacheEngine

from .base import BaseService


class AlertInfoCache(BaseService):
    def __init__(self, settings, cache_engine: AlertInfoCacheEngine | None = None):
        super().__init__(settings)
        self._cache = cache_engine or AlertInfoCacheEngine.from_sample()

    async def init_all(self) -> None:
        await self._cache.init_all()

    def __getattr__(self, item):
        return getattr(self._cache, item)
