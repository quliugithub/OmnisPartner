"""Helper utilities for executing JBoss CLI deployments."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

from app.modules.deployfilemanage.domain import DeployRequest, DeployResultRecord
from app.modules.deployfilemanage.service.deploy_process import DepRepSysParams


class DeploymentBackupManager:
    """Handle backup/restore of deployed artifacts."""

    def __init__(self, backup_root: Optional[str]) -> None:
        self.backup_root = Path(backup_root) if backup_root else None
        self.log = logging.getLogger(self.__class__.__name__)

    def create_backup(self, request: DeployRequest) -> Optional[Path]:
        if not self.backup_root:
            return None
        source = Path(request.deploy_file_path)
        if not source.exists():
            return None
        dest_dir = self.backup_root / request.task_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / source.name
        shutil.copy2(source, dest)
        self.log.info("Created backup %s for %s", dest, request.task_id)
        return dest

    def restore_backup(self, backup_file: Path, target_path: Path) -> None:
        if not backup_file.exists():
            return
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_file, target_path)
        self.log.warning("Restored backup %s -> %s", backup_file, target_path)


StatusCallback = Optional[Callable[[str], None]]


class JbossCliExecutor:
    """Executes deployment commands via jboss-cli."""

    def __init__(self, sys_params: DepRepSysParams) -> None:
        self.sys_params = sys_params
        self.backup_manager = DeploymentBackupManager(sys_params.singlefile_dep_bak_path)
        self.log = logging.getLogger(self.__class__.__name__)

    def deploy(
        self,
        request: DeployRequest,
        *,
        status_callback: StatusCallback = None,
    ) -> DeployResultRecord:
        result = DeployResultRecord()
        result.task_id = request.task_id
        result.deploy_id = request.dep_event_id
        result.username = request.username
        result.war_artifact_id = request.artifact_war_name
        result.war_version = request.war_version

        operation = "卸载" if request.is_undeploy else "部署"
        artifact_name = self._artifact_name(request)
        operation_log = "undeploy" if request.is_undeploy else "deploy"

        if not request.is_undeploy:
            # Mirror Java flow: undeploy first, ignore failures
            self._preclean_existing_deployment(
                request,
                artifact_name=artifact_name,
                status_callback=status_callback,
            )

        self._notify_progress(
            request,
            status_callback,
            self._build_progress_message(request),
        )
        self.log.info(
            "Starting %s task=%s user=%s artifact=%s target=%s:%s deployId=%s",
            operation_log,
            request.task_id,
            request.username,
            artifact_name,
            request.ip,
            request.port,
            request.dep_event_id,
        )

        start = time.perf_counter()
        backup_file = None
        cli_temp_dir: Optional[Path] = None
        cli_script: Optional[Path] = None
        try:
            backup_file = self.backup_manager.create_backup(request)
            result.prepare_time_secs = time.perf_counter() - start

            command, cli_script, cli_cwd, cli_temp_dir = self._build_cli_command(request)
            run_start = time.perf_counter()
            cli_timeout = (
                self.sys_params.deploy_timeout
                if self.sys_params.deploy_timeout and self.sys_params.deploy_timeout > 0
                else None
            )
            timeout_hint = f"{cli_timeout}s" if cli_timeout else "无超时限制"
            self._notify_progress(
                request,
                status_callback,
                f"正在执行 JBoss CLI 命令(超时 {timeout_hint})...",
            )
            output = self._run_cli(command, cli_cwd, timeout=cli_timeout)
            status_ok = self._interpret_cli_output(output, request)
            if not status_ok:
                # 若 CLI 输出未明确 OK，再做一次状态轮询校验
                self._poll_deployment_status(request, status_callback=status_callback)
            result.deploy_time_secs = time.perf_counter() - run_start
            success_msg = self._build_success_message(request)
            result.mark_success(success_msg)
            self._notify_progress(request, status_callback, success_msg)
            self.log.info(
                "%s succeeded task=%s artifact=%s deployId=%s duration=%.2fs",
                operation_log,
                request.task_id,
                artifact_name,
                request.dep_event_id,
                result.deploy_time_secs,
            )
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            result.mark_failure(error_message)
            self._notify_progress(request, status_callback, error_message)
            self.log.exception(
                "%s failed task=%s artifact=%s deployId=%s",
                operation_log,
                request.task_id,
                artifact_name,
                request.dep_event_id,
            )
            if backup_file:
                self.backup_manager.restore_backup(
                    backup_file,
                    Path(request.deploy_file_path),
                )
        finally:
            if cli_script and cli_script.exists():
                cli_script.unlink(missing_ok=True)
            if cli_temp_dir:
                shutil.rmtree(cli_temp_dir, ignore_errors=True)
            total = time.perf_counter() - start
            result.down_rep_time_secs = total
        return result

    def _build_cli_command(self, request: DeployRequest) -> Tuple[List[str], Path, Path, Path]:
        is_windows = os.name == "nt"
        cli_bin = self._resolve_cli_bin(request, is_windows)
        cli_cwd = cli_bin.parent
        artifact = self._artifact_name(request)
        cli_temp_dir = Path(tempfile.mkdtemp(prefix="jboss-cli-"))
        cli_script = cli_temp_dir / f"{request.task_id}.cli"
        if request.is_undeploy:
            cli_script.write_text(f"undeploy {artifact}\n", encoding="utf-8")
        else:
            commands = [
                f'deploy --force "{request.deploy_file_path}" --name={artifact}',
                f"deployment-info --name={artifact}",
            ]
            cli_script.write_text("\n".join(commands) + "\n", encoding="utf-8")
        soft_type = (request.deploy_type or "").lower()
        is_jboss7 = "jboss7" in soft_type
        port = request.port or (
            str(self.sys_params.jboss7_cli_default_port)
            if is_jboss7
            else str(self.sys_params.jboss_cli_default_port)
        )
        if is_jboss7:
            controller = f"remote+http://{request.ip}:{port}"
            timeout = 45000
        else:
            controller = f"{request.ip}:{port}"
            timeout = 30000

        cli_args = [
            "--connect",
            f"--controller={controller}",
            f"--user={self.sys_params.jboss_admin or ''}",
            f"--password={self.sys_params.jboss_admin_pwd or ''}",
            f"--file={cli_script}",
            f"--timeout={timeout}",
        ]
        if is_windows:
            command = ["cmd", "/c", str(cli_bin)] + cli_args
        else:
            command = [str(cli_bin)] + cli_args
        return command, cli_script, cli_cwd, cli_temp_dir

    def _write_cli_script(self, commands: Iterable[str]) -> Path:
        cli_temp_dir = Path(tempfile.mkdtemp(prefix="jboss-cli-"))
        cli_script = cli_temp_dir / "query.cli"
        cli_script.write_text("\n".join(commands) + "\n", encoding="utf-8")
        return cli_script

    def _resolve_cli_bin(self, request: DeployRequest, is_windows: bool) -> Path:
        suffix = ".bat" if is_windows else ".sh"
        soft_type = (request.deploy_type or "").lower()
        if is_windows:
            home = self.sys_params.jboss_cli_home_win
            if "jboss7" in soft_type and self.sys_params.jboss7_cli_home_win:
                home = self.sys_params.jboss7_cli_home_win
        else:
            home = self.sys_params.jboss_cli_home
            if "jboss7" in soft_type and self.sys_params.jboss7_cli_home:
                home = self.sys_params.jboss7_cli_home
        if not home:
            raise FileNotFoundError("JBoss CLI home path is not configured")
        home_path = Path(home)
        candidates = [
            home_path / "src" / "main" / "bin" / f"jboss-cli{suffix}",  # source layout
            home_path / "bin" / f"jboss-cli{suffix}",  # standard install
            home_path / f"jboss-cli{suffix}",  # direct path
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise FileNotFoundError(f"JBoss CLI not found under {home}")

    def _build_cli_command_from_script(self, script: Path, request: DeployRequest) -> Tuple[List[str], Path]:
        is_windows = os.name == "nt"
        cli_bin = self._resolve_cli_bin(request, is_windows)
        cli_cwd = cli_bin.parent
        soft_type = (request.deploy_type or "").lower()
        is_jboss7 = "jboss7" in soft_type
        port = request.port or (
            str(self.sys_params.jboss7_cli_default_port)
            if is_jboss7
            else str(self.sys_params.jboss_cli_default_port)
        )
        if is_jboss7:
            controller = f"remote+http://{request.ip}:{port}"
            timeout = 45000
        else:
            controller = f"{request.ip}:{port}"
            timeout = 30000
        cli_args = [
            "--connect",
            f"--controller={controller}",
            f"--user={self.sys_params.jboss_admin or ''}",
            f"--password={self.sys_params.jboss_admin_pwd or ''}",
            f"--file={script}",
            f"--timeout={timeout}",
        ]
        if is_windows:
            return ["cmd", "/c", str(cli_bin)] + cli_args, cli_cwd
        return [str(cli_bin)] + cli_args, cli_cwd

    def _run_cli(self, command: List[str], cwd: Path, *, timeout: Optional[int] = None) -> str:
        proc_timeout = timeout if timeout and timeout > 0 else None
        timeout_desc = f"{proc_timeout}s" if proc_timeout else "无限制"
        self.log.info("Executing JBoss CLI cmd=%s cwd=%s timeout=%s", command, cwd, timeout_desc)
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                cwd=str(cwd),
                timeout=proc_timeout,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            self.log.error("JBoss CLI command timeout after %ss cmd=%s", proc_timeout, command)
            raise RuntimeError("执行 JBoss CLI 命令超时，请检查目标服务器状态") from exc
        if completed.stdout:
            self.log.info("CLI stdout: %s", completed.stdout.strip())
            if "JAVA_HOME is not set" in completed.stdout:
                self.log.warning("JBoss CLI warns: JAVA_HOME is not set")
        if completed.stderr:
            self.log.warning("CLI stderr: %s", completed.stderr.strip())
        completed.check_returncode()
        return completed.stdout or ""

    def _interpret_cli_output(self, output: str, request: DeployRequest) -> bool:
        text = (output or "").lower()
        if not text:
            return True
        if "outofmemoryerror" in text or "permgen" in text:
            raise RuntimeError("部署出现错误，Jboss 内存溢出，需重启后再试")
        if "doesn't exist" in text or "not found" in text:
            raise RuntimeError("部署错误，待部署资源不存在，可尝试重新部署")
        if "duplicate" in text and "resource" in text:
            raise RuntimeError(f"部署错误，重复的部署资源[{request.artifact_war_name}]，请尝试重新部署")
        if all(keyword in text for keyword in ("persistent", "enabled", "status")):
            if "status" in text and "ok" in text:
                return True
            if "stopped" in text:
                raise RuntimeError("部署完成，但应用处于 STOPPED 状态，可在 JBoss 控制台启用包")
        if "failure" in text or "error" in text:
            raise RuntimeError(output.strip())
        # 未匹配到明确成功，交给后续轮询确认
        return False

    def _poll_deployment_status(
        self,
        request: DeployRequest,
        *,
        status_callback: StatusCallback = None,
    ) -> None:
        commands = [
            f"deployment-info --name={self._artifact_name(request)}",
            ":read-attribute(name=server-state)",
        ]
        script = self._write_cli_script(commands)
        temp_dir = script.parent
        try:
            command, cli_cwd = self._build_cli_command_from_script(script, request)
            for idx in range(10):
                self._notify_progress(
                    request,
                    status_callback,
                    f"正在查询部署状态({idx + 1}/10)...",
                )
                output = self._run_cli(command, cli_cwd, timeout=30)
                lowered = output.lower()
                if ("status=ok" in lowered) or ("server-state" in lowered and "running" in lowered):
                    self._notify_progress(
                        request,
                        status_callback,
                        "部署状态为 OK",
                    )
                    return
                if "jbas014807" in lowered or "not found" in lowered:
                    raise RuntimeError("部署错误，未知原因导致未正常部署，可以尝试重启Jboss再部署！")
                if any(keyword in lowered for keyword in ("failure", "error", "stopped")):
                    self._notify_progress(
                        request,
                        status_callback,
                        "部署完成，但状态异常，正在分析日志",
                    )
                    raise RuntimeError(f"部署完成，但状态异常: {output}")
                if "server-state" in lowered and any(t in lowered for t in ("starting", "reload-required", "restart-required")):
                    raise RuntimeError(f"部署完成，但服务器状态异常: {output}")
                time.sleep(1.5)
            raise RuntimeError("部署状态查询超时")
        finally:
            script.unlink(missing_ok=True)
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _notify_progress(
        self,
        request: DeployRequest,
        callback: StatusCallback,
        message: Optional[str],
    ) -> None:
        if not callback or not message:
            return
        try:
            callback(message)
        except Exception as exc:  # noqa: BLE001
            self.log.warning(
                "Status callback failed task=%s deployId=%s: %s",
                request.task_id,
                request.dep_event_id,
                exc,
            )

    def _preclean_existing_deployment(
        self,
        request: DeployRequest,
        *,
        artifact_name: Optional[str] = None,
        status_callback: StatusCallback = None,
    ) -> None:
        name = artifact_name or self._artifact_name(request)
        script = self._write_cli_script([f"undeploy {name}"])
        temp_dir = script.parent
        try:
            command, cli_cwd = self._build_cli_command_from_script(script, request)
            self._notify_progress(request, status_callback, f"正在卸载历史部署[{name}]...")
            self._run_cli(command, cli_cwd, timeout=60)
            self._notify_progress(request, status_callback, f"历史部署[{name}]已卸载")
        except subprocess.CalledProcessError as exc:
            self.log.info("No existing deployment removed for %s: %s", name, exc)
        except Exception as exc:  # noqa: BLE001
            self.log.warning("Preclean deployment %s failed: %s", name, exc)
        finally:
            script.unlink(missing_ok=True)
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _artifact_name(self, request: DeployRequest) -> str:
        artifact = request.artifact_war_name or Path(request.deploy_file_path).name
        if not str(artifact).lower().endswith('.war'):
            return f"{artifact}.war"
        return artifact

    def _build_progress_message(self, request: DeployRequest) -> str:
        timestamp = time.strftime("%H:%M:%S")
        timeout = self.sys_params.deploy_timeout
        action = "卸载" if request.is_undeploy else "部署"
        hint = "一般需要用时1-3分钟" if not request.is_undeploy else "一般用时小于20秒"
        return f"正在{action}({timestamp},{timeout}s timeout)...{hint}"

    def _build_success_message(self, request: DeployRequest) -> str:
        if request.is_undeploy:
            return "卸载成功"
        if request.snapshot_war_long_version:
            return (
                f"成功[{request.war_version}]--->nexus快照精准版本[{request.snapshot_war_long_version}]"
                "(与nexus仓库比对核对当前部署快照版本是否为最新构建)"
            )
        if request.war_version:
            return f"成功[{request.war_version}]"
        return "部署成功"


