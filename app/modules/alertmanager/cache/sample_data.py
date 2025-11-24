"""Seed data so the Python port works without a database."""

from __future__ import annotations

from app.modules.alertmanager.domain import AlertItem, ChannelProvider, MsgChannel, MsgSendRules
from app.modules.alertmanager.util import AlertLevelType, ChannelType

default_provider = ChannelProvider(
    msg_send_provider_id="provider-mail",
    provider_name="Default Mail Provider",
    provider_type="MAIL",
    mail_username="noreply@example.com",
    mail_pwd="password",
    mail_sender_smtp="smtp.example.com",
    mail_sender_smtp_port=465,
    mail_sender="noreply@example.com",
    allMailAddress=["ops@example.com"],
)

default_channel = MsgChannel(
    channel_id="channel-mail",
    channel_name="Mail Notification",
    channel_type=ChannelType.MAIL.value,
    msg_send_rule_id="rule-busi",
    msg_send_provider_id=default_provider.msg_send_provider_id,
    channel_providers=default_provider,
    channelType=ChannelType.MAIL,
    msg_format="[Omnis][{ALERT_CODE}] {HOST_NAME}({HOST_IP}) {STATU}: {ALERT_MSG}",
    send_rate=30,
)

default_rule = MsgSendRules(
    msg_send_rule_id="rule-busi",
    send_rule_group_id="group-busi",
    alertitem_code="BUSI000",
    repeat_send_interval=300,
    repeat_send_interval_maxtime=3,
    same_alert_resend_mintime=60,
    msg_fmt=default_channel.msg_format,
    msgChannels=[default_channel],
)

default_alert_item = AlertItem(
    alertitem_code="BUSI000",
    alertitem_desc="Default business notification",
    alertitem_solution="Inspect the upstream system.",
    alertitem_level=AlertLevelType.REMIND.value,
    alertitem_group="default",
)


def bootstrap_alertitems():
    return {
        default_alert_item.alertitem_code: default_alert_item,
    }


def bootstrap_rules():
    return {
        default_rule.alertitem_code: default_rule,
    }


def bootstrap_forbids():
    return []
