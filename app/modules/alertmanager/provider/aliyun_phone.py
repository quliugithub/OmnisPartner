"""Aliyun phone call provider using SingleCallByTts."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Dict

import httpx

from app.modules.alertmanager.domain import MsgSendEventBean
from app.modules.alertmanager.provider.base import BaseProvider
from app.modules.alertmanager.service.exceptions import MsgSendException
from app.modules.alertmanager.util import ChannelType

log = logging.getLogger(__name__)


class AliyunPhoneProvider(BaseProvider):
    channel_type = ChannelType.ALIYUN_PHONE
    DEFAULT_ENDPOINT = "https://dyvmsapi.aliyuncs.com/"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        super().__init__()
        self._client = client or httpx.AsyncClient(timeout=10)

    async def send(self, event: MsgSendEventBean) -> None:
        self._apply_common_rules(event)

        provider = event.msgChannel.channel_providers
        if not provider:
            raise MsgSendException("阿里云语音通道未配置。")

        access_key = provider.aliyun_access_key_id
        secret = provider.aliyun_access_key_secret
        tts_code = provider.aliyun_voice_template_code
        called_numbers = provider.aliyun_voice_called_numbers
        called_show = provider.aliyun_voice_called_show_number

        if not (access_key and secret and tts_code and called_numbers and called_show):
            raise MsgSendException("阿里云语音通道需要 access key、模板、主叫/被叫号码等配置。")

        endpoint = (provider.aliyun_api_url or self.DEFAULT_ENDPOINT).rstrip("/")
        called_number = called_numbers[0]  # 支持多号码时可循环

        params = {
            "Action": "SingleCallByTts",
            "RegionId": provider.aliyun_region or "cn-hangzhou",
            "Version": "2017-05-25",
            "AccessKeyId": access_key,
            "SignatureMethod": "HMAC-SHA1",
            "Timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Format": "JSON",
            "SignatureNonce": str(uuid.uuid4()),
            "SignatureVersion": "1.0",
            "CalledShowNumber": called_show,
            "CalledNumber": called_number,
            "TtsCode": tts_code,
            "TtsParam": provider.aliyun_voice_template_params or "{}",
        }

        params["Signature"] = self._sign_parameters(secret, params)

        resp = await self._client.get(endpoint, params=params)
        data = resp.json()

        if data.get("Code") != "OK":
            raise MsgSendException(f"阿里云语音调用失败: {data.get('Message')}")

    @staticmethod
    def _percent_encode(value: str) -> str:
        return urllib.parse.quote(value, safe="~")

    def _sign_parameters(self, secret: str, params: Dict[str, str]) -> str:
        sorted_pairs = sorted((k, v) for k, v in params.items())
        canonicalized = "&".join(
            f"{self._percent_encode(k)}={self._percent_encode(str(v))}" for k, v in sorted_pairs
        )
        string_to_sign = f"GET&%2F&{self._percent_encode(canonicalized)}"
        key = f"{secret}&"
        signature = hmac.new(key.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1)
        return base64.b64encode(signature.digest()).decode("utf-8")
