"""Partial translation of DeployService focusing on sys params and task status."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Optional, Sequence, TYPE_CHECKING

from datetime import datetime

import httpx

from app.modules.deployfilemanage.domain import DeployTaskListEntry, DeployRequest
from app.modules.deployfilemanage.repositories import DepRepRepository

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.deployfilemanage.deploy import DeployInvokerService


@dataclass
class DepRepSysParams:
    """Container for deployment system parameters."""

    jboss_cli_home: Optional[str] = None
    jboss_cli_home_win: Optional[str] = None
    jboss7_cli_home: Optional[str] = None
    jboss7_cli_home_win: Optional[str] = None
    jboss_admin: Optional[str] = None
    jboss_admin_pwd: Optional[str] = None
    jboss_cli_default_port: int = 9999
    jboss7_cli_default_port: int = 9990
    deploy_timeout: int = 600
    encrypt_key: Optional[str] = None
    deploy_local_base_url: Optional[str] = None
    singlefile_dep_bak_path: Optional[str] = None

    def load_from_mapping(self, mapping: Dict[str, str]) -> None:
        def _int(value: Optional[str], default: int) -> int:
            if value is None:
                return default
            try:
                return int(value)
            except ValueError:
                return default

        self.jboss_cli_home = mapping.get("jboss_cli_home")
        self.jboss_cli_home_win = mapping.get("jboss_cli_home_win")
        self.jboss7_cli_home = mapping.get("jboss7_cli_home")
        self.jboss7_cli_home_win = mapping.get("jboss7_cli_home_win")
        self.jboss_admin = mapping.get("jboss_admin")
        self.jboss_admin_pwd = mapping.get("jboss_admin_pwd")
        self.jboss_cli_default_port = _int(mapping.get("jboss_admin_port"), self.jboss_cli_default_port)
        self.jboss7_cli_default_port = _int(mapping.get("jboss7_admin_port"), self.jboss7_cli_default_port)
        self.deploy_timeout = _int(mapping.get("deploy_timeout"), self.deploy_timeout)
        self.encrypt_key = mapping.get("encrypt_key")
        self.deploy_local_base_url = mapping.get("deploy_local_base_url")
        self.singlefile_dep_bak_path = mapping.get("singlefile_dep_bak_path")


class TaskStatusNotifier:
    """Helper that mirrors RecordTaskStatusEvent/RecordTaskListStatus."""

    def __init__(self, repository: DepRepRepository, logger: Optional[logging.Logger] = None) -> None:
        self.repository = repository
        self.log = logger or logging.getLogger(self.__class__.__name__)

    def notify(self, *, username: str, op_type: str, message: str, task_ids: Iterable[str]) -> int:
        task_list = [task for task in task_ids if task]
        if not task_list:
            return 0
        timestamp = datetime.now().strftime("%m-%d %H:%M")
        status_plain = f"{username}:{op_type}-{message}({timestamp})"
        color = self._color_for_message(status_plain)
        status_msg = f"<font color='{color}'>{status_plain}</font>"
        truncated_status = status_msg[:2000]
        truncated_comments = status_plain[:5800]
        effected = self.repository.update_task_status(task_list, truncated_status, truncated_comments)
        self.log.info(
            "Task status updated op=%s user=%s tasks=%s msg=%s",
            op_type,
            username,
            ",".join(task_list),
            message,
        )
        return effected

    def _color_for_message(self, message: str) -> str:
        text = message or ""
        if any(keyword in text for keyword in ("失败", "错误", "异常")):
            return "red"
        if "成功" in text:
            return "green"
        return "blue"


class DeployProcessService:
    """Subset of DeployService responsible for sys param loading and task status."""

    SYS_PARAM_KEYS = (
        "jboss_cli_home",
        "jboss_cli_home_win",
        "jboss7_cli_home",
        "jboss7_cli_home_win",
        "deploy_timeout",
        "jboss_admin",
        "jboss_admin_pwd",
        "jboss_admin_port",
        "encrypt_key",
        "deploy_local_base_url",
        "jboss7_admin_port",
        "singlefile_dep_bak_path",
    )

    def __init__(self, repository: DepRepRepository) -> None:
        self.repository = repository
        self.sys_params = DepRepSysParams()
        self.notifier = TaskStatusNotifier(repository)
        self._http_client = httpx.Client(timeout=5.0)

    def init_sys_params(self) -> DepRepSysParams:
        values = self.repository.get_sys_params(self.SYS_PARAM_KEYS)
        self.sys_params.load_from_mapping(values)
        logging.getLogger(self.__class__.__name__).info("Loaded deploy sys params %s", values.keys())
        return self.sys_params

    def record_task_status(self, *, username: str, op_type: str, message: str, task_ids: Iterable[str]) -> None:
        self.notifier.notify(username=username, op_type=op_type, message=message, task_ids=task_ids)

    def load_deploy_tasks(self, task_ids: Sequence[str]) -> Dict[str, DeployTaskListEntry]:
        return self.repository.get_deploy_tasks(task_ids)

    def enqueue_tasks(
        self,
        *,
        dep_event_id: str,
        task_ids: Sequence[str],
        invoker: "DeployInvokerService",
        request_builder: Callable[[DeployTaskListEntry], DeployRequest],
    ) -> None:
        tasks = self.load_deploy_tasks(task_ids)
        for entry in tasks.values():
            request = request_builder(entry)
            server_key = request.request_key()
            from app.modules.deployfilemanage.deploy import DeployTask  # local import to avoid cycles
            invoker.submit(
                DeployTask(
                    dep_event_id=dep_event_id,
                    task_id=entry.dep_task_id,
                    server_key=server_key,
                    request=request,
                )
            )

    def show_checkwar_status(self, task_ids: Sequence[str], username: str) -> Dict[str, str]:
        entries = self.load_deploy_tasks(task_ids)
        statuses: Dict[str, str] = {}
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        for entry in entries.values():
            url = self._build_check_url(entry)
            statuses[entry.dep_task_id] = f"{self._fetch_check_status(url)}({timestamp})"
        self.repository.update_task_checkwar_status(statuses)
        self.notifier.notify(
            username=username,
            op_type="[CHECKWAR]",
            message="已刷新 checkwar 状态",
            task_ids=task_ids,
        )
        return statuses

    def _build_check_url(self, entry: DeployTaskListEntry) -> str:
        if entry.appurl:
            base = entry.appurl.rsplit("/", 1)[0]
            return f"{base}/check"
        port = entry.service_port or entry.remote_connect_port or "8080"
        return f"http://{entry.server_ip}:{port}/check"

    def _fetch_check_status(self, url: str) -> str:
        try:
            response = self._http_client.get(url)
            response.raise_for_status()
            if "CheckSuccess" in response.text:
                return "OK"
            return "FAIL"
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(self.__class__.__name__).warning("checkwar %s failed: %s", url, exc)
            return "FAIL"
