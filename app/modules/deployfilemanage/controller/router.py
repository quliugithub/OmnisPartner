"""FastAPI routes mirroring DepAndReplaceController."""

from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.modules.deployfilemanage.service.manager import DeployFileManageService

router = APIRouter(prefix="/deployfilemanage", tags=["deploy-file-manage"])


def get_service(request: Request) -> DeployFileManageService:
    container = getattr(request.app.state, "container", None)
    if not container or not getattr(container, "deployfile_service", None):
        raise HTTPException(status_code=500, detail="Deploy file service not initialized.")
    return container.deployfile_service


def require_deploy_enabled(request: Request) -> None:
    switches = getattr(request.app.state, "switches", None)
    if switches and not getattr(switches, "deploy_on", lambda: True)():
        raise HTTPException(status_code=503, detail="deploy feature is disabled")


@router.get("/nexus2localdiskdownload")
async def nexus_download(
    filegroup: str,
    fileName: str,
    version: str,
    extension: str,
    project: str | None = None,
    svc: DeployFileManageService = Depends(get_service),
):
    result = svc.download_nexus_to_disk(
        filegroup=filegroup,
        fileName=fileName,
        version=version,
        extension=extension,
        project=project,
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.message)
    meta = result.data
    return FileResponse(
        meta["filePath"],
        media_type="application/octet-stream",
        filename=meta["fileName"],
    )


@router.post("/predowloadnexusfile")
async def pre_download(payload: Dict[str, Any], svc: DeployFileManageService = Depends(get_service)):
    data = payload.get("data")
    if not isinstance(data, str):
        raise HTTPException(status_code=400, detail="data must be a JSON string")
    return svc.pre_download(data=data)


@router.get("/getstaticpathbyagv/{group}/{artifactid}/{version}")
async def get_static_path(
    group: str,
    artifactid: str,
    version: str,
    svc: DeployFileManageService = Depends(get_service),
):
    return svc.get_static_path(group=group, artifactid=artifactid, version=version)


@router.post("/dowloadnexusfilebyagv")
async def download_by_agv(payload: Dict[str, Any], svc: DeployFileManageService = Depends(get_service)):
    data = payload.get("data")
    if not isinstance(data, str):
        raise HTTPException(status_code=400, detail="data must be a JSON string")
    return svc.download_by_agv(data=data)


@router.post("/onlydowloadnexusfile")
async def only_download(payload: Dict[str, Any], svc: DeployFileManageService = Depends(get_service)):
    data = payload.get("data")
    if not isinstance(data, str):
        raise HTTPException(status_code=400, detail="data must be a JSON string")
    return svc.only_download(
        data=data,
        nexus_url=payload.get("nexus_url") or payload.get("nexusUrl"),
        username=payload.get("username"),
        userid=payload.get("userid"),
        hospital_code=payload.get("hospital_code") or payload.get("hospitalCode"),
    )


@router.post("/getlatestnexusversion")
async def get_latest(payload: Dict[str, Any], svc: DeployFileManageService = Depends(get_service)):
    return svc.get_latest_version(**payload)


@router.post("/checknexusversion")
async def check_version(payload: Dict[str, Any], svc: DeployFileManageService = Depends(get_service)):
    return svc.check_version(**payload)


@router.post("/replaceproperties")
async def replace_properties(payload: Dict[str, Any], svc: DeployFileManageService = Depends(get_service)):
    content = payload.get("content")
    env_name = payload.get("envGlobalName")
    if not isinstance(content, str) or not isinstance(env_name, str):
        raise HTTPException(status_code=400, detail="content and envGlobalName must be strings")
    return svc.replace_properties(content=content, env_global_name=env_name)


@router.post("/jboss/replace")
async def jboss_replace(payload: Dict[str, Any], svc: DeployFileManageService = Depends(get_service)):
    required = ["filePath", "deployId", "artifactId", "globalNames"]
    for key in required:
        if key not in payload:
            raise HTTPException(status_code=400, detail=f"{key} is required")
    return svc.jboss_replace_preview(
        file_path=payload["filePath"],
        deploy_id=payload["deployId"],
        artifact_id=payload["ArtifactId" if "ArtifactId" in payload else "artifactId"] if "ArtifactId" in payload else payload["artifactId"],
        global_names=list(payload.get("globalNames") or []),
    )


@router.post("/depandrep")
async def dep_and_rep(
    payload: Dict[str, Any],
    svc: DeployFileManageService = Depends(get_service),
    _: None = Depends(require_deploy_enabled),
):
    required = ["username", "userid", "req_id", "hospital_code", "data"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing parameters: {', '.join(missing)}")
    extra = dict(payload.get("extra") or {})
    if payload.get("nexus_url"):
        extra.setdefault("nexus_url", payload["nexus_url"])
    return svc.deploy_and_replace(
        username=payload["username"],
        userid=payload["userid"],
        req_id=payload["req_id"],
        hospital_code=payload["hospital_code"],
        data=payload["data"],
        do_deploy=True,
        extra=extra,
    )


@router.post("/showcheckwarstatus")
async def show_checkwar_status(payload: Dict[str, Any], svc: DeployFileManageService = Depends(get_service)):
    username = payload.get("username")
    task_ids = payload.get("taskIds") or payload.get("task_ids")
    if not isinstance(username, str) or not username:
        raise HTTPException(status_code=400, detail="username is required")
    if isinstance(task_ids, str):
        try:
            task_ids = json.loads(task_ids)
        except Exception:
            raise HTTPException(status_code=400, detail="taskIds must be an array or JSON array")
    if not isinstance(task_ids, list) or not task_ids:
        raise HTTPException(status_code=400, detail="taskIds must be a non-empty array")
    return svc.show_checkwar_status(username=username, task_ids=task_ids)
