"""Alert recovery service port."""

from __future__ import annotations

from .base import BaseService


class RecoveryService(BaseService):
    async def init(self) -> None:
        self.log.info("Initializing alert recovery routines.")
