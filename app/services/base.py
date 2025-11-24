"""Shared utilities for translated service classes."""

from __future__ import annotations

import logging

from ..settings import Settings


class BaseService:
    """Base service offering a logger and settings access."""

    def __init__(self, settings: Settings, logger_name: str | None = None) -> None:
        self.settings = settings
        self.log = logging.getLogger(logger_name or self.__class__.__name__)
