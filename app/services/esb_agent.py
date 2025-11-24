"""Translation of ESB agent background tasks."""

from __future__ import annotations

from .base import BaseService


class EsbAgentService(BaseService):
    async def do_data_sync(self) -> None:
        self.log.info("Synchronizing data with ESB cache database.")

    async def do_ens_messageheader_hour_init(self) -> None:
        self.log.info("Initializing ENS message headers for the current hour.")
