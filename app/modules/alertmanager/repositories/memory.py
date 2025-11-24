"""In-memory repository implementation."""

from __future__ import annotations

import itertools
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Sequence

from app.modules.alertmanager.domain import AlertItemRecord
from app.modules.alertmanager.repositories.base import AlertManagerRepository
from app.modules.alertmanager.util import AlertManagerConstant


class InMemoryAlertManagerRepository(AlertManagerRepository):
    """Simple storage so the FastAPI port behaves without a database."""

    def __init__(self) -> None:
        self.records: Dict[str, AlertItemRecord] = {}

    def save_record(self, record: AlertItemRecord) -> None:
        self.records[record.alertitem_record_id] = record

    def mark_recovered(self, record: AlertItemRecord) -> int:
        stored = self.records.get(record.alertitem_record_id)
        if not stored:
            return 0
        stored.is_recover = AlertManagerConstant.IS_RECOVER_YES
        stored.recover_time = record.recover_time
        stored.event_type = AlertManagerConstant.EVENT_TYPE_RECOVER
        return 1

    def get_record(self, record_id: str) -> AlertItemRecord | None:
        return self.records.get(record_id)

    def query_repeat_candidates(self) -> Sequence[dict]:
        open_records = [
            r
            for r in self.records.values()
            if r.event_type == AlertManagerConstant.EVENT_TYPE_CREATE
            and r.is_recover == AlertManagerConstant.IS_RECOVER_NO
        ]
        grouped = defaultdict(list)
        for record in open_records:
            key = (record.hostip, record.alertitem_code, record.project)
            grouped[key].append(record)

        result: List[dict] = []
        for records in grouped.values():
            if len(records) <= 1:
                continue
            sorted_records = sorted(records, key=lambda r: r.add_time)
            for rec in itertools.islice(sorted_records, 0, len(sorted_records) - 1):
                result.append(
                    {
                        "hostip": rec.hostip,
                        "alertitem_code": rec.alertitem_code,
                        "addtime": rec.add_time,
                        "project": rec.project,
                    }
                )
        return result

    def confirm_repeat(self, hostip: str, alert_code: str, add_time: datetime, project: str) -> None:
        for record in self.records.values():
            if (
                record.hostip == hostip
                and record.alertitem_code == alert_code
                and record.project == project
                and record.add_time == add_time
            ):
                record.is_confirm = AlertManagerConstant.CONFIRM_YES
