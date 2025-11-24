
"""Spring Boot zip deployer aligned with the Java SpringBootZipDeploy flow."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Optional, Tuple

import httpx

from app.modules.deployfilemanage.domain import DeployRequest, DeployResultRecord
from app.modules.deployfilemanage.deploy.remote import RemoteAuth, RemoteExecutor
from app.modules.deployfilemanage.repositories import DepRepRepository
from app.modules.deployfilemanage.service.deploy_process import DepRepSysParams, TaskStatusNotifier


class SpringBootDeployer:
    """Implements stop -> upload/unzip -> start -> health/version checks."""

    def __init__(
        self,
        *,
        notifier: TaskStatusNotifier,
        repository: DepRepRepository,
        sys_params: DepRepSysParams,
    ) -> None:
        self.notifier = notifier
        self.repository = repository
        self.sys_params = sys_params
        self.log = logging.getLogger(self.__class__.__name__)
        self._http = httpx.Client(timeout=5.0, follow_redirects=True)

    def deploy(self, request: DeployRequest) -> DeployResultRecord:
        result = DeployResultRecord()
        result.task_id = request.task_id
        result.deploy_id = request.dep_event_id
        result.username = request.username
        result.war_artifact_id = request.artifact_war_name
        result.war_version = request.war_version

        try:
            deploy_dir = self._resolve_deploy_dir(request)
            if not deploy_dir:
                raise RuntimeError("???????")
            pkg = Path(request.deploy_file_path)
            if not pkg.exists():
                raise FileNotFoundError(f"??????? {pkg}")

            self._notify(request, "????...????????30?")
            self._add_version_marker(pkg, request.war_version)

            if request.is_win:
                msg_full = self._deploy_windows(deploy_dir, request, pkg)
            else:
                msg_full = self._deploy_linux(deploy_dir, request, pkg)

            result.msg_full = msg_full or "????"
            result.mark_success(result.msg_full)
            self._notify(request, self._final_status_message(request, True, result.msg_full))
        except Exception as exc:  # noqa: BLE001
            result.mark_failure(str(exc))
            self._notify(request, self._final_status_message(request, False, str(exc)))
            self.log.exception("SpringBoot deploy failed task=%s", request.task_id)
        return result

    def _deploy_linux(self, deploy_dir: str, request: DeployRequest, pkg: Path) -> str:
        dep_info = request.dep_server_info
        if not dep_info or not dep_info.os_user_name or not dep_info.os_user_pwd:
            raise RuntimeError("?????????????")

        auth = RemoteAuth(
            host=dep_info.server_ip,
            username=dep_info.os_user_name,
            password=dep_info.os_user_pwd,
            port=int(dep_info.remote_connect_port or 22),
        )
        artifact_name = self._artifact_zip_name(request)

        with RemoteExecutor(auth) as remote:
            try:
                remote.run(f"mkdir -p {deploy_dir}")
            except Exception:
                self.log.debug("?????????%s", deploy_dir)

            self._remote_backup(remote, deploy_dir, artifact_name, request)
            try:
                remote.run(f"cd {deploy_dir} && mv ./{artifact_name} ./{artifact_name}.bak")
            except Exception:
                self.log.debug("???????????? %s", artifact_name)

            self._notify(request, "????????...??????10?")
            remote_file = remote.upload(pkg, deploy_dir, remote_name=artifact_name)

            self._notify(request, "????????????...")
            self._before_deploy_linux(remote, deploy_dir, request)
            self._unzip_remote(remote, deploy_dir, remote_file, request)
            self._after_unzip_linux(remote, deploy_dir, request)
            return self._after_deploy_linux(remote, deploy_dir, request)

    def _before_deploy_linux(self, remote: RemoteExecutor, deploy_dir: str, request: DeployRequest) -> None:
        manager_port = self._resolve_manager_port(request)
        try:
            version_output = remote.run("java -version")
            if version_output and any(v in version_output for v in ("1.5.0", "1.6.0", "1.7.0")):
                raise RuntimeError("JDK???????????JDK1.8????")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(str(exc)) from exc

        try:
            if "omnis-partner" in (request.artifact_war_name or ""):
                self.log.info("?????? restart.sh")
                remote.run(f"cd {deploy_dir} && nohup sh ./restart.sh")
            else:
                remote.run(f"cd {deploy_dir} && nohup sh ./shutdown.sh {manager_port}".strip())
                time.sleep(5)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"??????: {exc}") from exc

    def _unzip_remote(self, remote: RemoteExecutor, deploy_dir: str, remote_file: str, request: DeployRequest) -> None:
        self._notify(request, "???????...")
        try:
            remote.run(f"cd {deploy_dir} && cd lib && rm -f *.jar || true")
        except Exception:
            self.log.debug("??lib???????")

        if getattr(self.sys_params, "use_agent_unzip", False):
            try:
                remote.run(f"omnis-agent unzip {remote_file} {deploy_dir}")
                return
            except Exception as exc:  # noqa: BLE001
                self.log.warning("agent ??????? unzip: %s", exc)

        output = remote.run(f"unzip -oq {remote_file} -d {deploy_dir}")
        lowered = (output or "").lower()
        if "cannot find or open" in lowered:
            raise RuntimeError(f"???????????? {remote_file}")
        if "permission" in lowered:
            raise RuntimeError(f"???????????????? {deploy_dir}")
        if "bad zip file" in lowered:
            raise RuntimeError("??????????")

    def _after_unzip_linux(self, remote: RemoteExecutor, deploy_dir: str, request: DeployRequest) -> None:
        text = self.repository.get_spingboot_env_conf_text(request.task_id)
        if not text:
            return
        tmp_dir = Path(tempfile.mkdtemp(prefix="envconf-"))
        try:
            tmp_file = tmp_dir / "env.conf"
            tmp_file.write_text(text, encoding="utf-8")
            try:
                remote.run(f"cd {deploy_dir} && mv ./conf/env.conf ./conf/env.conf.bak")
            except Exception:
                self.log.debug("???? env.conf ???????")
            remote.upload(tmp_file, deploy_dir + ("" if deploy_dir.endswith("/") else "/") + "conf")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _after_deploy_linux(self, remote: RemoteExecutor, deploy_dir: str, request: DeployRequest) -> str:
        manager_port = self._resolve_manager_port(request)
        try:
            remote.run(f"cd {deploy_dir} && nohup sh ./startup.sh {manager_port}".strip())
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"??????: {exc}") from exc

        port, ok = self._check_spring_boot_running(request)
        request.spring_boot_server_port = port
        version, url = self._update_online_version(request)
        self._record_app_status(request, ok or bool(version), url, version)
        if ok or version:
            return "????"
        return "????"

    def _deploy_windows(self, deploy_dir: str, request: DeployRequest, pkg: Path) -> str:
        target_dir = Path(deploy_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        self._notify(request, "????????...??????10?")
        self._before_deploy_local(target_dir, request)
        self._unzip_local(target_dir, pkg, request)
        self._after_unzip_local(target_dir, request)
        msg = self._after_deploy_local(target_dir, request)
        return msg

    def _before_deploy_local(self, deploy_dir: Path, request: DeployRequest) -> None:
        manager_port = self._resolve_manager_port(request)
        shutdown_cmds = [
            ["cmd", "/c", "restart.bat"],
            ["cmd", "/c", "shutdown.cmd", manager_port] if manager_port else ["cmd", "/c", "shutdown.cmd"],
        ]
        for cmd in shutdown_cmds:
            script_path = deploy_dir / cmd[-1]
            if not script_path.exists():
                continue
            self._notify(request, "????????????...")
            subprocess.run(cmd, cwd=str(deploy_dir), check=False)
            time.sleep(1)
            break

    def _unzip_local(self, deploy_dir: Path, pkg: Path, request: DeployRequest) -> None:
        self._notify(request, "???????...")
        lib_dir = deploy_dir / "lib"
        if lib_dir.exists():
            for jar in lib_dir.glob("*.jar"):
                try:
                    jar.unlink()
                except Exception:
                    self.log.debug("??? jar ?? %s", jar)
        shutil.unpack_archive(str(pkg), str(deploy_dir))

    def _after_unzip_local(self, deploy_dir: Path, request: DeployRequest) -> None:
        text = self.repository.get_spingboot_env_conf_text(request.task_id)
        if not text:
            return
        conf_dir = deploy_dir / "conf"
        conf_dir.mkdir(parents=True, exist_ok=True)
        dest = conf_dir / "env.conf"
        bak = conf_dir / "env.conf.bak"
        if dest.exists():
            try:
                dest.replace(bak)
            except Exception:
                self.log.debug("???? env.conf ??")
        dest.write_text(text, encoding="utf-8")

    def _after_deploy_local(self, deploy_dir: Path, request: DeployRequest) -> str:
        manager_port = self._resolve_manager_port(request)
        start_cmds = [
            ["cmd", "/c", "startup.cmd", manager_port] if manager_port else ["cmd", "/c", "startup.cmd"],
            ["cmd", "/c", "restart.cmd"],
        ]
        for cmd in start_cmds:
            script = deploy_dir / cmd[-1]
            if not script.exists():
                continue
            subprocess.run(cmd, cwd=str(deploy_dir), check=False)
            break
        port, ok = self._check_spring_boot_running(request)
        request.spring_boot_server_port = port
        version, url = self._update_online_version(request)
        self._record_app_status(request, ok or bool(version), url, version)
        if ok or version:
            return "????"
        return "????"

    def _notify(self, request: DeployRequest, message: Optional[str]) -> None:
        if not message or not self.notifier:
            return
        try:
            self.notifier.notify(
                username=request.username or "-",
                op_type=self._operation_label(),
                message=message,
                task_ids=[request.task_id],
            )
        except Exception as exc:  # noqa: BLE001
            self.log.warning("Notify failed for task=%s: %s", request.task_id, exc)

    def _operation_label(self) -> str:
        return "[SpringBoot??]"

    def _resolve_deploy_dir(self, request: DeployRequest) -> Optional[str]:
        dep_info = request.dep_server_info
        if not dep_info:
            return None
        deploy_dir = (
            getattr(dep_info, "deploy_dir", None)
            or getattr(dep_info, "deploydir", None)
            or getattr(dep_info, "soft_home_dir", None)
        )
        if not deploy_dir:
            return None
        return str(deploy_dir).rstrip(r"/\\")

    def _artifact_zip_name(self, request: DeployRequest) -> str:
        name = request.artifact_war_name or Path(request.deploy_file_path).name
        lower = name.lower()
        if lower.endswith(".war"):
            name = name[:-4]
        if not name.lower().endswith(".zip"):
            name = f"{name}.zip"
        return name

    def _add_version_marker(self, zip_path: Path, version: Optional[str]) -> None:
        if not version or not zip_path.exists():
            return
        content = "##omnis-partner-auto-add\n" + version + "\n##omnis-partner-auto-add-end\n"
        try:
            with zipfile.ZipFile(zip_path, "a") as zf:
                zf.writestr("version-deploy-add.txt", content)
        except Exception as exc:  # noqa: BLE001
            self.log.warning("????????: %s", exc)
        try:
            with zipfile.ZipFile(zip_path, "a") as zf:
                zf.writestr("version-deploy-add.txt", content)
        except Exception as exc:  # noqa: BLE001
            self.log.warning("????????: %s", exc)

    def _resolve_manager_port(self, request: DeployRequest) -> str:
        props = request.properties_some_key_value or {}
        conf_port = props.get("management.server.port") or ""
        db_port = self.repository.get_soft_manager_port(request.task_id) or ""
        return db_port or conf_port or ""

    def _resolve_server_port(self, request: DeployRequest) -> Optional[str]:
        props = request.properties_some_key_value or {}
        conf_port = props.get("server.port")
        db_port = self.repository.get_task_springboot_server_port(request.task_id)
        service_port = self.repository.get_service_port(request.task_id)
        dep_port = getattr(request.dep_server_info, "service_port", None) if request.dep_server_info else None
        port = conf_port or db_port or dep_port
        if service_port:
            port = service_port
        return port

    def _check_spring_boot_running(self, request: DeployRequest) -> Tuple[Optional[str], bool]:
        server_port = self._resolve_server_port(request)
        if not server_port:
            return None, False
        attempt = 0
        while attempt < 10:
            hint = f"????SpringBoot??...??????10?????????????????({attempt + 1}/10)"
            self._notify(request, hint)
            body = self._do_http_get(f"http://{request.ip}:{server_port}")
            if body is not None and "[ERROR]" not in body:
                self.log.info("spring boot running check ok: %s", body[:120])
                return server_port, True
            attempt += 1
            time.sleep(1)
        self._notify(request, "??????")
        return server_port, False

    def _update_online_version(self, request: DeployRequest) -> Tuple[Optional[str], Optional[str]]:
        try:
            time.sleep(10)
        except Exception:
            pass

        appurl = self.repository.get_task_appurl(request.task_id) or ""
        manager_port = self._resolve_manager_port(request)
        server_port = self._resolve_server_port(request) or request.spring_boot_server_port
        urls = []
        if appurl:
            url = appurl if appurl.endswith("info") else appurl.rstrip("/") + "/info"
            urls.append(url)
        if request.spring_boot_server_port:
            urls.extend(
                [
                    f"http://{request.ip}:{request.spring_boot_server_port}/actuator/info",
                    f"http://{request.ip}:{request.spring_boot_server_port}/info",
                ]
            )
        if server_port:
            urls.extend(
                [
                    f"http://{request.ip}:{server_port}/actuator/info",
                    f"http://{request.ip}:{server_port}/info",
                ]
            )
        if manager_port:
            urls.extend(
                [
                    f"http://{request.ip}:{manager_port}/actuator/info",
                    f"http://{request.ip}:{manager_port}/info",
                ]
            )

        for url in urls:
            content = self._do_http_get(url)
            version = self._try_get_version(content)
            if version:
                self.repository.update_task_list_online_version(request.task_id, version)
                self.repository.update_task_list_app_url(request.task_id, url)
                return version, url
        return None, None

    def _record_app_status(self, request: DeployRequest, ok: bool, appurl: Optional[str], version: Optional[str]) -> None:
        appstatu = "200" if ok else "404"
        try:
            if version:
                self.repository.update_task_list_by_task(request.task_id, appstatu, appurl or "", version, None)
            else:
                self.repository.update_task_list_nover_by_task(request.task_id, appstatu, appurl or "")
        except Exception as exc:  # noqa: BLE001
            self.log.warning("????????: %s", exc)

    def _remote_backup(self, remote: RemoteExecutor, deploy_dir: str, artifact_name: str, request: DeployRequest) -> None:
        """Lightweight backup similar to Java????????????????"""
        try:
            bak_name = f"{artifact_name}-current.zip"
            cmd = f"cd {deploy_dir} && zip -rq {bak_name} ./* -x ./*.zip"
            self.log.info("??????: %s", cmd)
            remote.run(cmd)
        except Exception as exc:  # noqa: BLE001
            self.log.warning("???????????: %s", exc)

    def _do_http_get(self, url: str) -> Optional[str]:
        try:
            resp = self._http.get(url)
            if resp.status_code >= 400:
                return None
            return resp.text
        except Exception as exc:  # noqa: BLE001
            self.log.debug("GET %s failed: %s", url, exc)
            return None

    def _try_get_version(self, content: Optional[str]) -> Optional[str]:
        if not content or "[ERROR]" in content:
            return None
        try:
            doc = json.loads(content)
            if isinstance(doc, dict):
                if isinstance(doc.get("app"), dict) and "version" in doc["app"]:
                    return str(doc["app"]["version"])
                if isinstance(doc.get("build"), dict) and "version" in doc["build"]:
                    return str(doc["build"]["version"])
        except Exception:
            return None
        return None

    def _final_status_message(self, request: DeployRequest, success: bool, detail: Optional[str]) -> str:
        base = "??" if success else "??"
        if detail:
            base = f"{base}({detail})"
        if request.dep_server_info and request.dep_server_info.os_user_name:
            base = f"{base}({request.dep_server_info.os_user_name})"
        return base
