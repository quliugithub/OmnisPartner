"""Channel provider configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ChannelProvider:
    msg_send_provider_id: str
    provider_name: str = ""
    provider_type: str | None = None

    # WeChat (corp)
    wx_corpid: str | None = None
    wx_secret: str | None = None
    wx_agentId: str | None = None
    wx_touser: str | None = None
    wx_toparty: str | None = None
    wx_base_url: str | None = None

    # DingTalk
    ding_robot_url: str | None = None
    ding_robot_keywords: str | None = None
    ding_robot_sign: str | None = None
    ding_robot_ip: str | None = None

    # Mail
    mail_sender: str | None = None
    mail_username: str | None = None
    mail_pwd: str | None = None
    mail_sender_smtp: str | None = None
    mail_sender_smtp_port: int | None = None
    mail_recive_address: str | None = None
    mail_recive_user_groups: str | None = None
    mail_recive_users: str | None = None
    allMailAddress: List[str] = field(default_factory=list)

    # SMS / MAS
    mas_recive_users: str | None = None
    mas_recive_user_groups: str | None = None
    mas_recive_pthones: List[str] = field(default_factory=list)
    mas_sender_user: str | None = None
    mas_sender_pwd: str | None = None
    mas_sender_name: str | None = None
    mas_sender_url: str | None = None
    mas_type: str | None = None
    mas_sign: str | None = None
    mas_other_1: str | None = None
    mas_other_2: str | None = None
    mas_other_3: str | None = None

    # Aliyun phone call
    aliyun_access_key_id: str | None = None
    aliyun_access_key_secret: str | None = None
    aliyun_voice_template_code: str | None = None
    aliyun_voice_template_params: str | None = None
    aliyun_voice_called_show_number: str | None = None
    aliyun_voice_called_numbers: List[str] = field(default_factory=list)
    aliyun_region: str | None = None
    aliyun_api_url: str | None = None

    metadata: Dict[str, str] = field(default_factory=dict)
