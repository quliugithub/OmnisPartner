"""MySQL-backed repository for AlertManager data."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Dict, Iterable, List, Tuple

import pymysql

from app.db import mysql_connection
from app.modules.alertmanager.domain import (
    AlertItem,
    AlertItemRecord,
    ChannelProvider,
    MsgChannel,
    MsgSendEventBean,
    MsgSendForbidObj,
    MsgSendRules,
)
from app.modules.alertmanager.repositories import AlertManagerRepository
from app.modules.alertmanager.util import AlertManagerConstant
from app.modules.alertmanager.service.exceptions import MsgSendException
from app.settings import Settings

log = logging.getLogger(__name__)


class MySQLAlertManagerRepository(AlertManagerRepository):
    """Skeleton implementation that mirrors the legacy AlertManagerDBOperator."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @contextmanager
    def _conn(self):
        conn = mysql_connection(self.settings)
        try:
            yield conn
        finally:
            conn.close()

    # ---- Metadata loaders -------------------------------------------------
    def load_alert_items(self) -> Dict[str, AlertItem]:
        sql = (
            "SELECT alertitem_code, alertitem_desc, alertitem_solution, alertitem_level, alertitem_group, note "
            "FROM monitor_alertitem_solution"
        )
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        return {
            row["alertitem_code"].upper(): AlertItem(
                alertitem_code=row["alertitem_code"].upper(),
                alertitem_desc=row.get("alertitem_desc", ""),
                alertitem_solution=row.get("alertitem_solution", ""),
                alertitem_level=row.get("alertitem_level", AlertManagerConstant.EVENT_TYPE_CREATE),
                alertitem_group=row.get("alertitem_group", ""),
                note=row.get("note", ""),
            )
            for row in rows
        }

    def load_channel_providers(self) -> Dict[str, ChannelProvider]:
        sql = "SELECT * FROM msg_sendchannel_provider"
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
        providers = {}
        for row in rows:
            providers[row["msg_send_provider_id"]] = ChannelProvider(
                msg_send_provider_id=row["msg_send_provider_id"],
                provider_name=row.get("provider_name", ""),
                provider_type=row.get("provider_type"),
                wx_corpid=row.get("wx_corpid"),
                wx_secret=row.get("wx_secret"),
                wx_agentId=row.get("wx_agentId"),
                wx_touser=row.get("wx_touser"),
                wx_toparty=row.get("wx_toparty"),
                wx_base_url=row.get("wx_base_url"),
                ding_robot_url=row.get("ding_robot_url"),
                ding_robot_keywords=row.get("ding_robot_keywords"),
                ding_robot_sign=row.get("ding_robot_sign"),
                ding_robot_ip=row.get("ding_robot_ip"),
                mail_sender=row.get("mail_sender"),
                mail_username=row.get("mail_username"),
                mail_pwd=row.get("mail_pwd"),
                mail_sender_smtp=row.get("mail_sender_smtp"),
                mail_sender_smtp_port=row.get("mail_sender_smtp_port"),
                mail_recive_address=row.get("mail_recive_address"),
                allMailAddress=self._split_csv(row.get("mail_recive_address")),
                mas_sender_user=row.get("mas_sender_user"),
                mas_sender_pwd=row.get("mas_sender_pwd"),
                mas_sender_name=row.get("mas_sender_name"),
                mas_sender_url=row.get("mas_sender_url"),
                mas_sign=row.get("mas_sign"),
                mas_recive_users=row.get("mas_recive_users"),
                mas_recive_user_groups=row.get("mas_recive_user_groups"),
                mas_recive_pthones=self._split_csv(row.get("mas_recive_pthones")),
                aliyun_access_key_id=row.get("aliyun_access_key_id"),
                aliyun_access_key_secret=row.get("aliyun_access_key_secret"),
                aliyun_voice_template_code=row.get("aliyun_voice_template_code"),
                aliyun_voice_template_params=row.get("aliyun_voice_template_params"),
                aliyun_voice_called_show_number=row.get("aliyun_voice_called_show_number"),
                aliyun_voice_called_numbers=self._split_csv(row.get("aliyun_voice_called_numbers")),
                aliyun_region=row.get("aliyun_region"),
                aliyun_api_url=row.get("aliyun_api_url"),
            )
        return providers

    @staticmethod
    def _split_csv(value: str | None) -> list[str]:
        if not value:
            return []
        return [part.strip() for part in value.split(",") if part.strip()]

    def load_channels(self, providers: Dict[str, ChannelProvider]) -> Dict[str, List[MsgChannel]]:
        sql = "select b.*,a.msg_send_rule_id from msg_send_rel_channel a,monitor_msg_channel b,msg_send_rule c,msg_send_rule_group d where a.channel_id = b.channel_id and c.msg_send_rule_id=a.msg_send_rule_id AND c.send_rule_group_id=d.send_rule_group_id  and b.is_del = '0' and b.is_invalid='0' and d.is_default_group = '1'"
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        grouped: Dict[str, List[MsgChannel]] = {}
        for row in rows:
            provider = providers.get(row["msg_send_provider_id"])
            channel = MsgChannel(
                channel_id=row["channel_id"],
                channel_name=row["channel_name"],
                channel_type=row["channel_type"],
                msg_send_rule_id=row["msg_send_rule_id"],
                msg_send_provider_id=row["msg_send_provider_id"],
                receiver=row.get("receiver"),
                send_rate=row.get("send_rate"),
                forbid_type=row.get("forbid_type"),
                forbid_begintime=row.get("forbid_begintime"),
                forbid_endtime=row.get("forbid_endtime"),
                mapper_monitor_group=row.get("mapper_monitor_group"),
                msg_format=row.get("msg_format"),
                is_invalid=row.get("is_invalid", "0"),
                is_del=row.get("is_del", "0"),
                channel_providers=provider,
            )
            grouped.setdefault(channel.msg_send_rule_id, []).append(channel)
        return grouped

    def load_rules(self, channels: Dict[str, List[MsgChannel]]) -> Dict[str, MsgSendRules]:
        sql = "select * from msg_send_rule a,msg_send_rule_group b,monitor_alertitem_solution c where a.send_rule_group_id = b.send_rule_group_id and c.alertitem_code = a.alertitem_code and b.is_default_group = '1' "
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        rules: Dict[str, MsgSendRules] = {}
        for row in rows:
            rule = MsgSendRules(
                msg_send_rule_id=row["msg_send_rule_id"],
                send_rule_group_id=row.get("send_rule_group_id", ""),
                alertitem_code=row["alertitem_code"].upper(),
                repeat_send_interval=row.get("repeat_send_interval", 0),
                repeat_send_interval_maxtime=row.get("repeat_send_interval_maxtime", 0),
                same_alert_resend_mintime=row.get("same_alert_resend_mintime", 0),
                valid_time_begin=row.get("valid_time_begin"),
                valid_time_end=row.get("valid_time_end"),
                is_forbid=row.get("is_forbid", "0"),
                recover_msg_notsend=row.get("recover_msg_notsend", 0),
                alertitem_notshow=row.get("alertitem_notshow", 0),
                msg_fmt=row.get("msg_fmt"),
                msgChannels=channels.get(row["msg_send_rule_id"], []),
            )
            rules[rule.alertitem_code] = rule
        return rules

    def load_forbid_rules(self) -> List[MsgSendForbidObj]:
        from datetime import datetime
        now = datetime.now()
        sql = """
            SELECT * FROM msg_send_forbid
            WHERE %s BETWEEN time_begin AND time_end
        """
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, (now,))  # 把 now 作为参数传进去
            rows = cur.fetchall()

        forbids: List[MsgSendForbidObj] = []
        for row in rows:
            forbids.append(
                MsgSendForbidObj(
                    begTime=row["time_begin"],
                    endTime=row["time_end"],
                    forbidType=row.get("forbid_type", "1"),
                    ips=set((row.get("ip_str") or "").split(",")) if row.get("ip_str") else set(),
                    hosts=set((row.get("machine_name_str") or "").split(",")) if row.get("machine_name_str") else set(),
                    channels=set((row.get("channel_id_str") or "").split(",")) if row.get("channel_id_str") else set(),
                    contents=set((row.get("msg_content_str") or "").split(",")) if row.get("msg_content_str") else set(),
                    alertCodes=set((row.get("alertitem_code_str") or "").split(",")) if row.get("alertitem_code_str") else set(),
                    projects=set((row.get("project_code_str") or "").split(",")) if row.get("project_code_str") else set(),
                )
            )
        return forbids

    def load_metadata(self) -> Tuple[Dict[str, AlertItem], Dict[str, MsgSendRules], List[MsgSendForbidObj]]:
        try:
            alertitems = self.load_alert_items()
            providers = self.load_channel_providers()
            channels = self.load_channels(providers)
            rules = self.load_rules(channels)
            forbids = self.load_forbid_rules()
            log.info("Loaded %d alert items / %d rules from MySQL.", len(alertitems), len(rules))
            return alertitems, rules, forbids
        except pymysql.MySQLError as exc:
            log.warning("Failed to load AlertManager metadata from MySQL: %s", exc)
            raise

    # ---- Record persistence (stubs for now) -------------------------------
    def save_record(self, record: AlertItemRecord) -> None:
        sql = (
            "INSERT INTO monitor_alertitem_record "
            "(alertitem_record_id, event_id, alert_time, recover_time, hostname, hostip, alertitem_code, "
            "event_type, event_name, add_time, alert_source, is_confirm, comments, record_statu, alert_msg, "
            "alert_msg_org, alert_level, alertitem_notshow, server_id, is_recover, project) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    record.alertitem_record_id,
                    record.event_id,
                    record.alert_time,
                    record.recover_time,
                    record.hostname,
                    record.hostip,
                    record.alertitem_code,
                    record.event_type,
                    record.event_name,
                    record.alert_source,
                    record.is_confirm or AlertManagerConstant.CONFIRM_NO,
                    record.comment,
                    record.record_statu,
                    record.alert_msg,
                    record.alert_msg_org,
                    record.alert_level,
                    record.alertitem_notshow,
                    record.server_id,
                    record.is_recover,
                    record.project,
                ),
            )

    def mark_recovered(self, record: AlertItemRecord) -> int:
        sql = (
            "UPDATE monitor_alertitem_record "
            "SET event_type = %s, recover_time = %s, is_recover = '1' "
            "WHERE event_id = %s"
        )
        with self._conn() as conn, conn.cursor() as cur:
            return cur.execute(sql, (record.event_type, record.recover_time, record.event_id))

    def get_record(self, record_id: str) -> AlertItemRecord | None:
        sql = "SELECT * FROM monitor_alertitem_record WHERE alertitem_record_id = %s"
        with self._conn() as conn, conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, (record_id,))
            row = cur.fetchone()
            if not row:
                return None
            return AlertItemRecord(
                alertitem_record_id=row["alertitem_record_id"],
                event_id=row["event_id"],
                alertitem_code=row["alertitem_code"],
                project=row["project"],
                project_group=row.get("mapper_monitor_group_one", ""),
                alert_source=row["alert_source"],
                event_type=row["event_type"],
                hostip=row["hostip"],
                hostname=row["hostname"],
                alert_level=row["alert_level"],
                add_time=row["add_time"],
                alert_msg_org=row["alert_msg_org"],
                alert_msg=row["alert_msg"],
                comment=row.get("comments", ""),
                record_statu=row.get("record_statu", "0"),
                alertitem_notshow=row.get("alertitem_notshow", 0),
                alert_time=row.get("alert_time"),
                recover_time=row.get("recover_time"),
                is_recover=row.get("is_recover", AlertManagerConstant.IS_RECOVER_NO),
                is_confirm=row.get("is_confirm", AlertManagerConstant.CONFIRM_NO),
                server_id=row.get("server_id"),
            )

    def query_repeat_candidates(self):
        sql = (
            "SELECT hostip, alertitem_code, add_time, project "
            "FROM monitor_alertitem_record "
            "WHERE event_type = %s AND (is_recover IS NULL OR is_recover = %s)"
        )
        with self._conn() as conn, conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql, (AlertManagerConstant.EVENT_TYPE_CREATE, AlertManagerConstant.IS_RECOVER_NO))
            return cur.fetchall()

    def confirm_repeat(self, hostip: str, alert_code: str, add_time, project: str) -> None:
        sql = (
            "UPDATE monitor_alertitem_record SET is_confirm = %s "
            "WHERE hostip = %s AND alertitem_code = %s AND add_time = %s AND project = %s"
        )
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, (AlertManagerConstant.CONFIRM_YES, hostip, alert_code, add_time, project))
