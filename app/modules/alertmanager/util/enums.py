"""Enumerations for the AlertManager module."""

from __future__ import annotations

from enum import Enum


class AlertSourceType(str, Enum):
    ZABBIX = "0"
    PINPOINT = "1"
    ELK = "2"
    OMNIS = "3"
    PROMETHEUS = "4"
    BUSI = "8"
    OTHERS = "9"
    ALL = "-1"


class ChannelType(str, Enum):
    WEIXIN = "1"
    QQ = "2"
    DINGDING = "3"
    MAIL = "4"
    SHORTMSG = "5"
    ALIYUN_PHONE = "aliyun_phone"
    OTHERS = "9"


class AlertLevelType(str, Enum):
    UNKOWN = ("-1", "未知", "-")
    INFO = ("0", "信息", "☆")
    REMIND = ("1", "提醒", "★")
    WARN = ("2", "警告", "★★")
    IMPORTANT = ("3", "重要", "★★★")
    SERIOUS = ("4", "严重", "★★★★")
    DANGER = ("5", "危险", "★★★★★")

    def __new__(cls, level: str, desc: str, star: str) -> "AlertLevelType":  # type: ignore[override]
        obj = str.__new__(cls, level)
        obj._value_ = level
        obj.desc = desc
        obj.star = star
        return obj  # type: ignore[return-value]

    desc: str
    star: str
