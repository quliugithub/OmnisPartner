"""Dataclasses mirroring deployfilemanage domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class FileGetResponse:
    success: bool = False
    message: str = ""
    file_path: Optional[Path] = None


@dataclass
class ReplaceDetails:
    updated_items: Dict[str, List[str]] = field(default_factory=dict)
    new_items: Dict[str, str] = field(default_factory=dict)
    untouched_items: Dict[str, str] = field(default_factory=dict)
    spring_boot_items: Dict[str, List[str]] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)
    other_infos: Dict[str, str] = field(default_factory=dict)
    nexus_index: Optional["NexusIndex"] = None
    global_name: Optional[str] = None
    global_id: Optional[str] = None

    def add_updated(self, key: str, old_value: str, new_value: str) -> None:
        self.updated_items[key] = [old_value, new_value]

    def add_new(self, key: str, value: str) -> None:
        self.new_items[key] = value

    def add_untouched(self, key: str, value: str) -> None:
        self.untouched_items[key] = value

    # Backwards compatible helpers
    def addUpdated(self, key: str, old_value: str, new_value: str) -> None:  # noqa: N802
        self.add_updated(key, old_value, new_value)

    def addNewAddItems(self, key: str, value: str) -> None:  # noqa: N802
        self.add_new(key, value)

    def addnotUpdatedItems(self, key: str, value: str) -> None:  # noqa: N802
        self.add_untouched(key, value)

    def add_spring_boot(self, key: str, old_value: str, new_value: str) -> None:
        self.spring_boot_items[key] = [old_value, new_value]

    def add_other_info(self, key: str, value: str) -> None:
        self.other_infos[key] = value


@dataclass
class DepServerInfo:
    server_ip: str = ""
    os_user_name: str = ""
    os_user_pwd: str = ""
    remote_connect_port: str = ""
    server_os: Optional[str] = None
    deploy_dir: Optional[str] = None
    soft_home_dir: Optional[str] = None
    singledep_bak_path: Optional[str] = None
    service_port: Optional[str] = None
    manage_port: Optional[str] = None
    portoffset: Optional[str] = None
    appurl: Optional[str] = None


@dataclass
class NexusIndex:
    artifact_id: str
    deploy_event_id: str
    version: Optional[str] = None
    group_id: Optional[str] = None
    extension: Optional[str] = None
    repository: Optional[str] = None
    current_user_id: Optional[str] = None
    current_user_name: Optional[str] = None
    current_tasks: List[str] = field(default_factory=list)
    deploy_type: Optional[str] = None
    current_file_path: Optional[str] = None
    current_replace_path: Optional[str] = None
    task_ip_map: Dict[str, "DepServerInfo"] = field(default_factory=dict)
    is_snapshot: bool = False


@dataclass
class FileReplaceOneResponse:
    success: bool = False
    message: str = ""
    file_path: Optional[str] = None
    deploy_id: Optional[str] = None
    task_id: Optional[str] = None
    global_name: Optional[str] = None
    global_id: Optional[str] = None
    deploy_type: Optional[str] = None
    time_log: Optional[str] = None
    total_time: int = 0
    artifact_name: Optional[str] = None
    war_version: Optional[str] = None
    dep_server_info: Optional[DepServerInfo] = None
    username: Optional[str] = None
    replace_details: Optional[ReplaceDetails] = None


@dataclass
class DepOnceGlobalInfos:
    global_task_map: Dict[str, Set[str]] = field(default_factory=dict)
    global_infos: Dict[str, Dict[str, str]] = field(default_factory=dict)
    global_ids: Dict[str, str] = field(default_factory=dict)


@dataclass
class GetAndReplaceRequest:
    nexus_index: Optional[NexusIndex] = None
    dep_once_global_infos: Optional[DepOnceGlobalInfos] = None
    only_download: bool = False
    record_download_progress: bool = True
    record_replace_info: bool = True
    do_deploy: bool = False


@dataclass
class ReplaceStrategyRequest:
    file_get_response: FileGetResponse
    get_and_replace_request: GetAndReplaceRequest
    only_download: bool = False
    record_replace_info: bool = True
    do_deploy: bool = False


@dataclass
class DepFileGetReplaceResponse:
    final_files: List[FileReplaceOneResponse] = field(default_factory=list)


@dataclass
class DeployReplaceWarRecord:
    rep_war_id: str
    dep_event_id: str
    dep_rep_id: str
    global_param_id: str
    war_artifactid: str
    war_groupid: str
    war_version: str
    war_rep_location: str
    comments: str = ""


@dataclass
class DeployConfDiffDetailRecord:
    diff_id: str
    rep_war_id: str
    param_key: str
    param_org_value: str
    param_rep_value: str
    not_replace: str
    comments: str = ""


@dataclass
class DeployTaskListEntry:
    dep_task_id: str
    war_artifactid: str
    war_groupid: str
    global_id: str
    server_ip: str
    deploydir: Optional[str] = None
    server_id: Optional[str] = None
    lastversion: Optional[str] = None
    soft_home_dir: Optional[str] = None
    os_user_name: Optional[str] = None
    os_user_pwd: Optional[str] = None
    appurl: Optional[str] = None
    hospital_code: Optional[str] = None
    soft_type: Optional[str] = None
    portoffset: Optional[str] = None
    service_port: Optional[str] = None
    manage_port: Optional[str] = None
    server_os: Optional[str] = None
    remote_connect_port: Optional[str] = None
    install_soft_id: Optional[str] = None
    lastdeployver: Optional[str] = None
    singledep_bak_path: Optional[str] = None


@dataclass
class DeployRequest:
    ip: str
    port: str
    deploy_type: str
    deploy_file_path: str
    artifact_war_name: str
    war_version: str
    username: str
    task_id: str
    dep_event_id: str
    dep_server_info: Optional[DepServerInfo] = None
    base_url: Optional[str] = None
    spring_boot_server_port: Optional[str] = None
    is_undeploy: bool = False
    snapshot_war_long_version: Optional[str] = None
    properties_some_key_value: Dict[str, str] = field(default_factory=dict)
    add_time: datetime = field(default_factory=datetime.utcnow)
    current_zip_deploy_dir: Optional[str] = None
    singledep_bak_path: Optional[str] = None
    windows_trans_file_default_path: Optional[str] = None

    def request_key(self) -> str:
        return f"{self.ip}#{self.port or 'NULL'}"

    @property
    def is_win(self) -> bool:
        if not self.dep_server_info:
            return False
        server_os = (self.dep_server_info.server_os or "").lower()
        return "windows" in server_os


@dataclass
class DeployResultRecord:
    msg: str = "OK"
    msg_full: str = "OK"
    down_rep_time_secs: float = 0.0
    prepare_time_secs: float = 0.0
    deploy_time_secs: float = 0.0
    task_id: Optional[str] = None
    deploy_id: Optional[str] = None
    username: Optional[str] = None
    war_artifact_id: Optional[str] = None
    war_group_id: Optional[str] = None
    war_version: Optional[str] = None
    success: bool = True

    def mark_success(self, message: str = "OK") -> None:
        self.msg = message
        self.msg_full = message
        self.success = True

    def mark_failure(self, message: str) -> None:
        self.msg = message
        self.msg_full = message
        self.success = False
