"""In-memory cache for alert metadata."""

from __future__ import annotations

from collections import OrderedDict
import logging
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional

from app.modules.alertmanager.domain import AlertItem, MsgSendForbidObj, MsgSendRules, ReSendInfoSnapshot
from .sample_data import bootstrap_alertitems, bootstrap_forbids, bootstrap_rules

log = logging.getLogger(__name__)


class AlertInfoCache:
    """Simplified port of the Java cache backed by in-memory dictionaries."""

    MAX_CACHE_SIZE = 20_000

    def __init__(
        self,
        alertitems: Mapping[str, AlertItem] | None = None,
        msg_send_rules: Mapping[str, MsgSendRules] | None = None,
        forbids: Iterable[MsgSendForbidObj] | None = None,
    ) -> None:
        self._alertitems: Dict[str, AlertItem] = {
            code.upper(): item for code, item in (alertitems or {}).items()
        }
        self._msg_send_rules: Dict[str, MsgSendRules] = {
            code.upper(): rule for code, rule in (msg_send_rules or {}).items()
        }
        self._msg_send_forbid_objs: List[MsgSendForbidObj] = list(forbids or [])
        self._tmp_messages: "OrderedDict[str, bool]" = OrderedDict()
        self.resend_snapshot: MutableMapping[str, ReSendInfoSnapshot] = {}

    @classmethod
    def from_sample(cls) -> "AlertInfoCache":
        return cls(
            alertitems=bootstrap_alertitems(),
            msg_send_rules=bootstrap_rules(),
            forbids=bootstrap_forbids(),
        )

    async def init_all(self) -> None:
        log.info(
            "Alert cache primed with %d alert items / %d rules.",
            len(self._alertitems),
            len(self._msg_send_rules),
        )

    def get_alertitem(self, code: str) -> Optional[AlertItem]:
        return self._alertitems.get(code.upper())

    def get_msg_send_rules(self, code: str) -> Optional[MsgSendRules]:
        return self._msg_send_rules.get(code.upper())

    @property
    def msg_send_rules(self) -> Mapping[str, MsgSendRules]:
        return self._msg_send_rules

    @property
    def msg_send_forbid_objs(self) -> List[MsgSendForbidObj]:
        return self._msg_send_forbid_objs

    def add_tmp_message(self, event_id: str, project: str, is_recover: bool) -> None:
        key = self._cache_key(event_id, project)
        self._tmp_messages[key] = is_recover
        self._tmp_messages.move_to_end(key)
        while len(self._tmp_messages) > self.MAX_CACHE_SIZE:
            self._tmp_messages.popitem(last=False)

    def check_tmp_message(self, event_id: str, project: str) -> Optional[bool]:
        return self._tmp_messages.get(self._cache_key(event_id, project))

    @staticmethod
    def _cache_key(event_id: str, project: str) -> str:
        return f"{event_id}#{project}"
