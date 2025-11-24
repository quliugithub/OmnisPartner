"""Python port of GetRepDepIntegrationInvoker for limited scenarios."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.modules.deployfilemanage.domain import (
    ArtifactCoordinates,
    DepFileGetReplaceResponse,
    DepOnceGlobalInfos,
    DepRepRequestInfo,
    DepRepRequestInfoData,
    FileGetResponse,
    FileReplaceOneResponse,
    GetAndReplaceRequest,
    NexusIndex,
    ReplaceStrategyRequest,
)
from app.modules.deployfilemanage.fileget import NexusDownloader
from app.modules.deployfilemanage.filereplace import CbhJbossReplaceStrategy
from app.modules.deployfilemanage.repositories import DepRepRepository

log = logging.getLogger(__name__)


class GetRepDepIntegrationInvoker:
    """Minimal invoker that supports the Java `/onlydowloadnexusfile` flow."""

    def __init__(
        self,
        downloader: NexusDownloader,
        strategy: CbhJbossReplaceStrategy,
        repository: DepRepRepository,
    ) -> None:
        self.downloader = downloader
        self.strategy = strategy
        self.repository = repository

    def request_invoke_sync(self, request: DepRepRequestInfo) -> DepFileGetReplaceResponse:
        if not request.dep_rep_data:
            raise ValueError("depRepRequestInfoDataList cannot be empty")

        dep_event_id = request.dep_event_id or uuid.uuid4().hex
        request.dep_event_id = dep_event_id

        dep_globals, global_snapshots = self._build_global_context(request.dep_rep_data)
        grouped = self._group_by_coordinates(request.dep_rep_data)

        final_files: List[FileReplaceOneResponse] = []
        for (group_id, artifact_id, version, extension), items in grouped.items():
            coords = ArtifactCoordinates(
                groupid=group_id,
                artifactid=artifact_id,
                version=version,
                extension=extension,
            )
            target_path = self._resolve_download_path(request, items[0], coords)
            download_path = self._download_artifact(
                coords,
                request.nexus_url,
                target_path,
                force_download=items[0].snapshot,
                username=request.username,
                userid=request.userid,
            )
            nexus_index = self._build_nexus_index(request, items, download_path, coords)

            replace_request = ReplaceStrategyRequest(
                file_get_response=FileGetResponse(success=True, file_path=download_path),
                get_and_replace_request=GetAndReplaceRequest(
                    nexus_index=nexus_index,
                    dep_once_global_infos=dep_globals,
                ),
                only_download=False,
                record_replace_info=not request.not_record_replace_info,
                do_deploy=request.do_deploy,
            )

            strategy_response = self.strategy.do_replace(replace_request)
            task_map = self._build_local_task_map(items, global_snapshots)
            final_files.extend(
                self._expand_for_tasks(
                    strategy_response.final_files,
                    task_map,
                    dep_globals.global_ids or {},
                )
            )

        return DepFileGetReplaceResponse(final_files=final_files)

    def _download_artifact(
        self,
        coords: ArtifactCoordinates,
        override_url: Optional[str],
        target_path: Path,
        force_download: bool,
        *,
        username: Optional[str],
        userid: Optional[str],
    ) -> Path:
        if target_path.exists() and not force_download:
            log.info("Reuse cached artifact %s", target_path)
            return target_path
        return self.downloader.download(
            coords,
            override_url,
            dest_path=target_path,
            force=force_download,
            username=username,
            userid=userid,
        )

    def _group_by_coordinates(
        self,
        items: Sequence[DepRepRequestInfoData],
    ) -> Dict[Tuple[str, str, str, str], List[DepRepRequestInfoData]]:
        grouped: Dict[Tuple[str, str, str, str], List[DepRepRequestInfoData]] = defaultdict(list)
        for item in items:
            key = (item.nexus_group_id, item.nexus_artifact_id, item.version, item.extension)
            grouped[key].append(item)
        return grouped

    def _build_global_context(
        self,
        items: List[DepRepRequestInfoData],
    ) -> Tuple[DepOnceGlobalInfos, Dict[str, GlobalSnapshot]]:
        global_task_map: Dict[str, Set[str]] = defaultdict(set)
        global_infos: Dict[str, Dict[str, str]] = {}
        global_ids: Dict[str, str] = {}
        cache: Dict[str, GlobalSnapshot] = {}

        for item in items:
            snapshot = cache.get(item.global_group_id)
            if snapshot is None:
                name, details = self.repository.get_global_conf_group(item.global_group_id)
                snapshot = GlobalSnapshot(name=name, details=details)
                cache[item.global_group_id] = snapshot
            item.resolved_global_name = snapshot.name
            global_task_map[snapshot.name].add(item.dep_task_id)
            global_infos[snapshot.name] = snapshot.details
            global_ids[snapshot.name] = item.global_group_id

        dep_globals = DepOnceGlobalInfos(
            global_task_map={key: set(value) for key, value in global_task_map.items()},
            global_infos=global_infos,
            global_ids=global_ids,
        )
        return dep_globals, cache

    def _build_local_task_map(
        self,
        items: Iterable[DepRepRequestInfoData],
        snapshots: Dict[str, "GlobalSnapshot"],
    ) -> Dict[str, Set[str]]:
        local_map: Dict[str, Set[str]] = defaultdict(set)
        for item in items:
            snapshot = snapshots.get(item.global_group_id)
            if not snapshot:
                continue
            local_map[snapshot.name].add(item.dep_task_id)
        return local_map

    def _build_nexus_index(
        self,
        request: DepRepRequestInfo,
        items: Sequence[DepRepRequestInfoData],
        download_path: Path,
        coords: ArtifactCoordinates,
    ) -> NexusIndex:
        nexus_index = NexusIndex(
            artifact_id=coords.artifactid,
            deploy_event_id=request.dep_event_id,
        )
        nexus_index.group_id = coords.groupid
        nexus_index.version = coords.version
        nexus_index.extension = coords.extension
        nexus_index.current_user_id = request.userid
        nexus_index.current_user_name = request.username
        nexus_index.current_tasks = [item.dep_task_id for item in items]
        nexus_index.current_file_path = str(download_path)
        nexus_index.is_snapshot = items[0].snapshot
        return nexus_index

    def _expand_for_tasks(
        self,
        responses: List[FileReplaceOneResponse],
        task_map: Dict[str, Set[str]],
        global_ids: Dict[str, str],
    ) -> List[FileReplaceOneResponse]:
        expanded: List[FileReplaceOneResponse] = []
        for resp in responses:
            tasks = task_map.get(resp.global_name or "", set())
            global_id = global_ids.get(resp.global_name or "")
            if not tasks:
                expanded.append(resp)
                continue
            for task_id in tasks:
                clone = dc_replace(
                    resp,
                    task_id=task_id,
                    global_id=global_id,
                )
                expanded.append(clone)
        return expanded

    def _resolve_download_path(
        self,
        request: DepRepRequestInfo,
        sample_item: DepRepRequestInfoData,
        coords: ArtifactCoordinates,
    ) -> Path:
        base_dir = self.downloader.download_dir
        group_segments = [self._sanitize_segment(seg) for seg in coords.groupid.split(".")]
        version_segment = self._sanitize_segment(sample_item.version)
        user_segment = self._sanitize_segment(request.userid or "anonymous")
        parts = [*group_segments, coords.artifactid, version_segment, user_segment]
        if sample_item.snapshot:
            parts.append(request.dep_event_id)
        target_dir = base_dir.joinpath(*parts)
        filename = f"{coords.artifactid}-{coords.version}.{coords.extension}"
        return target_dir / filename

    def _sanitize_segment(self, value: str) -> str:
        return value.replace("/", "_").replace("\\", "_")


class GlobalSnapshot:
    def __init__(self, *, name: str, details: Dict[str, str]) -> None:
        self.name = name
        self.details = details
