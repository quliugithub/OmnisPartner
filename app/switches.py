"""Feature toggle helpers mirroring `OmnisSwitch` from the Java codebase."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .settings import Settings

log = logging.getLogger(__name__)


@dataclass
class OmnisSwitch:
    """Lightweight translation of the Spring component."""

    settings: Settings

    def websql_on(self) -> bool:
        return bool(self.settings.omnis_switch_websql)

    def alert_manager_on(self) -> bool:
        return bool(self.settings.omnis_switch_alertmanager)

    def alert_recovery_on(self) -> bool:
        return bool(self.settings.omnis_switch_alertrecovery)

    def deploy_on(self) -> bool:
        return bool(self.settings.omnis_switch_deploy)

    def esb_agent_on(self) -> bool:
        enabled = bool(self.settings.omnis_switch_esbagent)
        if not enabled:
            return False

        missing = [
            name
            for name in (
                "esbagent_cachedb_url",
                "esbagent_cachedb_username",
                "esbagent_cachedb_password",
                "esbagent_project",
            )
            if not getattr(self.settings, name)
        ]
        if missing:
            log.info("ESB Agent requires %s, disabling sync.", ", ".join(missing))
            return False
        return True

    def finereport_on(self) -> bool:
        enabled = bool(self.settings.omnis_switch_finereport)
        if not enabled:
            return False

        missing = [
            name
            for name in ("finereport_db_url", "finereport_db_username")
            if not getattr(self.settings, name)
        ]
        if missing:
            log.info("FineReport requires %s, disabling sync.", ", ".join(missing))
            return False
        return True

    def cbh_report_on(self) -> bool:
        enabled = bool(self.settings.omnis_switch_cbhreport)
        if not enabled:
            return False

        missing = [
            name
            for name in ("cbh_cms_db_url", "cbh_cms_db_username", "cbh_cms_db_password")
            if not getattr(self.settings, name)
        ]
        if missing:
            log.info("CBH report requires %s, disabling sync.", ", ".join(missing))
            return False
        return True
