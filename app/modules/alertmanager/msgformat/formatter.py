"""Message formatting helpers."""

from __future__ import annotations

import json
from typing import Mapping

from app.modules.alertmanager.domain import AlertItemRecord
from app.modules.alertmanager.util import format_dot_datetime, now


class AlertMsgFormatter:
    """Applies the placeholder substitutions from the legacy formatters."""

    def format(self, record: AlertItemRecord, template: str) -> str:
        if not template:
            return record.alert_msg or record.alert_msg_org

        msg_info = record.msgJsoninfo or {}

        replacements = {
            "{HOST_BUSI_NAME}": record.host_business_name or record.hostname,
            "{HOST_NAME}": record.hostname,
            "{HOST_IP}": record.hostip,
            "{ALERT_CODE}": record.alertitem_code,
            "{ALERT_TIME}": format_dot_datetime(record.alert_time),
            "{RECOVER_TIME}": format_dot_datetime(record.recover_time),
            "{ALERT_MSG}": record.alert_msg or record.alert_msg_org,
            "{NOW}": format_dot_datetime(now()),
            "{ALERT_LEVEL}": record.alert_level,
            "{LOCATION}": record.others.get("location") if record.others else "",
            "{EVENT_ID}": record.event_id,
            "{STATU}": self._status(record.event_type),
            "{TITLE}": self._title(record),
            "{PROJECT}": record.project,
            "{JSON_MESSGES}": self._json_payload(record),
            "{K8S_RESOURCE_NAME}": msg_info.get("k8s_resource_name", ""),
            "{K8S_RESOURCE_TYPE}": msg_info.get("k8s_resource_type", ""),
            "{NAMESPACE}": msg_info.get("namespace", ""),
            "{HOSPITAL_NAME}": msg_info.get("hospital_name", ""),
            "{DESCRIPTION}": msg_info.get("description", ""),
        }

        formatted = template
        for placeholder, value in replacements.items():
            formatted = formatted.replace(placeholder, str(value or ""))

        if record.others:
            formatted = self._apply_others(formatted, record.others)

        return formatted

    @staticmethod
    def _status(event_type: str | None) -> str:
        if event_type == "0":
            return "RECOVER"
        if event_type == "1":
            return "PROBLEM"
        return "UNKNOWN"

    @staticmethod
    def _title(record: AlertItemRecord) -> str:
        if record.others and record.others.get("subject"):
            return str(record.others["subject"])
        if record.alert_msg:
            return record.alert_msg.splitlines()[0][:120]
        return record.alertitem_code

    @staticmethod
    def _json_payload(record: AlertItemRecord) -> str:
        if not record.msgJsoninfo:
            return ""
        try:
            return json.dumps(record.msgJsoninfo, ensure_ascii=False)
        except TypeError:
            return str(record.msgJsoninfo)

    @staticmethod
    def _apply_others(text: str, values: Mapping[str, str]) -> str:
        formatted = text
        for key, val in values.items():
            placeholder = "{OTHERS." + key.upper() + "}"
            formatted = formatted.replace(placeholder, str(val or ""))
        return formatted
