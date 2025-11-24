"""HTTP client to interact with Nexus repositories."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import httpx

from app.modules.deployfilemanage.domain import ArtifactCoordinates
from app.settings import Settings


class NexusDownloader:
    """Download artifacts from a Nexus repository to the local filesystem."""

    def __init__(self, settings: Settings, client: Optional[httpx.Client] = None) -> None:
        self.settings = settings
        self.base_url = settings.nexus_base_url.rstrip("/")
        self.repository = settings.nexus_repository
        self.download_dir = Path(settings.nexus_download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.log = logging.getLogger(self.__class__.__name__)
        auth = None
        if settings.nexus_username and settings.nexus_password:
            auth = (settings.nexus_username, settings.nexus_password)
        self._auth = auth
        self._client = client or httpx.Client(timeout=30, verify=True)

    def _build_artifact_url(self, coords: ArtifactCoordinates, base_url: Optional[str] = None) -> str:
        base = (base_url or self.base_url).rstrip("/")
        path = "/".join(coords.path_segments)
        return f"{base}/repository/{self.repository}/{path}"

    def download(
        self,
        coords: ArtifactCoordinates,
        base_url: Optional[str] = None,
        *,
        dest_path: Optional[Path] = None,
        force: bool = False,
        username: Optional[str] = None,
        userid: Optional[str] = None,
    ) -> Path:
        url = self._build_artifact_url(coords, base_url=base_url)
        filename = coords.path_segments[-1]
        target = dest_path or (self.download_dir / filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not force:
            self.log.info(
                "Reusing cached artifact group=%s artifact=%s version=%s user=%s(%s) -> %s",
                coords.groupid,
                coords.artifactid,
                coords.version,
                username or "-",
                userid or "-",
                target,
            )
            return target
        self.log.info(
            "Downloading artifact group=%s artifact=%s version=%s user=%s(%s) url=%s",
            coords.groupid,
            coords.artifactid,
            coords.version,
            username or "-",
            userid or "-",
            url,
        )
        start_time = time.time()
        downloaded = 0
        with self._client.stream("GET", url, auth=self._auth) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            next_percent = 10
            next_bytes_logged = 5 * 1024 * 1024  # log every 5MB when size unknown
            with open(target, "wb") as fh:
                for chunk in response.iter_bytes(65536):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        percent = int(downloaded * 100 / total)
                        if percent >= next_percent:
                            self.log.info(
                                "Download progress %s:%s:%s user=%s(%s) %s%% (%d/%d bytes)",
                                coords.groupid,
                                coords.artifactid,
                                coords.version,
                                username or "-",
                                userid or "-",
                                percent,
                                downloaded,
                                total,
                            )
                            next_percent += 10
                    else:
                        if downloaded >= next_bytes_logged:
                            self.log.info(
                                "Download progress %s:%s:%s user=%s(%s) %d bytes",
                                coords.groupid,
                                coords.artifactid,
                                coords.version,
                                username or "-",
                                userid or "-",
                                downloaded,
                            )
                            next_bytes_logged += 5 * 1024 * 1024
        elapsed = max(time.time() - start_time, 1e-3)
        speed_mb_s = (downloaded / 1024 / 1024) / elapsed
        self.log.info(
            "Downloaded artifact group=%s artifact=%s version=%s user=%s(%s) -> %s (%d bytes, %.2f MB/s, %.2fs)",
            coords.groupid,
            coords.artifactid,
            coords.version,
            username or "-",
            userid or "-",
            target,
            downloaded,
            speed_mb_s,
            elapsed,
        )
        return target

    def get_latest_version(self, groupid: str, artifactid: str, base_url: Optional[str] = None) -> Optional[str]:
        base = (base_url or self.base_url).rstrip("/")
        search_url = f"{base}/service/rest/v1/search"
        params = {
            "repository": self.repository,
            "group": groupid,
            "name": artifactid,
            "sort": "version",
            "direction": "desc",
        }
        resp = self._client.get(search_url, params=params, auth=self._auth)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items") or []
        if not items:
            return None
        return items[0].get("version")

    def version_exists(
        self,
        groupid: str,
        artifactid: str,
        version: str,
        base_url: Optional[str] = None,
    ) -> bool:
        base = (base_url or self.base_url).rstrip("/")
        search_url = f"{base}/service/rest/v1/search"
        params = {
            "repository": self.repository,
            "group": groupid,
            "name": artifactid,
            "version": version,
        }
        resp = self._client.get(search_url, params=params, auth=self._auth)
        resp.raise_for_status()
        data = resp.json()
        return bool(data.get("items"))

if __name__ == "__main__":
    coords = ArtifactCoordinates(groupid="com.cenboomh.sdxm.bds", artifactid="bds-ui-server", version="1.0.30-SDXM",
                                 extension="war")

    downloader = NexusDownloader(Settings())

    path = downloader.download(coords)
