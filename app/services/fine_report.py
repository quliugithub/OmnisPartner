"""FineReport service translation."""

from __future__ import annotations

from .base import BaseService


class FineReportService(BaseService):
    async def do_data_sync(self) -> None:
        self.log.info("Synchronizing FineReport artifacts.")
