"""Temporary message send forbid rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Set


@dataclass
class MsgSendForbidObj:
    begTime: datetime
    endTime: datetime
    forbidType: str
    ips: Set[str] = field(default_factory=set)
    hosts: Set[str] = field(default_factory=set)
    channels: Set[str] = field(default_factory=set)
    contents: Set[str] = field(default_factory=set)
    alertCodes: Set[str] = field(default_factory=set)
    projects: Set[str] = field(default_factory=set)
