"""AlertManager service translated from the Spring implementation."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import deque
from typing import Any, Deque, Dict, Optional, Set

from app.settings import Settings

from app.modules.alertmanager.cache import AlertInfoCache
from app.modules.alertmanager.domain import (
    AlertItemRecord,
    MsgChannel,
    MsgSendEventBean,
    MsgSendRules,
    ReSendInfoSnapshot,
    SyncMsgBean,
)
from app.modules.alertmanager.msgformat import AlertMsgFormatter
from app.modules.alertmanager.provider import ProviderRegistry
from app.modules.alertmanager.repositories import AlertManagerRepository, InMemoryAlertManagerRepository
from app.modules.alertmanager.util.exceptions import MsgSendException
from app.modules.alertmanager.util import (
    AlertLevelType,
    AlertManagerConstant,
    AlertSourceType,
    ChannelType,
    MsgSendDefaultInfos,
    generate_event_id,
    now,
    parse_dot_datetime,
)

log = logging.getLogger(__name__)


class AlertManagerService:
    def __init__(
        self,
        settings: Settings,
        alert_cache: AlertInfoCache | None = None,
        repository: AlertManagerRepository | None = None,
        formatter: AlertMsgFormatter | None = None,
        providers: ProviderRegistry | None = None,
    ) -> None:
        self.settings = settings
        self.cache = alert_cache or AlertInfoCache.from_sample()
        self.repository = repository or InMemoryAlertManagerRepository()
        self.formatter = formatter or AlertMsgFormatter()
        self.providers = providers or ProviderRegistry.default()
        self._sync_queue: Deque[SyncMsgBean] = deque()
        self._resend_task: asyncio.Task | None = None
        self._repeat_task: asyncio.Task | None = None
        self._sync_task: asyncio.Task | None = None

    async def push_msg(self, json_msg: str, source_type: AlertSourceType, send_msg: bool) -> Dict[str, Any]:
        try:
            if source_type == AlertSourceType.ZABBIX:
                raise MsgSendException("zabbix类型只能通过专用接口发送。")
            record = self._gen_record_from_json(json_msg, source_type)
            record.currentIsSendMsg = send_msg
            return await self._push_alert_msg_native(record)
        except MsgSendException as exc:
            log.warning("push_msg failed: %s", exc)
            return builder_error(str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("Unexpected error in push_msg")
            return builder_error(str(exc))

    async def push_alert_msg_zbx(self, payload: str, source_type: AlertSourceType, send_msg: bool) -> Dict[str, Any]:
        try:
            record = self._gen_record_from_zabbix(payload)
            record.currentIsSendMsg = send_msg
            return await self._push_alert_msg_native(record)
        except MsgSendException as exc:
            log.warning("push_alert_msg_zbx failed: %s", exc)
            return builder_error(str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("Unexpected error in push_alert_msg_zbx")
            return builder_error(str(exc))

    async def interval_msg_send_task(self) -> None:
        if self._resend_task is None:
            self._resend_task = asyncio.create_task(self._resend_loop())

    async def sync_data_to_remote_thread_invoker(self) -> None:
        if self._sync_task is None:
            self._sync_task = asyncio.create_task(self._sync_loop())

    async def repeated_alert_msg_auto_confirm(self) -> None:
        if self._repeat_task is None:
            self._repeat_task = asyncio.create_task(self._repeat_loop())

    async def _push_alert_msg_native(self, record: AlertItemRecord) -> Dict[str, Any]:
        try:
            comment = ""
            record_state = "0"
            rules = self.cache.get_msg_send_rules(record.alertitem_code)

            if not rules or not rules.msgChannels:
                log.info(
                    "Alert %s does not have channels configured, skipping.",
                    record.alertitem_code,
                )
                comment = "NOT_SEND"
                record_state = "2"
            elif rules.is_forbid == AlertManagerConstant.FORBID_YES:
                log.info("%s rule is disabled, skipping.", record.alertitem_code)
                comment = "NOT_SEND_RULE_FORBID"
                record_state = "1"
            elif (
                record.event_type == AlertManagerConstant.EVENT_TYPE_RECOVER
                and rules.recover_msg_notsend == AlertManagerConstant.FORBID_YES_INT
            ):
                log.info("%s recover notifications suppressed by rule.", record.alertitem_code)
                record_state = "10"
                comment = "NOT_SEND_RECOVER_FORBID"
            else:
                comment = "NOT_SEND"
                await self._dispatch_channels(record, rules)
                record_state = "0"

            if record.forbidRuleType == AlertManagerConstant.MSG_SEND_FORBID_NOT_SHOWANDSEND:
                record.alertitem_notshow = int(AlertManagerConstant.ALERTITEM_NOTSHOW_YES)
            elif rules:
                record.alertitem_notshow = rules.alertitem_notshow or int(AlertManagerConstant.ALERTITEM_NOTSHOW_NO)

            record.comment = comment
            record.record_statu = record_state

            if record.event_type == AlertManagerConstant.EVENT_TYPE_RECOVER:
                effect = self.repository.mark_recovered(record)
                self.cache.add_tmp_message(record.event_id, record.project, True)
                if effect == 0:
                    log.warning(
                        "Recover message for %s arrived before create event. Stored only in cache.",
                        record.event_id,
                    )
            else:
                already = self.cache.check_tmp_message(record.event_id, record.project)
                if already is None:
                    if record.forbidRuleType != AlertManagerConstant.MSG_SEND_FORBID_NOT_SHOWANDSEND:
                        self.repository.save_record(record)
                    self.cache.add_tmp_message(record.event_id, record.project, False)
                else:
                    if already:
                        log.warning(
                            "Duplicate recover for %s detected, skipping persistence.", record.event_id
                        )
                    else:
                        log.warning(
                            "Duplicate create event %s detected, skipping persistence.", record.event_id
                        )

            return builder_success("OK")
        except MsgSendException as exc:
            return builder_error(str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("Unexpected error when pushing alert %s", record.alertitem_code)
            return builder_error(str(exc))

    async def _dispatch_channels(self, record: AlertItemRecord, rules: MsgSendRules) -> None:
        for msg_channel in rules.msgChannels:
            if self._is_channel_forbidden(record, msg_channel):
                continue
            template = msg_channel.msg_format or rules.msg_fmt or record.alert_msg_org
            message = self.formatter.format(record, template)
            record.currentChannelType = msg_channel.channel_type
            event = MsgSendEventBean(
                alertitemRecord=record,
                msg=message,
                msgChannel=msg_channel,
                msgSendRules=rules,
            )
            if record.currentIsSendMsg:
                channel_type = msg_channel.channelType or ChannelType(msg_channel.channel_type)
                provider = self.providers.get(channel_type)
                try:
                    await provider.send(event)
                except MsgSendException as exc:
                    log.warning(
                        "Provider %s failed for alert %s: %s",
                        channel_type.name,
                        record.alertitem_code,
                        exc,
                    )
                    record.record_statu = "9"
                    record.comment = f"PROVIDER_FAIL_{channel_type.name}"
                except Exception as exc:  # noqa: BLE001
                    log.exception(
                        "Unexpected provider error (%s) for alert %s",
                        channel_type.name,
                        record.alertitem_code,
                        exc,
                    )
                    record.record_statu = "9"
                    record.comment = f"PROVIDER_ERROR_{channel_type.name}"
            else:
                log.info("Master push mode detected, suppressing channel send for %s.", record.event_id)

    def _is_channel_forbidden(self, record: AlertItemRecord, msg_channel: MsgChannel) -> bool:
        if record.forbidChannels and msg_channel.channel_id in record.forbidChannels:
            log.info(
                "Channel %s blocked by temporary forbid rule for alert %s.",
                msg_channel.channel_id,
                record.alertitem_code,
            )
            record.record_statu = "1"
            record.comment = "NOT_SEND_RULE_FORBID"
            return True

        if (
            msg_channel.is_invalid == AlertManagerConstant.CAN_NOT_USE
            or msg_channel.is_del == AlertManagerConstant.CAN_NOT_USE
        ):
            record.record_statu = "2"
            record.comment = "NOT_SEND_CHANNEL_INVALID"
            return True

        group = msg_channel.mapper_monitor_group
        if group and group.lower() != "[all]":
            normalized = group.replace("[", "").replace("]", "")
            if normalized and normalized not in record.project_group:
                record.record_statu = "3"
                record.comment = "NOT_SEND_PROVIDE_NO_GROUP"
                return True
        return False

    def _gen_record_from_json(self, json_msg: str, source_type: AlertSourceType) -> AlertItemRecord:
        if not json_msg:
            raise MsgSendException("消息内容不能为空")
        try:
            payload = json.loads(json_msg)
        except json.JSONDecodeError as exc:
            raise MsgSendException(f"消息必须是JSON: {exc}") from exc

        alert_code = str(
            payload.get(MsgSendDefaultInfos.DEFAULT_ALERT_CODE_JSONSTR, MsgSendDefaultInfos.ALERTCODE_DEFAULT_BUSI)
        ).upper()
        alert_source_type = payload.get(
            MsgSendDefaultInfos.DEFAULT_ALERT_SOURCE_TYPE_JSONSTR, source_type.value
        )
        if not alert_source_type:
            raise MsgSendException(f"Json字符串必须描述 {MsgSendDefaultInfos.DEFAULT_ALERT_SOURCE_TYPE_JSONSTR} 属性")

        src_type = AlertSourceType(alert_source_type)
        msg_obj = payload.get(MsgSendDefaultInfos.DEFAULT_MSG_JSONSTR)
        if isinstance(msg_obj, str) and src_type == AlertSourceType.PINPOINT:
            msg_map = self._parse_pinpoint(msg_obj)
        elif isinstance(msg_obj, dict):
            msg_map = msg_obj
        else:
            msg_map = {"message": msg_obj}

        alert_item = self.cache.get_alertitem(alert_code)
        if not alert_item:
            raise MsgSendException(f"{alert_code} 编码未在知识库找到，请传入正确的消息编码")

        project = str(payload.get("project", self.settings.alertmanager_project)).upper()
        hostname = payload.get(MsgSendDefaultInfos.DEFAULT_HOSTNAME_JSONSTR, f"[{project}]-0.0.0.0-[unknown]")

        record = AlertItemRecord(
            alertitem_record_id=str(uuid.uuid4()),
            event_id=generate_event_id(),
            alertitem_code=alert_code,
            project=project,
            project_group=f"[{project}]",
            alert_source=src_type.value,
            event_type=AlertManagerConstant.EVENT_TYPE_CREATE,
            hostip=str(payload.get("hostip", "0.0.0.0")),
            hostname=str(hostname),
            alert_level=alert_item.alertitem_level,
            add_time=now(),
            alert_msg_org=json_msg,
            alert_msg=msg_map.get("message", ""),
            alertSourceType=src_type,
            msgJsoninfo=msg_map,
            others=payload.get("others"),
        )
        self._check_forbid_rules(record)
        return record

    def _gen_record_from_zabbix(self, msg: str) -> AlertItemRecord:
        if not msg:
            raise MsgSendException("消息为空")
        disable_msg = msg.startswith("NOTE:") and "disabled." in msg
        parts = msg.split("|")
        if len(parts) < 9:
            raise MsgSendException("错误的消息格式")

        event_id = parts[0].strip()
        if disable_msg:
            event_id = event_id[event_id.index("disabled.") + 9 :].strip()

        hostname = parts[1]
        hostip = parts[2]
        alert_time = parse_dot_datetime(parts[4])
        recover_time = parse_dot_datetime(parts[5])
        event_type = parts[6]
        project_group = parts[7]
        group = parts[7]
        if group is None:
            raise MsgSendException(f"错误格式的项目分组名称，需要描述为[TJH]xxxxxx类似{msg}")

        if not group.startswith('[') or ']' not in group:
            raise MsgSendException(f"错误格式的项目分组名称，需要描述为[TJH]xxxxxx类似{msg}")

        # 截取最外层中括号及其内部内容
        end = group.index(']')
        group = group[:end + 1]  # -
        project = group[1:-1]

        alert_msg = parts[8]
        if not alert_msg.startswith("[") or "]" not in alert_msg:
            raise MsgSendException("错误的消息格式，需要描述为[JVM001]类似 预警编码开始")
        alert_code = alert_msg[1 : alert_msg.index("]")]
        alert_item = self.cache.get_alertitem(alert_code.upper())
        level = alert_item.alertitem_level if alert_item else AlertLevelType.UNKOWN.value

        record = AlertItemRecord(
            alertitem_record_id=str(uuid.uuid4()),
            event_id=event_id,
            alertitem_code=alert_code.upper(),
            project=project.upper(),
            project_group=project_group,
            alert_source=AlertSourceType.ZABBIX.value,
            event_type=event_type,
            hostip=hostip,
            hostname=hostname,
            alert_level=level,
            add_time=now(),
            alert_msg_org=msg,
            alert_msg=alert_msg,
            alert_time=alert_time,
            recover_time=recover_time,
            is_recover=(
                AlertManagerConstant.IS_RECOVER_YES
                if recover_time or disable_msg
                else AlertManagerConstant.IS_RECOVER_NO
            ),
            alertSourceType=AlertSourceType.ZABBIX,
        )
        self._check_forbid_rules(record)
        return record

    @staticmethod
    def _parse_pinpoint(msg_str: str) -> Dict[str, Any]:
        fields = ["appid", "checkername", "notes", "time", "threshold", "message"]
        segments = msg_str.split("|")
        return {field: (segments[idx] if idx < len(segments) else "") for idx, field in enumerate(fields)}

    def _check_forbid_rules(self, record: AlertItemRecord) -> None:
        forbids = self.cache.msg_send_forbid_objs
        if not forbids:
            return
        now_ts = now().timestamp()
        for forbid in forbids:
            if not forbid.begTime or not forbid.endTime:
                continue
            if forbid.begTime.timestamp() > now_ts or forbid.endTime.timestamp() < now_ts:
                continue
            if not self._match_forbid(forbid.ips, record.hostip):
                continue
            if not self._match_forbid(forbid.alertCodes, record.alertitem_code):
                continue
            if not self._match_forbid(forbid.projects, record.project):
                continue
            if forbid.hosts and not any(h.lower() in record.hostname.lower() for h in forbid.hosts):
                continue
            record.forbidRuleType = forbid.forbidType
            record.forbidChannels = set(forbid.channels)

    @staticmethod
    def _match_forbid(values: Set[str], candidate: str) -> bool:
        if not values:
            return False
        if values == {"NULL"}:
            return True
        return candidate in values

    def sync_data_to_slave(self, msg: str, project_identify: str, msg_type: int) -> None:
        self._sync_queue.append(SyncMsgBean(msg=msg, projectIdentify=project_identify, msgType=msg_type))

    async def _sync_loop(self) -> None:
        while True:
            if not self._sync_queue:
                await asyncio.sleep(1)
                continue
            sync_msg = self._sync_queue.popleft()
            for target in self.settings.alertmanager_slave_targets:
                log.info(
                    "Would sync message to %s (project=%s, type=%s)",
                    target,
                    sync_msg.projectIdentify,
                    sync_msg.msgType,
                )
                await asyncio.sleep(0)

    async def _resend_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            to_remove: Set[str] = set()
            for record_id, snapshot in list(self.cache.resend_snapshot.items()):
                if snapshot.sendCount >= snapshot.msgSendRules.repeat_send_interval_maxtime:
                    to_remove.add(record_id)
                    continue
                now_ms = now().timestamp() * 1000
                interval_ms = snapshot.msgSendRules.repeat_send_interval * 1000
                if now_ms - snapshot.lastSendTime < interval_ms:
                    continue
                stored = self.repository.get_record(snapshot.record.alertitem_record_id)
                if stored and stored.is_confirm != AlertManagerConstant.CONFIRM_YES:
                    snapshot.sendCount += 1
                    snapshot.lastSendTime = now_ms
                    event = MsgSendEventBean(
                        alertitemRecord=snapshot.record,
                        msg=snapshot.msg,
                        msgChannel=snapshot.msgChannel,
                        msgSendRules=snapshot.msgSendRules,
                    )
                    channel_type = snapshot.msgChannel.channelType or ChannelType(snapshot.msgChannel.channel_type)
                    await self.providers.get(channel_type).send(event)
                else:
                    to_remove.add(record_id)
            for key in to_remove:
                self.cache.resend_snapshot.pop(key, None)

    async def _repeat_loop(self) -> None:
        while True:
            await asyncio.sleep(10)
            reps = self.repository.query_repeat_candidates()
            if not reps:
                continue
            for row in reps:
                self.repository.confirm_repeat(
                    hostip=row["hostip"],
                    alert_code=row["alertitem_code"],
                    add_time=row["addtime"],
                    project=row["project"],
                )

    def check_msg_send_token(self, token: str, business_name: str) -> bool:
        if not self.settings.alertmanager_allowed_tokens:
            return True
        return token in self.settings.alertmanager_allowed_tokens


def builder_success(msg: str) -> Dict[str, Any]:
    return {"status": "success", "message": msg}


def builder_error(msg: str) -> Dict[str, Any]:
    return {"status": "error", "message": msg}
