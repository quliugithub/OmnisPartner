"""Placeholder for the Java NexusManagerService file transfer step."""

from __future__ import annotations

import logging

from app.modules.deployfilemanage.domain import DepFileGetReplaceResponse

log = logging.getLogger(__name__)


class NexusTransferService:
    """Stub that logs the transfer request for future implementation."""

    def send_files(self, response: DepFileGetReplaceResponse) -> None:
        if not response or not response.final_files:
            return
        log.info(
            "Nexus transfer stub invoked for %s files. Configure remote sync if required.",
            len(response.final_files),
        )
