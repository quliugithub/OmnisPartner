"""Domain objects for deploy file management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class ArtifactCoordinates:
    """Represents a Maven/Nexus artifact coordinate."""

    groupid: str
    artifactid: str
    version: str
    extension: str = "jar"

    @property
    def path_segments(self) -> List[str]:
        group_path = self.groupid.replace(".", "/")
        filename = f"{self.artifactid}-{self.version}.{self.extension}"
        return [group_path, self.artifactid, self.version, filename]
