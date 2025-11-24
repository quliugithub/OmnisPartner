"""Deployment-related services."""

from __future__ import annotations

from .base import BaseService


class DeployInvoker(BaseService):
    async def invoke(self) -> None:
        self.log.info("Executing deployment workflow.")


class DeployInfoRefresh(BaseService):
    async def do_refresh_auto(self) -> None:
        self.log.info("Refreshing deployment metadata.")
