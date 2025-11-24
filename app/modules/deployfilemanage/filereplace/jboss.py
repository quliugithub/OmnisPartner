"""JBoss-specific replacement strategy."""

from __future__ import annotations

from pathlib import Path

from app.modules.deployfilemanage.filereplace.base_strategy import AbsReplaceStrategy
from app.modules.deployfilemanage.filereplace.simple_properties_replace import SimplePropertiesContentReplace


class CbhJbossReplaceStrategy(AbsReplaceStrategy):
    def __init__(
        self,
        replace_root: Path,
        properties_replacer: SimplePropertiesContentReplace | None = None,
        event_publisher=None,
    ) -> None:
        super().__init__(replace_root, properties_replacer, event_publisher)
