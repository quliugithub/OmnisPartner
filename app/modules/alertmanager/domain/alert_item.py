"""Alert metadata."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.alertmanager.util import AlertLevelType


@dataclass
class AlertItem:
    alertitem_code: str
    alertitem_desc: str = ""
    alertitem_solution: str = ""
    alertitem_level: str = AlertLevelType.UNKOWN.value
    alertitem_group: str = ""
    note: str = ""
