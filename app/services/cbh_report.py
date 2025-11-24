"""CBH report service port."""

from __future__ import annotations

from .base import BaseService


class CbhReportService(BaseService):
    async def init_sys_params(self) -> None:
        self.log.info("Initializing CBH report system parameters.")

    async def collect_data_to_db(self) -> None:
        self.log.info("Collecting CBH data snapshots into the CMS database.")
