"""Deploy file manage service implementation."""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.modules.deployfilemanage.domain import (
    ArtifactCoordinates,
    DepRepRequestInfo,
    DepOnceGlobalInfos,
    DeployConfDiffDetailRecord,
    DeployReplaceWarRecord,
    FileGetResponse,
    FileReplaceOneResponse,
    GetAndReplaceRequest,
    NexusIndex,
    DepServerInfo,
    DeployRequest,
    ReplaceDetails,
    ReplaceStrategyRequest,
    DeployTaskListEntry,
)
from app.modules.deployfilemanage.fileget import NexusDownloader
from app.modules.deployfilemanage.filereplace import SimplePropertiesContentReplace, CbhJbossReplaceStrategy
from app.modules.deployfilemanage.integration import GetRepDepIntegrationInvoker, NexusTransferService
from app.modules.deployfilemanage.repositories import DepRepRepository
from app.modules.deployfilemanage.service.deploy_process import DeployProcessService
from app.modules.deployfilemanage.deploy import DeployInvokerService
from app.settings import Settings
from app.modules.deployfilemanage.domain.constants import REPLACE_NEW, REPLACE_NOT, REPLACE_YES

log = logging.getLogger(__name__)


@dataclass
class OperationResult:
    ok: bool
    message: str
    data: Any = None

    def as_dict(self) -> Dict[str, Any]:
        payload = {"status": "true" if self.ok else "false", "msg": self.message}
        if self.data is not None:
            payload["data"] = self.data
        return payload


