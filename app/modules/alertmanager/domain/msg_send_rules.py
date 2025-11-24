"""Message send rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from app.modules.alertmanager.domain.msg_channel import MsgChannel


@dataclass
class MsgSendRules:
    msg_send_rule_id: str
    send_rule_group_id: str
    alertitem_code: str
    repeat_send_interval: int = 0
    repeat_send_interval_maxtime: int = 0
    same_alert_resend_mintime: int = 0
    valid_time_begin: str | None = None
    valid_time_end: str | None = None
    is_forbid: str = "0"
    recover_msg_notsend: int = 0
    alertitem_notshow: int = 0
    msg_fmt: str | None = None
    msgChannels: List[MsgChannel] = field(default_factory=list)
