"""Simple properties replacement logic."""

from __future__ import annotations

from typing import Dict

from app.modules.deployfilemanage.repositories import DepRepRepository


class SimplePropertiesContentReplace:
    """Port of the Java SimplePropertiesContentReplace."""

    def __init__(self, repository: DepRepRepository) -> None:
        self.repository = repository

    def replace(self, original: str, env_global_name: str) -> str:
        hospital, env_name, group_name = self._parse_env_name(env_global_name)
        details = self.repository.get_global_details(hospital, env_name, group_name) or {}

        output_lines = []
        for raw_line in original.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                output_lines.append(line)
                continue
            if "=" not in line:
                output_lines.append(line)
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in details:
                value = details[key]
            output_lines.append(f"{key}={value}")
        return "\n".join(output_lines)

    @staticmethod
    def _parse_env_name(env_global_name: str) -> tuple[str, str, str]:
        parts = [segment.strip() for segment in env_global_name.split(".") if segment.strip()]
        if len(parts) < 3:
            raise ValueError("env global name must contain hospital, env, group (e.g. H0016.CBH.omnis_backend)")
        return parts[0], parts[1], parts[2]
