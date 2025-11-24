"""Message sending providers."""

from __future__ import annotations

import logging
from typing import Dict, Protocol

import httpx

from app.modules.alertmanager.domain import MsgSendEventBean
from app.modules.alertmanager.util import ChannelType

from .dingtalk import DingTalkProvider
from .email import EmailProvider
from .sms import SmsProvider
from .wechat import WeChatProvider
from .aliyun_phone import AliyunPhoneProvider

log = logging.getLogger(__name__)


class MsgSendProvider(Protocol):
    channel_type: ChannelType

    async def send(self, event: MsgSendEventBean) -> None:
        ...


class LoggingProvider:
    """Default provider that only logs the outgoing payload."""

    def __init__(self, channel_type: ChannelType) -> None:
        self.channel_type = channel_type

    async def send(self, event: MsgSendEventBean) -> None:
        log.info(
            "[%s] send alert %s via %s -> %s",
            self.channel_type.name,
            event.alertitemRecord.alertitem_code,
            event.msgChannel.channel_name,
            event.msg,
        )


class ProviderRegistry:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._providers: Dict[ChannelType, MsgSendProvider] = {}
        self._client = client or httpx.AsyncClient(timeout=10)

    def register(self, provider: MsgSendProvider) -> None:
        self._providers[provider.channel_type] = provider

    def get(self, channel_type: ChannelType) -> MsgSendProvider:
        if channel_type not in self._providers:
            self._providers[channel_type] = LoggingProvider(channel_type)
        return self._providers[channel_type]

    @classmethod
    def default(cls) -> "ProviderRegistry":
        registry = cls()
        registry.register(WeChatProvider(registry._client))
        registry.register(DingTalkProvider(registry._client))
        registry.register(EmailProvider())
        registry.register(SmsProvider(registry._client))
        registry.register(AliyunPhoneProvider(registry._client))
        return registry
