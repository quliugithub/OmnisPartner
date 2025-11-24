"""Message synchronization payload."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SyncMsgBean:
    msg: str
    projectIdentify: str
    msgType: int
