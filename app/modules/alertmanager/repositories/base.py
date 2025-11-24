"""Repository contracts for AlertManager persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from app.modules.alertmanager.domain import AlertItemRecord


class AlertManagerRepository:
    def save_record(self, record: AlertItemRecord) -> None:
        raise NotImplementedError

    def mark_recovered(self, record: AlertItemRecord) -> int:
        raise NotImplementedError

    def get_record(self, record_id: str) -> AlertItemRecord | None:
        raise NotImplementedError

    def query_repeat_candidates(self) -> Sequence[dict]:
        raise NotImplementedError

    def confirm_repeat(self, hostip: str, alert_code: str, add_time: datetime, project: str) -> None:
        raise NotImplementedError
