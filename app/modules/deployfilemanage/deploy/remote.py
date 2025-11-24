"""Lightweight SSH helper inspired by Java's LinuxConnetionHelper."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


try:  # optional dependency
    import paramiko
except Exception:  # pragma: no cover - optional
    paramiko = None

log = logging.getLogger(__name__)


@dataclass
class RemoteAuth:
    host: str
    username: str
    password: str
    port: int = 22


class RemoteExecutor:
    """Minimal SSH wrapper; requires paramiko to be installed."""

    def __init__(self, auth: RemoteAuth) -> None:
        if paramiko is None:
            raise RuntimeError("paramiko is required for remote deployment but is not installed")
        self.auth = auth
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            hostname=auth.host,
            username=auth.username,
            password=auth.password,
            port=auth.port or 22,
            look_for_keys=False,
        )

    def run(self, command: str, timeout: int = 30) -> str:
        """Execute a remote shell command."""
        log.info("Remote exec %s: %s", self.auth.host, command)
        stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
        out = stdout.read().decode(errors="ignore")
        err = stderr.read().decode(errors="ignore")
        if err:
            log.warning("Remote stderr: %s", err.strip())
        return out

    def upload(self, local_path: Path, remote_dir: str, remote_name: Optional[str] = None) -> str:
        """Upload a file to remote_dir; returns remote path."""
        remote_dir = remote_dir if remote_dir.endswith("/") else remote_dir + "/"
        target_name = remote_name or local_path.name
        try:
            self.run(f"mkdir -p {remote_dir}")
        except Exception:
            log.debug("Ignore mkdir failure for %s", remote_dir)
        sftp = self.client.open_sftp()
        try:
            remote_path = remote_dir + target_name
            sftp.put(str(local_path), remote_path)
            return remote_path
        finally:
            sftp.close()

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:  # pragma: no cover - best effort
            pass

    def __enter__(self) -> "RemoteExecutor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
