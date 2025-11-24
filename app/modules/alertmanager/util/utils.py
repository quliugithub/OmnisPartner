"""Utility helpers translated from AlertManagerUtil."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

DOT_FORMAT = "%Y.%m.%d %H:%M:%S"


def now() -> datetime:
    return datetime.now(timezone.utc)


def parse_dot_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, DOT_FORMAT).replace(tzinfo=timezone.utc)


def format_dot_datetime(value: datetime | None) -> str:
    if not value:
        return ""
    return value.astimezone(timezone.utc).strftime(DOT_FORMAT)


def generate_event_id() -> str:
    return now().strftime("%Y%m%d%H%M%S%f")


def upper(value: str | None) -> str:
    return value.upper() if value else ""


def flatten_map(data: Mapping[str, Any] | None) -> str:
    if not data:
        return ""
    return ", ".join(f"{key}={value}" for key, value in data.items())





