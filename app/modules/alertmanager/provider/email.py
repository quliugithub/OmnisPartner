"""Email provider implementation."""

from __future__ import annotations

import contextlib
import logging
from email.message import EmailMessage

import aiosmtplib

from app.modules.alertmanager.domain import MsgSendEventBean
from app.modules.alertmanager.provider.base import BaseProvider
from app.modules.alertmanager.service.exceptions import MsgSendException
from app.modules.alertmanager.util import ChannelType

log = logging.getLogger(__name__)


class EmailProvider(BaseProvider):
    channel_type = ChannelType.MAIL

    async def send(self, event: MsgSendEventBean) -> None:
        self._apply_common_rules(event)

        record = event.alertitemRecord
        msg_channel = event.msgChannel
        provider = msg_channel.channel_providers
        if not provider:
            raise MsgSendException("邮件通道未配置。")

        smtp_host = provider.mail_sender_smtp
        smtp_port = provider.mail_sender_smtp_port
        username = provider.mail_username
        password = provider.mail_pwd
        sender = provider.mail_sender or username
        recipients = provider.allMailAddress or self._split_csv(provider.mail_recive_address)

        if not smtp_host or not smtp_port or not username or not password:
            raise MsgSendException("邮件通道缺少SMTP配置。")
        if not recipients:
            raise MsgSendException("邮件通道未配置收件人。")

        email = EmailMessage()
        subject = f"告警 - {record.hostname or ''}#{record.hostip or ''}"
        email["Subject"] = subject
        email["From"] = sender
        email["To"] = ", ".join(recipients)
        email.set_content(event.msg)

        use_tls = smtp_port != 25
        smtp = aiosmtplib.SMTP(
            hostname=smtp_host,
            port=smtp_port,
            use_tls=use_tls,
            start_tls=not use_tls,
            username=username,
            password=password,
        )

        try:
            await smtp.connect()
            await smtp.send_message(email)
        finally:
            with contextlib.suppress(Exception):
                await smtp.quit()

    @staticmethod
    def _split_csv(value: str | None) -> list[str]:
        if not value:
            return []
        return [part.strip() for part in value.split(",") if part.strip()]
