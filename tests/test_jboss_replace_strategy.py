import shutil
from pathlib import Path

from app.modules.deployfilemanage.domain import (
    DepOnceGlobalInfos,
    FileGetResponse,
    GetAndReplaceRequest,
    NexusIndex,
    ReplaceStrategyRequest,
)
from app.modules.deployfilemanage.filereplace.base_strategy import AbsReplaceStrategy


def build_request(tmp_path: Path) -> ReplaceStrategyRequest:
    source = tmp_path / "app.properties"
    source.write_text("key=value\n", encoding="utf-8")
    file_resp = FileGetResponse(success=True, file_path=source)
    globals_map = {"H001.cbh.omnis": set()}
    dep_globals = DepOnceGlobalInfos(global_task_map=globals_map)
    get_req = GetAndReplaceRequest(
        nexus_index=NexusIndex(artifact_id="demo", deploy_event_id="deploy123"),
        dep_once_global_infos=dep_globals,
    )
    return ReplaceStrategyRequest(
        file_get_response=file_resp,
        get_and_replace_request=get_req,
        only_download=False,
        record_replace_info=True,
        do_deploy=False,
    )


def test_abs_replace_strategy(tmp_path):
    replace_root = tmp_path / "replace"
    strategy = AbsReplaceStrategy(replace_root, properties_replacer=None)
    response = strategy.do_replace(build_request(tmp_path))
    assert response.final_files
    dest = Path(response.final_files[0].file_path)
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "key=value\n"
