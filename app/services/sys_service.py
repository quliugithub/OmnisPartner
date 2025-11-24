"""Translation of `SysService` interactions."""

from __future__ import annotations

from .base import BaseService


class SysService(BaseService):
    async def register_myself(self, version: str) -> None:
        self.log.info("Registering service instance with version %s.", version)

    async def register_to_center(self) -> None:
        self.log.info("Registering service instance with central registry.")
