import httpx
import pytest

from app.modules.deployfilemanage.domain import ArtifactCoordinates
from app.modules.deployfilemanage.fileget.nexus_downloader import NexusDownloader
from app.settings import Settings


def build_settings(tmp_path, **overrides) -> Settings:
    defaults = {
        "nexus_base_url": "http://newnexus.cenboomh.com",
        "nexus_repository": "releases",
        "nexus_download_dir": str(tmp_path),
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def test_download_writes_file(tmp_path):
    coords = ArtifactCoordinates(groupid="com.cenboomh.sdxm.bds", artifactid="bds-ui-server", version="1.0.30-SDXM", extension="war")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("bds-ui-server-1.0.30-SDXM.war")
        return httpx.Response(200, content=b"binary-data")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    downloader = NexusDownloader(build_settings(tmp_path), client=client)

    path = downloader.download(coords)

    assert path.exists()
    assert path.read_bytes() == b"binary-data"


def test_get_latest_version(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        data = {"items": [{"version": "2.5.1"}]}
        return httpx.Response(200, json=data)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    downloader = NexusDownloader(build_settings(tmp_path), client=client)

    version = downloader.get_latest_version("com.test", "demo")
    assert version == "2.5.1"


def test_version_exists(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {"items": [{"version": "1.0.0"}]}
        if request.url.params.get("version") == "missing":
            payload = {"items": []}
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    downloader = NexusDownloader(build_settings(tmp_path), client=client)

    assert downloader.version_exists("com.test", "demo", "1.0.0")
    assert not downloader.version_exists("com.test", "demo", "missing")
