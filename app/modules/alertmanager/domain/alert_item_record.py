"""Alert occurrence record."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Set

from app.modules.alertmanager.util import AlertSourceType


@dataclass
class AlertItemRecord:
    alertitem_record_id: str
    event_id: str
    alertitem_code: str
    project: str
    project_group: str
    alert_source: str
    event_type: str
    hostip: str
    hostname: str
    alert_level: str
    add_time: datetime
    alert_msg_org: str = ""
    alert_msg: str = ""
    record_statu: str = "0"
    comment: str = ""
    alertitem_notshow: int = 0
    alert_time: datetime | None = None
    recover_time: datetime | None = None
    is_recover: str = "0"
    is_confirm: str = "0"
    server_id: str | None = None
    event_name: str | None = None
    currentChannelType: str | None = None
    alertSourceType: AlertSourceType = AlertSourceType.OTHERS
    msgJsoninfo: Dict[str, Any] | None = None
    others: Dict[str, Any] | None = None
    currentIsSendMsg: bool = True
    isDisableMsg: bool = False
    forbidChannels: Set[str] | None = None
    forbidRuleType: str | None = None
    host_business_name: str | None = None
