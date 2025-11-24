"""Translation of `AfterServerStartInit`."""

from __future__ import annotations

from .base import BaseService


class AfterServerStartInit(BaseService):
    async def do_init(self) -> None:
        self.log.info("Executing generic startup initialization.")

    async def do_init_websql(self) -> None:
        self.log.info("Initializing WebSQL module.")
