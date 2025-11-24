"""Constants translated from the Java AlertManager module."""

from __future__ import annotations


class AlertManagerConstant:
    FORBID_YES = "1"
    FORBID_NO = "0"
    FORBID_YES_INT = 1
    FORBID_NO_INT = 0

    CAN_NOT_USE = "1"

    EVENT_TYPE_CREATE = "1"
    EVENT_TYPE_RECOVER = "0"

    IS_RECOVER_YES = "1"
    IS_RECOVER_NO = "0"

    CONFIRM_YES = "1"
    CONFIRM_NO = "0"
    CONFIRM_CLOSE = "2"

    MSG_TYPE_ZBX = 1
    MSG_TYPE_JSON = 2

    ALERTITEM_NOTSHOW_YES = "1"
    ALERTITEM_NOTSHOW_NO = "0"

    MSG_SEND_FORBID_NOT_SEND = "1"
    MSG_SEND_FORBID_NOT_SHOWANDSEND = "2"

    BUSI_MSG_SEND_ALERT_CODE = "BUSI001"
    PUBWAR_MSG_SEND_ALERT_CODE = "BUSI999"

    PROXY_MSG_SEND_NATIVE_TOKEN = "67c6cb5049d5xxxxab00199cabdcf433yyyb895376ec11e99da8005056b79ffb"
    DEPLOY_NATIVE_MSGSEND_BUSI = "api_native_deploy_msgsend"


class MsgSendDefaultInfos:
    ALERTCODE_DEFAULT_PINPOINT = "PP000"
    ALERTCODE_DEFAULT_ESB = "ESB000"
    ALERTCODE_DEFAULT_BUSI = "BUSI000"

    DEFAULT_ALERT_CODE_JSONSTR = "alertcode"
    DEFAULT_ALERT_SOURCE_TYPE_JSONSTR = "alertsourcetype"
    DEFAULT_HOSTNAME_JSONSTR = "hostname"
    DEFAULT_MSG_JSONSTR = "msg"
