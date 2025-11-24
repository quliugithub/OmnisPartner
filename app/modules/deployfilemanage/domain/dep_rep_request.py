"""Deployment request DTOs translated from the Java domain."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _first_non_empty(payload: Dict[str, Any], *keys: str, default: Optional[str] = None) -> str:
    for key in keys:
        if key in payload and payload[key] is not None:
            value = str(payload[key]).strip()
            if value:
                return value
    if default is not None:
        return default
    raise ValueError(f"Missing required field {keys[0]}")


@dataclass
class DepRepRequestInfoData:
    dep_task_id: str
    global_group_id: str
    nexus_group_id: str
    nexus_artifact_id: str
    version: str
    extension: str = "war"
    snapshot: bool = False
    resolved_global_name: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "DepRepRequestInfoData":
        version = _first_non_empty(payload, "version")
        extension = _first_non_empty(payload, "extension", "ext", default="war").lstrip(".")
        snapshot = payload.get("snapshot")
        if snapshot is None:
            snapshot = version.lower().endswith("snapshot")

        return cls(
            dep_task_id=_first_non_empty(payload, "dep_task_id", "depTaskId"),
            global_group_id=_first_non_empty(payload, "global_group_id", "globalGroupId"),
            nexus_group_id=_first_non_empty(
                payload,
                "nexus_group_id",
                "nexusGroupId",
                "groupid",
                "groupId",
            ),
            nexus_artifact_id=_first_non_empty(
                payload,
                "nexus_artifact_id",
                "nexusArtifactId",
                "artifactid",
                "artifactId",
            ),
            version=version,
            extension=extension or "war",
            snapshot=bool(snapshot),
        )


@dataclass
class DepRepRequestInfo:
    dep_event_id: str
    username: Optional[str]
    userid: Optional[str]
    hospital_code: Optional[str]
    req_id: Optional[str] = None
    dep_rep_data: List[DepRepRequestInfoData] = field(default_factory=list)
    only_download: bool = False
    not_record_download_progress: bool = False
    not_record_replace_info: bool = False
    do_deploy: bool = False
    send_file_to_omnis_server: bool = False
    nexus_url: Optional[str] = None
    auto_check_war: bool = False
    auto_restart_after_deploy: bool = False

    @classmethod
    def from_payload(
        cls,
        payload: List[Dict[str, Any]],
        *,
        username: Optional[str],
        userid: Optional[str],
        hospital_code: Optional[str],
        nexus_url: Optional[str],
        dep_event_id: Optional[str] = None,
    ) -> "DepRepRequestInfo":
        if not isinstance(payload, list) or not payload:
            raise ValueError("data payload must be a non-empty array")
        items = [DepRepRequestInfoData.from_dict(entry) for entry in payload]
        return cls(
            dep_event_id=dep_event_id or uuid.uuid4().hex,
            username=username,
            userid=userid,
            hospital_code=hospital_code,
            dep_rep_data=items,
            only_download=False,
            not_record_download_progress=True,
            not_record_replace_info=True,
            do_deploy=False,
            send_file_to_omnis_server=True,
            nexus_url=nexus_url,
        )
