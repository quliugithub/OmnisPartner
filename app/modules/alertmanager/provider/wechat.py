"""Enterprise WeChat message provider."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, Tuple

import httpx

from app.modules.alertmanager.domain import MsgSendEventBean
from app.modules.alertmanager.provider.base import BaseProvider
from app.modules.alertmanager.service.exceptions import MsgSendException
from app.modules.alertmanager.util import ChannelType

log = logging.getLogger(__name__)


@dataclass
class _TokenEntry:
    token: str
    expire_at: float


class WeChatProvider(BaseProvider):
    channel_type = ChannelType.WEIXIN

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        super().__init__()
        self._client = client or httpx.AsyncClient(timeout=10)
        self._token_cache: Dict[str, _TokenEntry] = {}
        self._lock = asyncio.Lock()

    async def send(self, event: MsgSendEventBean) -> None:
        self._apply_common_rules(event)

        record = event.alertitemRecord
        msg_channel = event.msgChannel
        provider = msg_channel.channel_providers
        if not provider:
            raise MsgSendException("微信通道缺少配置。")

        if not provider.wx_corpid or not provider.wx_secret or not provider.wx_base_url:
            raise MsgSendException("微信通道缺少 corpid/secret/base_url。")

        base_url = provider.wx_base_url.rstrip("/")
        token = await self._get_token(provider.wx_corpid, provider.wx_secret, base_url)

        payload = {
            "touser": provider.wx_touser or "@all",
            "toparty": provider.wx_toparty or "",
            "msgtype": "text",
            "agentid": provider.wx_agentId or "",
            "text": {"content": event.msg},
            "safe": "0",
        }

        url = f"{base_url}/message/send?access_token={token}"
        resp = await self._client.post(url, json=payload)
        data = resp.json()
        code = data.get("errcode", 0)

        if code in (40014, 42001):  # token expired
            log.info("WeChat token expired, refreshing token.")
            token = await self._get_token(provider.wx_corpid, provider.wx_secret, base_url, force=True)
            url = f"{base_url}/message/send?access_token={token}"
            resp = await self._client.post(url, json=payload)
            data = resp.json()
            code = data.get("errcode", 0)

        if code != 0:
            raise MsgSendException(f"微信消息发送失败: {data.get('errmsg')}")

    async def _get_token(self, corp_id: str, secret: str, base_url: str, force: bool = False) -> str:
        cache_key = f"{corp_id}:{secret}"
        if not force:
            entry = self._token_cache.get(cache_key)
            if entry and entry.expire_at > time.time():
                return entry.token

        async with self._lock:
            entry = self._token_cache.get(cache_key)
            if entry and entry.expire_at > time.time() and not force:
                return entry.token

            url = f"{base_url}/gettoken"
            resp = await self._client.get(url, params={"corpid": corp_id, "corpsecret": secret})
            data = resp.json()
            if data.get("errcode") != 0:
                raise MsgSendException(f"获取微信token失败: {data.get('errmsg')}")

            token = data["access_token"]
            expires = int(data.get("expires_in", 7200))
            self._token_cache[cache_key] = _TokenEntry(token=token, expire_at=time.time() + expires - 300)
            return token
