"""Message channel definition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from app.modules.alertmanager.domain.channel_provider import ChannelProvider
from app.modules.alertmanager.util import ChannelType


@dataclass
class MsgChannel:
    channel_id: str
    channel_name: str
    channel_type: str
    msg_send_rule_id: str
    msg_send_provider_id: str
    receiver: str | None = None
    send_rate: int | None = None
    forbid_type: str | None = None
    forbid_begintime: str | None = None
    forbid_endtime: str | None = None
    note: str | None = None
    operate_user: str | None = None
    operate_time: str | None = None
    is_invalid: str = "0"
    is_del: str = "0"
    mapper_monitor_group: str | None = None
    msg_format: str | None = None
    channel_providers: ChannelProvider | None = None
    channelType: ChannelType | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)
