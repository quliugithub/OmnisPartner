"""Generic SMS provider using MAS-style HTTP POST."""

from __future__ import annotations

import logging
import httpx

from app.modules.alertmanager.domain import MsgSendEventBean
from app.modules.alertmanager.provider.base import BaseProvider
from app.modules.alertmanager.service.exceptions import MsgSendException
from app.modules.alertmanager.util import ChannelType

log = logging.getLogger(__name__)


class SmsProvider(BaseProvider):
    channel_type = ChannelType.SHORTMSG

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        super().__init__()
        self._client = client or httpx.AsyncClient(timeout=10)

    async def send(self, event: MsgSendEventBean) -> None:
        self._apply_common_rules(event)

        msg_channel = event.msgChannel
        provider = msg_channel.channel_providers
        if not provider or not provider.mas_sender_url:
            raise MsgSendException("短信通道未配置URL。")

        recipients = provider.mas_recive_pthones or self._split_csv(provider.mas_recive_users)
        if not recipients:
            raise MsgSendException("短信通道未配置接收号码。")

        body = {
            "username": provider.mas_sender_user,
            "password": provider.mas_sender_pwd,
            "sign": provider.mas_sign,
            "message": event.msg,
            "phones": recipients,
        }

        resp = await self._client.post(provider.mas_sender_url, json=body)
        if resp.status_code >= 400:
            raise MsgSendException(f"短信发送失败 HTTP {resp.status_code}")

        try:
            data = resp.json()
        except ValueError:
            log.warning("无法解析短信服务返回内容: %s", resp.text)
            return

        if data.get("success") is False:
            raise MsgSendException(f"短信发送失败: {data.get('message')}")

    @staticmethod
    def _split_csv(value: str | None) -> list[str]:
        if not value:
            return []
        return [part.strip() for part in value.split(",") if part.strip()]
