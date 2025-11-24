"""Lightweight translation of the Java DeployInvoker/DeployThread."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from queue import Queue, Empty
from typing import Callable, Dict, Optional

from app.modules.deployfilemanage.domain import DeployRequest, DeployResultRecord
from app.modules.deployfilemanage.service.deploy_process import TaskStatusNotifier
from .springboot import SpringBootDeployer
from .jboss_cli import JbossCliExecutor
from .strategies import DeployStrategy, JbossCliStrategy, SpringBootStrategy


@dataclass
class DeployTask:
    """Represents a single deployment job."""

    dep_event_id: str
    task_id: str
    server_key: str
    request: Optional[DeployRequest] = None


class DeployThread(threading.Thread):
    """Worker thread that sequentially executes deployment tasks for a server."""

    def __init__(
        self,
        *,
        server_key: str,
        executor: Callable[[DeployTask], None],
        queue: Queue,
    ) -> None:
        super().__init__(name=f"DeployThread-{server_key}", daemon=True)
        self.server_key = server_key
        self.executor = executor
        self.queue = queue
        self._stop_event = threading.Event()
        self.log = logging.getLogger(self.__class__.__name__)

    def run(self) -> None:  # pragma: no cover - continuous loop
        self.log.info("Deploy thread started for %s", self.server_key)
        while not self._stop_event.is_set():
            try:
                task: DeployTask = self.queue.get(timeout=1)
            except Empty:
                continue
            try:
                self.executor(task)
            except Exception as exc:  # noqa: BLE001
                self.log.exception("Deploy task %s failed: %s", task.task_id, exc)
            finally:
                self.queue.task_done()
        self.log.info("Deploy thread stopped for %s", self.server_key)

    def stop(self) -> None:
        self._stop_event.set()


class DeployInvokerService:
    """Python equivalent of DeployInvoker managing per-server queues."""

    def __init__(
        self,
        *,
        cli_executor: JbossCliExecutor,
        status_notifier: TaskStatusNotifier,
        springboot_executor: Optional[SpringBootDeployer] = None,
    ) -> None:
        self.thread_pool: Dict[str, DeployThread] = {}
        self.wait_queues: Dict[str, Queue] = {}
        self.log = logging.getLogger(self.__class__.__name__)
        self.cli_executor = cli_executor
        self.status_notifier = status_notifier
        self.springboot_executor = springboot_executor
        self.strategies: list[DeployStrategy] = [JbossCliStrategy(cli_executor)]
        if springboot_executor:
            self.strategies.insert(0, SpringBootStrategy(springboot_executor))

    def submit(self, task: DeployTask) -> None:
        """Enqueue a deploy task for execution."""
        queue = self.wait_queues.setdefault(task.server_key, Queue())
        thread = self.thread_pool.get(task.server_key)
        if not thread or not thread.is_alive():
            thread = DeployThread(
                server_key=task.server_key,
                executor=self._execute_task,
                queue=queue,
            )
            self.thread_pool[task.server_key] = thread
            thread.start()
        queue.put(task)
        self.log.info("Task %s enqueued for %s", task.task_id, task.server_key)

    def kill_server_tasks(self, server_key: str, reason: str) -> None:
        """Stop the worker thread and drop queued tasks for a server."""
        thread = self.thread_pool.get(server_key)
        if thread:
            thread.stop()
        queue = self.wait_queues.get(server_key)
        if queue:
            with queue.mutex:
                queue.queue.clear()
        self.log.warning("Killed deploy tasks for %s reason=%s", server_key, reason)

    def _execute_task(self, task: DeployTask) -> None:
        """Execute deployments using the configured executor."""
        if not task.request:
            self.log.error("Task %s missing DeployRequest payload", task.task_id)
            return

        self.log.info(
            "Executing deploy task event=%s task=%s server=%s",
            task.dep_event_id,
            task.task_id,
            task.server_key,
        )
        status_callback = self._build_status_callback(task.request)
        try:
            strategy = self._find_strategy(task.request)
            result = strategy.deploy(task.request)
        except Exception as exc:  # noqa: BLE001
            result = DeployResultRecord(msg=str(exc), msg_full=str(exc), success=False)
            result.task_id = task.task_id
            result.deploy_id = task.dep_event_id
            result.username = task.request.username
            if status_callback:
                try:
                    status_callback(result.msg)
                except Exception:  # pragma: no cover - defensive
                    self.log.exception(
                        "Status callback raised for failed task=%s", task.task_id
                    )
            else:
                self._send_status(task.request, result.msg)
            return

        if not status_callback:
            self._send_status(task.request, result.msg)

    def _operation_label(self, request: DeployRequest) -> str:
        if request.is_undeploy:
            return '[\u5378\u8f7d]'
        soft_type = (request.deploy_type or '').lower()
        if 'jboss7' in soft_type:
            return '[Jboss7\u90e8\u7f72]'
        if 'springboot' in soft_type:
            return '[SpringBoot\u90e8\u7f72]'
        return '[Jboss\u90e8\u7f72]'

    def _find_strategy(self, request: DeployRequest) -> DeployStrategy:
        for strat in self.strategies:
            if strat.matches(request):
                return strat
        return self.strategies[-1]

    def _build_status_callback(
        self,
        request: DeployRequest,
    ) -> Optional[Callable[[str], None]]:
        if not self.status_notifier or not request.task_id:
            return None
        username = request.username or "-"
        task_id = request.task_id
        op_type = self._operation_label(request)

        def _callback(message: str) -> None:
            if not message:
                return
            self.status_notifier.notify(
                username=username,
                op_type=op_type,
                message=message,
                task_ids=[task_id],
            )

        return _callback

    def _send_status(self, request: DeployRequest, message: Optional[str]) -> None:
        if not message or not self.status_notifier or not request.task_id:
            return
        self.status_notifier.notify(
            username=request.username or "-",
            op_type=self._operation_label(request),
            message=message,
            task_ids=[request.task_id],
        )

