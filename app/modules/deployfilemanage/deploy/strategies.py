"""Strategy-based deployers mirroring the Java dispatch style."""

from __future__ import annotations

import logging
from typing import Protocol

from app.modules.deployfilemanage.domain import DeployRequest, DeployResultRecord
from app.modules.deployfilemanage.service.deploy_process import TaskStatusNotifier
from .jboss_cli import JbossCliExecutor
from .springboot import SpringBootDeployer


class DeployStrategy(Protocol):
    """Common interface for deployment strategies."""

    def matches(self, request: DeployRequest) -> bool:  # pragma: no cover - interface
        ...

    def deploy(self, request: DeployRequest) -> DeployResultRecord:  # pragma: no cover - interface
        ...


class JbossCliStrategy:
    """Default strategy using JBoss CLI (covers war/jboss6/jboss7)."""

    def __init__(self, executor: JbossCliExecutor) -> None:
        self.executor = executor

    def matches(self, request: DeployRequest) -> bool:
        dtype = (request.deploy_type or "").lower()
        return any(key in dtype for key in ("jboss", "war")) or not dtype

    def deploy(self, request: DeployRequest) -> DeployResultRecord:
        return self.executor.deploy(request)


class SpringBootStrategy:
    """Strategy for Spring Boot ZIP deploy (simplified)."""

    def __init__(self, deployer: SpringBootDeployer) -> None:
        self.deployer = deployer
        self.log = logging.getLogger(self.__class__.__name__)

    def matches(self, request: DeployRequest) -> bool:
        dtype = (request.deploy_type or "").lower()
        return "springboot" in dtype or dtype == "2"

    def deploy(self, request: DeployRequest) -> DeployResultRecord:
        return self.deployer.deploy(request)