class DeployFileManageService:
    """Partial translation of DepAndReplaceController focused on Nexus endpoints."""

    def __init__(
        self,
        settings: Settings,
        dep_rep_repo: Optional[DepRepRepository] = None,
        deploy_process_service: Optional[DeployProcessService] = None,
        deploy_invoker: Optional[DeployInvokerService] = None,
    ) -> None:
        self.settings = settings
        self.nexus_downloader = NexusDownloader(settings)
        self.static_dir = Path("new/static")
        self.static_dir.mkdir(parents=True, exist_ok=True)
        self.dep_rep_repo = dep_rep_repo
        self.deploy_process = deploy_process_service
        self.deploy_invoker = deploy_invoker
        self.properties_replacer = (
            SimplePropertiesContentReplace(dep_rep_repo) if dep_rep_repo else None
        )
        replace_root = Path(settings.deploy_replace_path)
        replace_root.mkdir(parents=True, exist_ok=True)
        self.download_workers = max(1, int(getattr(settings, "deploy_download_workers", 4)))
        self.jboss_replace_strategy = CbhJbossReplaceStrategy(
            replace_root,
            self.properties_replacer,
            event_publisher=self._handle_replace_details,
        )
        self.integration_invoker = (
            GetRepDepIntegrationInvoker(
                downloader=self.nexus_downloader,
                strategy=self.jboss_replace_strategy,
                repository=dep_rep_repo,
            )
            if dep_rep_repo
            else None
        )
        self.nexus_transfer = NexusTransferService()

    # ------------------------------------------------------------------ Nexus helpers
    def download_nexus_to_disk(
        self,
        *,
        filegroup: str,
        fileName: str,
        version: str,
        extension: str,
        project: Optional[str] = None,
    ) -> OperationResult:
        try:
            coords = ArtifactCoordinates(
                groupid=filegroup,
                artifactid=fileName,
                version=version,
                extension=extension.lstrip("."),
            )
            path = self.nexus_downloader.download(coords)
            meta = self._build_metadata(coords, path)
            return OperationResult(True, "ok", meta)
        except Exception as exc:  # noqa: BLE001
            return OperationResult(False, str(exc))

    def pre_download(self, *, data: str) -> Dict[str, Any]:
        return self._handle_batch_download(data, send_to_static=False)

    def get_static_path(self, *, group: str, artifactid: str, version: str) -> str:
        coords = ArtifactCoordinates(groupid=group, artifactid=artifactid, version=version)
        try:
            meta = self._download_and_copy(coords)
            return meta["staticName"]
        except Exception as exc:  # noqa: BLE001
            return f"ERROR:{exc}"

    def download_by_agv(self, *, data: str) -> Dict[str, Any]:
        return self._handle_batch_download(data, send_to_static=True)

    def only_download(
        self,
        *,
        data: str,
        nexus_url: Optional[str] = None,
        username: Optional[str] = None,
        userid: Optional[str] = None,
        hospital_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.integration_invoker:
            return OperationResult(False, "deploy repository is required for this operation").as_dict()
        try:
            parsed_payload = json.loads(data)
        except json.JSONDecodeError:
            return OperationResult(False, "data must be a JSON array").as_dict()
        try:
            request = DepRepRequestInfo.from_payload(
                parsed_payload,
                username=username,
                userid=userid,
                hospital_code=hospital_code,
                nexus_url=nexus_url,
            )
        except ValueError as exc:
            return OperationResult(False, str(exc)).as_dict()

        try:
            response = self.integration_invoker.request_invoke_sync(request)
            if request.send_file_to_omnis_server:
                self.nexus_transfer.send_files(response)
            data_payload = [self._serialize_replace_response(resp) for resp in response.final_files]
            return OperationResult(True, "ok", data_payload).as_dict()
        except Exception as exc:  # noqa: BLE001
            log.exception("onlydowloadnexusfile failed")
            return OperationResult(False, str(exc)).as_dict()

    def get_latest_version(self, *, groupid: str, artifactid: str, nexus_url: Optional[str] = None) -> Dict[str, Any]:
        try:
            version = self.nexus_downloader.get_latest_version(groupid.strip(), artifactid.strip(), nexus_url)
            return OperationResult(True, "ok", {"version": version}).as_dict()
        except Exception as exc:  # noqa: BLE001
            return OperationResult(False, str(exc)).as_dict()

    def check_version(
        self,
        *,
        groupid: str,
        artifactid: str,
        version: str,
        nexus_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            exists = self.nexus_downloader.version_exists(
                groupid.strip(),
                artifactid.strip(),
                version.strip(),
                nexus_url,
            )
            return OperationResult(True, "ok", {"exists": exists}).as_dict()
        except Exception as exc:  # noqa: BLE001
            return OperationResult(False, str(exc)).as_dict()

    # ------------------------------------------------------------------ Placeholder stubs for remaining endpoints
    def dep_and_rep(self, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "depandrep not implemented").as_dict()

    def dep_and_rep_show(self, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "depandrepshow not implemented").as_dict()

    def deploy(self, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "deploy not implemented").as_dict()

    def undeploy(self, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "undeploy not implemented").as_dict()

    def check_jboss_status(self, sync: bool = False, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "checkjboss not implemented").as_dict()

    def kill_process(self, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "killprocess not implemented").as_dict()

    def kill_running_process(self, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "killruningrocess not implemented").as_dict()

    def get_local_link(self, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "getlocaldeploylink not implemented").as_dict()

    def create_local_link(self, env: bool = False, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "createlocaldeploylink not implemented").as_dict()

    def toggle_check_war(self, enable: bool | None = None, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "checkwar toggles not implemented").as_dict()

    def do_deploy(self, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "dodeploy not implemented").as_dict()

    def query_env_info(self) -> Dict[str, Any]:
        return OperationResult(False, "queryenvdeployinfo not implemented").as_dict()

    def refresh_infos(self) -> Dict[str, Any]:
        return OperationResult(False, "refreshdeployinfos not implemented").as_dict()

    def show_deploy_queue(self, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "showdeployquene not implemented").as_dict()

    def single_file_rollback(self, full: bool = False, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "singlefile rollback not implemented").as_dict()

    def agg_pub_file_zip(self, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "aggpubfilezip not implemented").as_dict()

    def single_file_online_download(self, **kwargs) -> Dict[str, Any]:
        return OperationResult(False, "singlefileonlinedownload not implemented").as_dict()

    def get_partner_conf(self) -> str:
        return "partner.conf not implemented"

    def get_backend_conf(self) -> str:
        return "omnisbackend.conf not implemented"

    def do_refresh(self) -> Dict[str, Any]:
        return OperationResult(False, "dorefresh not implemented").as_dict()

    # ------------------------------------------------------------------ internal helpers
    def _handle_replace_details(self, details: List[ReplaceDetails]) -> None:
        if not self.dep_rep_repo:
            log.debug("Replace details event ignored because repository is not configured.")
            return
        prepared = [detail for detail in details if detail and detail.nexus_index]
        if not prepared:
            return
        event_id = next((d.nexus_index.deploy_event_id for d in prepared if d.nexus_index.deploy_event_id), None)
        if not event_id:
            log.debug("Replace details skipped because deploy event id is missing.")
            return
        all_tasks: List[str] = []
        for detail in prepared:
            all_tasks.extend(detail.nexus_index.current_tasks or [])
        if not all_tasks:
            log.debug("Replace details skipped because no tasks were associated with event %s.", event_id)
            return
        # Preserve order while removing duplicates
        deduped_tasks = list(dict.fromkeys(filter(None, all_tasks)))
        task_once_map = self.dep_rep_repo.query_task_once_ids(event_id, deduped_tasks)
        if not task_once_map:
            log.info(
                "Skip persisting replace details for event %s because task_once ids are missing (likely preview mode).",
                event_id,
            )
            return

        war_records: List[DeployReplaceWarRecord] = []
        diff_records: List[DeployConfDiffDetailRecord] = []
        for detail in prepared:
            nexus = detail.nexus_index
            for _task_id in deduped_tasks:
                rep_war_id = uuid.uuid4().hex
                war_records.append(
                    DeployReplaceWarRecord(
                        rep_war_id=rep_war_id,
                        dep_event_id=event_id,
                        dep_rep_id="-1",
                        global_param_id=detail.global_id or "-1",
                        war_artifactid=nexus.artifact_id,
                        war_groupid=nexus.group_id or "",
                        war_version=nexus.version or "",
                        war_rep_location=detail.metadata.get("file_path")
                        or nexus.current_file_path
                        or "",
                        comments="X",
                    )
                )
                diff_records.extend(self._build_diff_records(rep_war_id, detail))

        if war_records:
            self.dep_rep_repo.add_deploy_replace_war(war_records)
        if diff_records:
            self.dep_rep_repo.add_deploy_conf_diff_detail(diff_records)

    def _build_diff_records(
        self,
        rep_war_id: str,
        detail: ReplaceDetails,
    ) -> List[DeployConfDiffDetailRecord]:
        rows: List[DeployConfDiffDetailRecord] = []
        for key, value in detail.new_items.items():
            rows.append(
                DeployConfDiffDetailRecord(
                    diff_id=uuid.uuid4().hex,
                    rep_war_id=rep_war_id,
                    param_key=key,
                    param_org_value="",
                    param_rep_value=value,
                    not_replace=REPLACE_NEW,
                    comments="new add",
                )
            )
        for key, value in detail.untouched_items.items():
            rows.append(
                DeployConfDiffDetailRecord(
                    diff_id=uuid.uuid4().hex,
                    rep_war_id=rep_war_id,
                    param_key=key,
                    param_org_value=value,
                    param_rep_value=value,
                    not_replace=REPLACE_NOT,
                    comments="not modify",
                )
            )
        for key, values in detail.updated_items.items():
            old_value, new_value = values
            rows.append(
                DeployConfDiffDetailRecord(
                    diff_id=uuid.uuid4().hex,
                    rep_war_id=rep_war_id,
                    param_key=key,
                    param_org_value=old_value,
                    param_rep_value=new_value,
                    not_replace=REPLACE_YES,
                    comments="update",
                )
            )
        return rows

    def _handle_batch_download(
        self,
        data: str,
        *,
        send_to_static: bool,
        override_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            coords_list = list(self._parse_download_payload(data))
            if not coords_list:
                return OperationResult(True, "ok", []).as_dict()

            self.log.info(
                "Batch Nexus download request count=%d sendToStatic=%s overrideUrl=%s",
                len(coords_list),
                send_to_static,
                override_url,
            )
            max_workers = min(self.download_workers, len(coords_list))
            results: List[Optional[Dict[str, Any]]] = [None] * len(coords_list)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(
                        self._download_single_meta,
                        coords,
                        send_to_static,
                        override_url,
                        username=None,
                        userid=None,
                    ): idx
                    for idx, coords in enumerate(coords_list)
                }
                try:
                    for future in as_completed(future_map):
                        idx = future_map[future]
                        results[idx] = future.result()
                except Exception:
                    for future in future_map:
                        future.cancel()
                    raise

            ordered = [meta for meta in results if meta]
            return OperationResult(True, "ok", ordered).as_dict()
        except Exception as exc:  # noqa: BLE001
            return OperationResult(False, str(exc)).as_dict()

    def _parse_download_payload(self, data: str) -> Iterable[ArtifactCoordinates]:
        items = json.loads(data)
        if not isinstance(items, list):
            raise ValueError("data payload must be a JSON array")
        for item in items:
            yield ArtifactCoordinates(
                groupid=item.get("groupid") or item.get("group"),
                artifactid=item.get("artifactid") or item.get("artifact"),
                version=item.get("version"),
                extension=(item.get("extension") or "jar").lstrip("."),
            )

    def _build_metadata(self, coords: ArtifactCoordinates, path: Path) -> Dict[str, Any]:
        stat = path.stat()
        return {
            "groupid": coords.groupid,
            "artifactid": coords.artifactid,
            "version": coords.version,
            "extension": coords.extension,
            "filePath": str(path),
            "fileName": path.name,
            "size": stat.st_size,
        }

    def _copy_to_static(self, path: Path) -> Dict[str, Any]:
        dest = self.static_dir / path.name
        counter = 1
        while dest.exists():
            dest = self.static_dir / f"{counter}_{path.name}"
            counter += 1
        shutil.copyfile(path, dest)
        return {"staticPath": str(dest), "staticName": dest.name}

    def _download_and_copy(self, coords: ArtifactCoordinates) -> Dict[str, Any]:
        path = self.nexus_downloader.download(coords)
        meta = self._build_metadata(coords, path)
        meta.update(self._copy_to_static(path))
        return meta

    def _download_single_meta(
        self,
        coords: ArtifactCoordinates,
        send_to_static: bool,
        override_url: Optional[str],
        username: Optional[str] = None,
        userid: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.log.debug(
            "Downloading coords group=%s artifact=%s version=%s override=%s",
            coords.groupid,
            coords.artifactid,
            coords.version,
            bool(override_url),
        )
        path = self.nexus_downloader.download(
            coords,
            override_url,
            username=username,
            userid=userid,
        )
        meta = self._build_metadata(coords, path)
        if send_to_static:
            meta.update(self._copy_to_static(path))
        self.log.debug(
            "Downloaded coords group=%s artifact=%s -> %s",
            coords.groupid,
            coords.artifactid,
            meta.get("filePath"),
        )
        return meta

    def _serialize_replace_response(self, response: FileReplaceOneResponse) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "success": response.success,
            "message": response.message,
            "filePath": response.file_path,
            "taskId": response.task_id,
            "globalName": response.global_name,
            "globalId": response.global_id,
            "deployId": response.deploy_id,
            "artifact": response.artifact_name,
            "warVersion": response.war_version,
        }
        return payload

    # ------------------------------------------------------------------ public helper for property replacement
    def replace_properties(self, *, content: str, env_global_name: str) -> Dict[str, Any]:
        if not self.properties_replacer or not self.dep_rep_repo:
            return OperationResult(False, "properties replacer not configured").as_dict()
        try:
            replaced = self.properties_replacer.replace(content, env_global_name)
            return OperationResult(True, "ok", {"content": replaced}).as_dict()
        except Exception as exc:  # noqa: BLE001
            return OperationResult(False, str(exc)).as_dict()

    def jboss_replace_preview(
        self,
        *,
        file_path: str,
        deploy_id: str,
        artifact_id: str,
        global_names: List[str],
    ) -> Dict[str, Any]:
        request = ReplaceStrategyRequest(
            file_get_response=FileGetResponse(success=True, file_path=Path(file_path)),
            get_and_replace_request=GetAndReplaceRequest(
                nexus_index=NexusIndex(artifact_id=artifact_id, deploy_event_id=deploy_id),
                dep_once_global_infos=DepOnceGlobalInfos(
                    global_task_map={name: set() for name in global_names}
                ),
            ),
            only_download=False,
            record_replace_info=False,
            do_deploy=False,
        )
        try:
            response = self.jboss_replace_strategy.do_replace(request)
            return OperationResult(
                True,
                "ok",
                [resp.file_path for resp in response.final_files],
            ).as_dict()
        except Exception as exc:  # noqa: BLE001
            return OperationResult(False, str(exc)).as_dict()

    def deploy_and_replace(
        self,
        *,
        username: str,
        userid: str,
        req_id: str,
        hospital_code: str,
        data: str,
        do_deploy: bool,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        extra = extra or {}
        try:
            request = self._build_dep_request(
                username=username,
                userid=userid,
                req_id=req_id,
                hospital_code=hospital_code,
                data=data,
                do_deploy=do_deploy,
                extra=extra,
            )
        except ValueError as exc:
            return OperationResult(False, str(exc)).as_dict()

        if not self.integration_invoker:
            return OperationResult(False, "deploy integration is not configured").as_dict()

        if do_deploy:
            if not self.deploy_process or not self.deploy_invoker:
                return OperationResult(False, "deploy services unavailable").as_dict()
            return self._handle_deploy_flow(request)

        try:
            response = self.integration_invoker.request_invoke_sync(request)
            return OperationResult(
                True,
                "ok",
                [self._serialize_replace_response(resp) for resp in response.final_files],
            ).as_dict()
        except Exception as exc:  # noqa: BLE001
            log.exception("deploy_and_replace failed")
            return OperationResult(False, str(exc)).as_dict()

    # ------------------------------------------------------------------ internal helpers for deploy flow
    def _build_dep_request(
        self,
        *,
        username: str,
        userid: str,
        req_id: str,
        hospital_code: str,
        data: str,
        do_deploy: bool,
        extra: Dict[str, Any],
    ) -> DepRepRequestInfo:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:  # noqa: F841
            raise ValueError("data must be a valid JSON array")
        if not isinstance(parsed, list) or not parsed:
            raise ValueError("data payload must be a non-empty array")
        request = DepRepRequestInfo.from_payload(
            parsed,
            username=username,
            userid=userid,
            hospital_code=hospital_code,
            nexus_url=extra.get("nexus_url"),
        )
        request.req_id = req_id
        request.username = username
        request.userid = userid
        request.hospital_code = hospital_code
        request.do_deploy = do_deploy
        request.only_download = False
        request.not_record_download_progress = False
        request.not_record_replace_info = False
        request.dep_event_id = request.dep_event_id or uuid.uuid4().hex
        request.send_file_to_omnis_server = True
        autocheck = str(extra.get("autocheck", "")).lower() == "true"
        autorestart = str(extra.get("autorestartjboss", "")).lower() == "true"
        request.auto_check_war = autocheck
        request.auto_restart_after_deploy = autorestart
        return request

    def _handle_deploy_flow(self, request: DepRepRequestInfo) -> Dict[str, Any]:
        assert self.deploy_process and self.deploy_invoker
        task_ids = [item.dep_task_id for item in request.dep_rep_data]
        self.deploy_process.record_task_status(
            username=request.username or "-",
            op_type="[DEPLOY]",
            message="请求已接受，正在整理数据",
            task_ids=task_ids,
        )
        try:
            response = self.integration_invoker.request_invoke_sync(request)
        except Exception as exc:  # noqa: BLE001
            self.deploy_process.record_task_status(
                username=request.username or "-",
                op_type="[DEPLOY]",
                message=f"部署前置步骤失败:{exc}",
                task_ids=task_ids,
            )
            return OperationResult(False, str(exc)).as_dict()

        self.nexus_transfer.send_files(response)
        self.deploy_process.record_task_status(
            username=request.username or "-",
            op_type="[DEPLOY]",
            message="替换完成，等待部署执行",
            task_ids=task_ids,
        )

        response_map = {resp.task_id: resp for resp in response.final_files if resp.task_id}
        try:
            self.deploy_process.enqueue_tasks(
                dep_event_id=request.dep_event_id,
                task_ids=task_ids,
                invoker=self.deploy_invoker,
                request_builder=lambda entry: self._build_deploy_request(
                    entry,
                    response_map,
                    request,
                ),
            )
            self.deploy_process.record_task_status(
                username=request.username or "-",
                op_type="[DEPLOY]",
                message="部署任务已入队，等待执行",
                task_ids=task_ids,
            )
        except Exception as exc:  # noqa: BLE001
            self.deploy_process.record_task_status(
                username=request.username or "-",
                op_type="[DEPLOY]",
                message=f"部署队列创建失败:{exc}",
                task_ids=task_ids,
            )
            return OperationResult(False, str(exc)).as_dict()

        return OperationResult(
            True,
            "queued",
            [self._serialize_replace_response(resp) for resp in response.final_files],
        ).as_dict()

    def show_checkwar_status(self, *, username: str, task_ids: List[str]) -> Dict[str, Any]:
        if not self.deploy_process:
            return OperationResult(False, "deploy process service unavailable").as_dict()
        try:
            statuses = self.deploy_process.show_checkwar_status(task_ids, username)
            return OperationResult(True, "ok", statuses).as_dict()
        except Exception as exc:  # noqa: BLE001
            return OperationResult(False, str(exc)).as_dict()

    def _build_deploy_request(
        self,
        entry: DeployTaskListEntry,
        response_map: Dict[str, FileReplaceOneResponse],
        request: DepRepRequestInfo,
    ) -> DeployRequest:
        response = response_map.get(entry.dep_task_id)
        if not response:
            raise ValueError(f"Missing replace response for task {entry.dep_task_id}")

        deploy_file = response.file_path
        if not deploy_file:
            raise ValueError(f"Task {entry.dep_task_id} missing file path")

        normalized_type = self._normalize_deploy_type(entry.soft_type)
        server_port = self._resolve_cli_port(entry, normalized_type)
        server_os = entry.server_os or getattr(self.settings, "deploy_default_server_os", "")
        if not server_os:
            for candidate in (entry.deploydir, entry.singledep_bak_path):
                if candidate and ":" in candidate:
                    server_os = "windows"
                    break

        dep_server_info = DepServerInfo(
            server_ip=entry.server_ip,
            os_user_name=entry.os_user_name or "",
            os_user_pwd=entry.os_user_pwd or "",
            remote_connect_port=entry.remote_connect_port or "22",
            server_os=server_os or "",
            deploy_dir=entry.deploydir,
            soft_home_dir=entry.soft_home_dir,
            singledep_bak_path=entry.singledep_bak_path,
            service_port=entry.service_port,
            manage_port=entry.manage_port,
            portoffset=entry.portoffset,
            appurl=entry.appurl,
        )
        deploy_request = DeployRequest(
            ip=entry.server_ip,
            port=server_port,
            deploy_type=normalized_type,
            deploy_file_path=deploy_file,
            artifact_war_name=response.artifact_name or Path(deploy_file).name,
            war_version=response.war_version or "",
            username=request.username or "",
            task_id=entry.dep_task_id,
            dep_event_id=request.dep_event_id,
            dep_server_info=dep_server_info,
        )
        deploy_request.singledep_bak_path = entry.singledep_bak_path
        deploy_request.base_url = self.deploy_process.sys_params.deploy_local_base_url
        deploy_request.snapshot_war_long_version = response.replace_details.metadata.get("snapshot") if response.replace_details else None
        deploy_request.properties_some_key_value = response.replace_details.other_infos if response.replace_details else {}

        # Detect Windows hosts to let CLI executor choose the correct binary
        effective_os = (server_os or "").lower()
        if "windows" in effective_os:
            deploy_request.windows_trans_file_default_path = self.settings.__dict__.get("deploy_windows_tmp", "C:/tmp")

        return deploy_request

    def _resolve_cli_port(self, entry: DeployTaskListEntry, deploy_type: str) -> str:
        offset = 0
        try:
            offset = int(entry.portoffset or "0")
        except ValueError:
            offset = 0
        default_port = self.deploy_process.sys_params.jboss_cli_default_port
        soft_type = (deploy_type or "").lower()
        if "jboss7" in soft_type or soft_type.endswith("7"):
            default_port = self.deploy_process.sys_params.jboss7_cli_default_port
        return str(default_port + offset)

    def _normalize_deploy_type(self, soft_type: Optional[str]) -> str:
        dtype = (soft_type or "").lower()
        if dtype in ("2", "springboot", "spring_boot", "spring-boot"):
            return "springboot"
        if dtype in ("4", "jboss7", "jboss-7", "jboss7.x"):
            return "jboss7"
        if dtype in ("1", "zip", "zipfile", "zip-file"):
            return "zip"
        if dtype in ("6", "singlefile", "single-file"):
            return "singlefile"
        if dtype in ("0", "war", "jboss"):
            return "jboss"
        # fall back to original descriptor
        return dtype or "jboss"
