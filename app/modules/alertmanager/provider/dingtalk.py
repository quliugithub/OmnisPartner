"""DingTalk robot provider."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from typing import Dict

import httpx

from app.modules.alertmanager.domain import MsgSendEventBean
from app.modules.alertmanager.provider.base import BaseProvider
from app.modules.alertmanager.service.exceptions import MsgSendException
from app.modules.alertmanager.util import ChannelType

log = logging.getLogger(__name__)


class DingTalkProvider(BaseProvider):
    channel_type = ChannelType.DINGDING

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        super().__init__()
        self._client = client or httpx.AsyncClient(timeout=10)

    async def send(self, event: MsgSendEventBean) -> None:
        self._apply_common_rules(event)

        msg_channel = event.msgChannel
        provider = msg_channel.channel_providers
        if not provider or not provider.ding_robot_url:
            raise MsgSendException("钉钉机器人URL未配置。")
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(provider.ding_robot_url)
        token = parse_qs(parsed.query)["access_token"][0]
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        params = {}
        if provider.ding_robot_sign:
            sign, timestamp = self._generate_sign(provider.ding_robot_sign)
            params["timestamp"] = timestamp
            params["sign"] = sign
            params["access_token"] = token

        payload: Dict[str, object] = {
            "msgtype": "text",
            "text": {"content": event.msg},
        }

        resp = await self._client.post(base_url, params=params or None, json=payload)
        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise MsgSendException(f"钉钉发送失败: {data.get('errmsg')}")

    @staticmethod
    def _generate_sign(secret: str) -> tuple[str, str]:
        timestamp = str(int(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        h = hmac.new(secret.encode("utf-8"), string_to_sign, digestmod=hashlib.sha256)
        sign = base64.b64encode(h.digest()).decode("utf-8")
        return sign, timestamp
