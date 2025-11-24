"""AlertManager-facing HTTP endpoints."""

from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from app.modules.alertmanager.service import AlertManagerService, MsgSendException
from app.modules.alertmanager.util import AlertManagerConstant, AlertSourceType
from app.settings import Settings, get_settings

router = APIRouter(prefix="/alertmanager", tags=["alert-manager"])


def get_alert_manager_service(request: Request) -> AlertManagerService:
    container = getattr(request.app.state, "container", None)
    if not container:
        raise RuntimeError("Service container not initialized.")
    return container.alert_manager_service


@router.post("/push/zbx")
async def push_zbx(
    payload: str = Body(..., media_type="text/plain"),
    projectIdentify: str | None = None,
    notsendmsg: int | None = None,
    syncdata: int | None = None,
    svc: AlertManagerService = Depends(get_alert_manager_service),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    send_msg = not (notsendmsg == 1)
    try:
        response = await svc.push_alert_msg_zbx(payload, AlertSourceType.ZABBIX, send_msg)
        if syncdata != 1:
            svc.sync_data_to_slave(
                payload,
                projectIdentify or settings.alertmanager_project,
                AlertManagerConstant.MSG_TYPE_ZBX,
            )
        return response
    except MsgSendException as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/push/json")
async def push_json(
    payload: Dict[str, Any],
    alertsourcetype: AlertSourceType = AlertSourceType.BUSI,
    sendmsg: bool = True,
    svc: AlertManagerService = Depends(get_alert_manager_service),
) -> Dict[str, Any]:
    try:
        return await svc.push_msg(json.dumps(payload, ensure_ascii=False), alertsourcetype, sendmsg)
    except MsgSendException as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/pushaltermsgpms")
async def push_prometheus(
    payload: Dict[str, Any],
    projectIdentify: str | None = None,
    notsendmsg: int | None = None,
    syncdata: int | None = None,
    svc: AlertManagerService = Depends(get_alert_manager_service),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    send_msg = not (notsendmsg == 1)
    body = json.dumps(payload, ensure_ascii=False)
    try:
        response = await svc.push_msg(body, AlertSourceType.PROMETHEUS, send_msg)
        if syncdata != 1:
            svc.sync_data_to_slave(
                body,
                projectIdentify
                or payload.get("project")
                or settings.alertmanager_project,
                AlertManagerConstant.MSG_TYPE_JSON,
            )
        return response
    except MsgSendException as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
