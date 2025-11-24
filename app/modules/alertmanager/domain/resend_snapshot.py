"""Snapshot used for repeated message sending."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.alertmanager.domain.alert_item_record import AlertItemRecord
from app.modules.alertmanager.domain.msg_channel import MsgChannel
from app.modules.alertmanager.domain.msg_send_rules import MsgSendRules


@dataclass
class ReSendInfoSnapshot:
    msgSendRules: MsgSendRules
    msgChannel: MsgChannel
    record: AlertItemRecord
    msg: str
    sendCount: int = 0
    lastSendTime: float = 0.0
    currentChannelType: str | None = None
