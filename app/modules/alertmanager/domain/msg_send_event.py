"""Container for dispatching messages to providers."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.alertmanager.domain.alert_item_record import AlertItemRecord
from app.modules.alertmanager.domain.msg_channel import MsgChannel
from app.modules.alertmanager.domain.msg_send_rules import MsgSendRules


@dataclass
class MsgSendEventBean:
    alertitemRecord: AlertItemRecord
    msg: str
    msgChannel: MsgChannel
    msgSendRules: MsgSendRules
