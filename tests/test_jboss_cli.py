import os
import subprocess
from pathlib import Path

from app.modules.deployfilemanage.deploy import JbossCliExecutor
from app.modules.deployfilemanage.domain import DepServerInfo, DeployRequest
from app.modules.deployfilemanage.service.deploy_process import DepRepSysParams


def _build_request(tmp_path: Path) -> DeployRequest:
    artifact = tmp_path / "demo.war"
    artifact.write_text("demo")
    return DeployRequest(
        ip="127.0.0.1",
        port="9999",
        deploy_type="JBOSS",
        deploy_file_path=str(artifact),
        artifact_war_name="demo.war",
        war_version="1.0.0",
        username="tester",
        task_id="TASK-1",
        dep_event_id="EV-1",
        dep_server_info=DepServerInfo(server_ip="127.0.0.1", server_os="linux"),
    )


def _prepare_cli_home(tmp_path: Path) -> str:
    suffix = ".bat" if os.name == "nt" else ".sh"
    cli_bin = tmp_path / f"jboss-cli{suffix}"
    cli_bin.write_text("echo cli")
    return str(tmp_path)


def test_cli_executor_runs_and_creates_backup(tmp_path, monkeypatch):
    sys_params = DepRepSysParams()
    cli_home = _prepare_cli_home(tmp_path)
    sys_params.jboss_cli_home = cli_home
    sys_params.jboss_cli_home_win = cli_home
    backup_dir = tmp_path / "backup"
    sys_params.singlefile_dep_bak_path = str(backup_dir)

    executor = JbossCliExecutor(sys_params)
    request = _build_request(tmp_path)
    monkeypatch.setattr(JbossCliExecutor, "_preclean_existing_deployment", lambda *_, **__: None)

    calls = []

    def fake_run(cmd, *_, **__):
        calls.append(cmd)

        class Result:
            stdout = "status=ok"
            stderr = ""

            def check_returncode(self) -> None:
                return None

        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = executor.deploy(request)

    assert result.success
    assert calls, "CLI command should be invoked"
    backup_file = backup_dir / request.task_id / Path(request.deploy_file_path).name
    assert backup_file.exists()


def test_cli_executor_restores_backup_on_failure(tmp_path, monkeypatch):
    sys_params = DepRepSysParams()
    cli_home = _prepare_cli_home(tmp_path)
    sys_params.jboss_cli_home = cli_home
    sys_params.jboss_cli_home_win = cli_home
    backup_dir = tmp_path / "backup"
    sys_params.singlefile_dep_bak_path = str(backup_dir)

    executor = JbossCliExecutor(sys_params)
    request = _build_request(tmp_path)
    monkeypatch.setattr(JbossCliExecutor, "_preclean_existing_deployment", lambda *_, **__: None)

    def fake_run(cmd, *_, **__):
        with open(request.deploy_file_path, "w", encoding="utf-8") as fp:
            fp.write("broken")
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = executor.deploy(request)

    assert not result.success
    # after failure the original artifact content should be restored from backup
    with open(request.deploy_file_path, encoding="utf-8") as fp:
        assert fp.read() == "demo"


def test_cli_executor_reports_status_callback(tmp_path, monkeypatch):
    sys_params = DepRepSysParams()
    sys_params.jboss_cli_home = str(tmp_path / "dummy")
    executor = JbossCliExecutor(sys_params)
    request = _build_request(tmp_path)
    monkeypatch.setattr(JbossCliExecutor, "_preclean_existing_deployment", lambda *_, **__: None)

    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    script = cli_dir / "demo.cli"
    script.write_text("deploy")

    def fake_build(self, req):
        return (["jboss-cli"], script, cli_dir, cli_dir)

    monkeypatch.setattr(JbossCliExecutor, "_build_cli_command", fake_build)
    monkeypatch.setattr(JbossCliExecutor, "_run_cli", lambda self, cmd, cwd, timeout=None: "status=ok")

    def fake_poll(self, req, *, status_callback=None):
        if status_callback:
            status_callback("正在查询部署状态(1/600)...")
            status_callback("部署状态为 OK")

    monkeypatch.setattr(JbossCliExecutor, "_poll_deployment_status", fake_poll)

    messages = []
    result = executor.deploy(request, status_callback=messages.append)

    assert result.success
    assert any("正在部署" in msg for msg in messages)
    assert any("查询部署状态" in msg for msg in messages)
    assert any("成功" in msg for msg in messages)


def test_cli_executor_attempts_undeploy_before_deploy(tmp_path, monkeypatch):
    sys_params = DepRepSysParams()
    sys_params.jboss_cli_home = str(tmp_path / "dummy")
    executor = JbossCliExecutor(sys_params)
    request = _build_request(tmp_path)

    commands = []

    def fake_build(self, req):
        deploy_dir = tmp_path / "deploy-temp"
        deploy_dir.mkdir()
        script = deploy_dir / "deploy.cli"
        script.write_text("deploy")
        return (["deploy-cli"], script, deploy_dir, deploy_dir)

    def fake_build_from_script(self, script, req):
        return (["undeploy-cli"], tmp_path)

    def fake_run(self, command, cwd, timeout=None):
        commands.append((list(command), timeout))
        return "status=ok"

    monkeypatch.setattr(JbossCliExecutor, "_build_cli_command", fake_build)
    monkeypatch.setattr(JbossCliExecutor, "_build_cli_command_from_script", fake_build_from_script)
    monkeypatch.setattr(JbossCliExecutor, "_run_cli", fake_run)
    monkeypatch.setattr(JbossCliExecutor, "_poll_deployment_status", lambda self, req, status_callback=None: None)

    result = executor.deploy(request)

    assert result.success
    assert commands[0][0][0] == "undeploy-cli"
    assert commands[1][0][0] == "deploy-cli"
