"""Base provider logic translated from AbsMsgSendProvider."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Deque, Dict

from app.modules.alertmanager.domain import AlertItemRecord, MsgChannel, MsgSendRules
from app.modules.alertmanager.domain.msg_send_event import MsgSendEventBean
from app.modules.alertmanager.msgformat import AlertMsgFormatter
from app.modules.alertmanager.util import AlertManagerConstant
from app.modules.alertmanager.util.exceptions import MsgSendException

log = logging.getLogger(__name__)


@dataclass
class _SendRecord:
    timestamp: datetime
    count: int = 1


class BaseProvider:
    """Rudimentary translation of AbsMsgSendProvider's throttling/helpers."""

    NOT_LIMIT_SEND_COUNT = "-1"

    def __init__(self, formatter: AlertMsgFormatter | None = None) -> None:
        self.formatter = formatter or AlertMsgFormatter()
        self._per_minute: Dict[str, Deque[_SendRecord]] = defaultdict(deque)
        self._last_send: Dict[str, datetime] = {}

    def _apply_common_rules(self, event: MsgSendEventBean) -> None:
        channel = event.msgChannel
        record = event.alertitemRecord
        rules = event.msgSendRules
        key = channel.channel_id
        self._throttle(key, channel.send_rate)
        self._dedup(record, channel, rules)

    def _throttle(self, key: str, max_per_minute: int | None) -> None:
        if not max_per_minute or max_per_minute <= 0:
            return

        window = self._per_minute[key]
        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=1)

        while window and window[0].timestamp < cutoff:
            window.popleft()

        count = sum(item.count for item in window)
        if count >= max_per_minute:
            raise MsgSendException(f"{key} exceeded {max_per_minute} msgs/min.")

        window.append(_SendRecord(timestamp=now))

    def _dedup(self, record: AlertItemRecord, msg_channel: MsgChannel, rules: MsgSendRules) -> None:
        resend_window = rules.same_alert_resend_mintime or 0
        if (
            record.event_type != AlertManagerConstant.EVENT_TYPE_CREATE
            or resend_window <= 0
        ):
            return

        key = f"{record.hostname}@{record.hostip}@{record.alertitem_code}@{msg_channel.channel_id}"
        now = datetime.utcnow()
        last = self._last_send.get(key)
        if last and (now - last).total_seconds() <= resend_window:
            raise MsgSendException(
                f"{record.alertitem_code} resend interval < {resend_window}s."
            )
        self._last_send[key] = now

    async def send(self, event: MsgSendEventBean) -> None:
        raise NotImplementedError
