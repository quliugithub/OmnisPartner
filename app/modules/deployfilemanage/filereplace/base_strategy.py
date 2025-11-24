"""Base classes for file replacement strategies."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set
from zipfile import ZipFile

from app.modules.deployfilemanage.domain import (
    DepFileGetReplaceResponse,
    DepOnceGlobalInfos,
    FileGetResponse,
    FileReplaceOneResponse,
    GetAndReplaceRequest,
    NexusIndex,
    ReplaceDetails,
    ReplaceStrategyRequest,
)
from app.modules.deployfilemanage.domain.constants import (
    SPRING_BOOT_MANAGER_PORT,
    SPRING_BOOT_SERVER_PORT,
)
from app.modules.deployfilemanage.filereplace import SimplePropertiesContentReplace


class ReplacementError(RuntimeError):
    """Raised when replacement prerequisites fail."""


class AbsReplaceStrategy:
    """Lightweight translation of the Java base strategy."""

    def __init__(
        self,
        replace_root: Path,
        properties_replacer: SimplePropertiesContentReplace | None = None,
        event_publisher: Optional[Callable[[List[ReplaceDetails]], None]] = None,
    ) -> None:
        self.replace_root = replace_root
        self.replace_root.mkdir(parents=True, exist_ok=True)
        self.properties_replacer = properties_replacer
        self.event_publisher = event_publisher
        self.log = logging.getLogger(self.__class__.__name__)

    def do_replace(self, request: ReplaceStrategyRequest) -> DepFileGetReplaceResponse:
        file_response = request.file_get_response
        if not file_response.success or not file_response.file_path:
            raise ReplacementError("original file not available")

        get_request = request.get_and_replace_request or GetAndReplaceRequest()
        nexus_index = get_request.nexus_index or NexusIndex(artifact_id="artifact", deploy_event_id="deploy")
        dep_globals = get_request.dep_once_global_infos or DepOnceGlobalInfos()

        artifact = nexus_index.artifact_id or "artifact"
        deploy_id = nexus_index.deploy_event_id or "deploy"
        self.log.info(
            "Start replacement artifact=%s deployId=%s globals=%s",
            artifact,
            deploy_id,
            list((dep_globals.global_task_map or {}).keys()),
        )

        if not dep_globals.global_task_map:
            dep_globals.global_task_map = {"GLOBAL_DEFAULT": set()}

        results: List[FileReplaceOneResponse] = []
        detail_events: List[ReplaceDetails] = []
        for global_name in dep_globals.global_task_map.keys():
            response, details = self._handle_single_global(
                global_name=global_name,
                artifact=artifact,
                deploy_id=deploy_id,
                request=request,
                source_path=file_response.file_path,
                dep_globals=dep_globals,
                nexus_index=nexus_index,
            )
            results.append(response)
            if details:
                detail_events.append(details)

        self.log.info(
            "Replacement finished artifact=%s deployId=%s outputs=%d",
            artifact,
            deploy_id,
            len(results),
        )
        self._publish_replace_events(detail_events, request.record_replace_info)
        return DepFileGetReplaceResponse(final_files=results)

    def _publish_replace_events(self, details: List[ReplaceDetails], should_publish: bool) -> None:
        if not should_publish or not self.event_publisher:
            return
        unique: List[ReplaceDetails] = []
        seen_ids: Set[int] = set()
        for detail in details:
            if not detail:
                continue
            marker = id(detail)
            if marker in seen_ids:
                continue
            seen_ids.add(marker)
            unique.append(detail)
        if unique:
            self.log.info("Publishing %d replacement detail events", len(unique))
            self.event_publisher(unique)

    def _handle_single_global(
        self,
        *,
        global_name: str,
        artifact: str,
        deploy_id: str,
        request: ReplaceStrategyRequest,
        source_path: Path,
        dep_globals: DepOnceGlobalInfos,
        nexus_index: NexusIndex,
    ) -> tuple[FileReplaceOneResponse, Optional[ReplaceDetails]]:
        if request.only_download:
            response = FileReplaceOneResponse(
                success=True,
                message="SKIP",
                file_path=str(source_path),
                global_name=global_name,
                deploy_id=deploy_id,
            )
            return response, None

        dest_dir = self.replace_root / deploy_id / artifact / global_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / source_path.name
        shutil.copyfile(source_path, dest_file)
        self.log.info("Copied artifact for global=%s deployId=%s -> %s", global_name, deploy_id, dest_file)

        replace_details: Optional[ReplaceDetails] = None
        global_id = (dep_globals.global_ids or {}).get(global_name)
        properties = (dep_globals.global_infos or {}).get(global_name)
        if dest_file.suffix.lower() in {".properties", ".conf"}:
            replace_details = self._process_properties_file(dest_file, global_name, properties)

        if dest_file.suffix.lower() in {".war", ".jar"}:
            exploded = self._extract_archive(dest_file)
            self.log.debug("Exploded archive %s -> %s", dest_file, exploded)
            replace_details = replace_details or ReplaceDetails()
            replace_details.metadata["exploded_path"] = str(exploded)
            for prop_file in exploded.rglob("*.properties"):
                details = self._process_properties_file(prop_file, global_name, properties)
                if details:
                    self._merge_details(replace_details, details)
            self.log.info("Processed exploded archive under %s", exploded)
            self._repack_archive(dest_file, exploded)

        if replace_details:
            replace_details.global_name = global_name
            replace_details.global_id = global_id
            replace_details.metadata.setdefault("file_path", str(dest_file))
            replace_details.metadata.setdefault("deploy_id", deploy_id)
            replace_details.nexus_index = nexus_index

        response = FileReplaceOneResponse(
            success=True,
            message="OK",
            file_path=str(dest_file),
            global_name=global_name,
            deploy_id=deploy_id,
            replace_details=replace_details,
            artifact_name=nexus_index.artifact_id,
            war_version=nexus_index.version,
        )
        self.log.debug(
            "Replacement complete for global=%s deployId=%s tasks=%d",
            global_name,
            deploy_id,
            len(dep_globals.global_task_map.get(global_name, set())),
        )
        return response, replace_details

    def _process_properties_file(
        self,
        file_path: Path,
        global_name: str,
        properties: Optional[Dict[str, str]],
    ) -> ReplaceDetails:
        if properties:
            return self._process_with_properties(file_path, properties)
        if not self.properties_replacer:
            return ReplaceDetails()
        original = file_path.read_text(encoding="utf-8", errors="ignore")
        replaced = self.properties_replacer.replace(original, global_name)
        file_path.write_text(replaced, encoding="utf-8")
        return self._build_replace_details(original, replaced)

    def _process_with_properties(self, file_path: Path, properties: Dict[str, str]) -> ReplaceDetails:
        details = ReplaceDetails()
        original_lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        output_lines: List[str] = []
        seen_keys: Set[str] = set()
        for raw_line in original_lines:
            line = raw_line
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                output_lines.append(line)
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            seen_keys.add(key)
            self._track_special_key(details, key, value)
            if key in properties:
                new_value = properties[key]
                if new_value == value:
                    details.add_untouched(key, value)
                else:
                    details.add_updated(key, value, new_value)
                self._track_special_key(details, key, new_value)
                output_lines.append(f"{key}={new_value}")
            else:
                details.add_untouched(key, value)
                output_lines.append(f"{key}={value}")
        for key, new_value in properties.items():
            if key in seen_keys:
                continue
            details.add_new(key, new_value)
            self._track_special_key(details, key, new_value)
            output_lines.append(f"{key}={new_value}")
        file_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
        self.log.debug("Processed properties file %s", file_path)
        return details

    def _build_replace_details(
        self,
        original: str,
        replaced: str,
        *,
        base_details: Optional[ReplaceDetails] = None,
    ) -> ReplaceDetails:
        details = base_details or ReplaceDetails()
        old_map = self._parse_properties(original)
        new_map = self._parse_properties(replaced)

        for key, value in new_map.items():
            if key not in old_map:
                details.add_new(key, value)
            elif old_map[key] != value:
                details.add_updated(key, old_map[key], value)
            else:
                details.add_untouched(key, value)

        for key, value in old_map.items():
            if key not in new_map:
                details.add_untouched(key, value)

        return details

    def _track_special_key(self, details: ReplaceDetails, key: str, value: str) -> None:
        if key in {SPRING_BOOT_MANAGER_PORT, SPRING_BOOT_SERVER_PORT}:
            details.add_other_info(key, value)

    def _parse_properties(self, text: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
        return result

    def _extract_archive(self, archive: Path) -> Path:
        exploded_dir = archive.with_suffix("") / "exploded"
        exploded_dir.mkdir(parents=True, exist_ok=True)
        self.log.debug("Extracting archive %s into %s", archive, exploded_dir)
        with ZipFile(archive, "r") as zf:
            zf.extractall(exploded_dir)
        self.log.info("Archive extracted %s -> %s", archive, exploded_dir)
        return exploded_dir

    def _repack_archive(self, archive: Path, exploded_dir: Path) -> None:
        """Replace the archive contents with the updated exploded directory."""
        tmp_archive = archive.with_suffix(".tmp")
        self.log.debug("Repacking archive %s from %s", archive, exploded_dir)
        with ZipFile(tmp_archive, "w") as zf:
            for item in exploded_dir.rglob("*"):
                if item.is_file():
                    zf.write(item, item.relative_to(exploded_dir))
        tmp_archive.replace(archive)
        shutil.rmtree(exploded_dir, ignore_errors=True)
        self.log.info("Repacked archive %s and removed %s", archive, exploded_dir)

    def _merge_details(self, target: ReplaceDetails, source: ReplaceDetails) -> None:
        target.updated_items.update(source.updated_items)
        target.new_items.update(source.new_items)
        target.untouched_items.update(source.untouched_items)
        target.spring_boot_items.update(source.spring_boot_items)
        target.metadata.update(source.metadata)
