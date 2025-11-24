"""Database event operator translation."""

from __future__ import annotations

from .base import BaseService


class DbEventOperatorService(BaseService):
    async def add_event_to_project_queue_from_db(self) -> None:
        self.log.info("Loading pending DB events into the in-memory queue.")

    async def auto_do_url_proxy_event(self) -> None:
        self.log.info("Executing queued URL proxy events.")
