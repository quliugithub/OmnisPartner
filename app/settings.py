"""Runtime configuration for the FastAPI version of Omnis Partner."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

def _default_not_before() -> datetime:
    return datetime(2020, 1, 1, tzinfo=timezone.utc)


def _default_not_after() -> datetime:
    return datetime(2099, 12, 31, tzinfo=timezone.utc)


class Settings(BaseSettings):
    """Configuration values mapped from environment variables."""

    app_name: str = Field("Omnis Partner API", env="APP_NAME")
    version: str = Field("3.3.12.10-SNAPSHOT", env="APP_VERSION")

    # Feature switches
    omnis_switch_websql: bool = Field(False, env="OMNIS_SWITCH_WEBSQL")
    omnis_switch_alertmanager: bool = Field(False, env="OMNIS_SWITCH_ALERTMANAGER")
    omnis_switch_alertrecovery: bool = Field(False, env="OMNIS_SWITCH_ALERTRECOVERY")
    omnis_switch_deploy: bool = Field(False, env="OMNIS_SWITCH_DEPLOY")
    omnis_switch_esbagent: bool = Field(False, env="OMNIS_SWITCH_ESBAGENT")
    omnis_switch_finereport: bool = Field(False, env="OMNIS_SWITCH_FINEREPORT")
    omnis_switch_cbhreport: bool = Field(False, env="OMNIS_SWITCH_CBHREPORT")

    # Dependent configuration for ESB and FineReport features
    esbagent_cachedb_url: Optional[str] = Field(None, env="ESBAGENT_CACHEDB_URL")
    esbagent_cachedb_username: Optional[str] = Field(None, env="ESBAGENT_CACHEDB_USERNAME")
    esbagent_cachedb_password: Optional[str] = Field(None, env="ESBAGENT_CACHEDB_PASSWORD")
    esbagent_project: Optional[str] = Field(None, env="ESBAGENT_PROJECT")

    finereport_db_url: Optional[str] = Field(None, env="FINEREPORT_DB_URL")
    finereport_db_username: Optional[str] = Field(None, env="FINEREPORT_DB_USERNAME")

    cbh_cms_db_url: Optional[str] = Field(None, env="CBH_CMS_DB_URL")
    cbh_cms_db_username: Optional[str] = Field(None, env="CBH_CMS_DB_USERNAME")
    cbh_cms_db_password: Optional[str] = Field(None, env="CBH_CMS_DB_PASSWORD")

    # AlertManager specifics
    alertmanager_project: str = Field("DEFAULT", env="ALERTMANAGER_PROJECT")
    alertmanager_slave_targets: List[str] = Field(default_factory=list, env="ALERTMANAGER_SLAVE_TARGETS")
    alertmanager_allowed_tokens: List[str] = Field(default_factory=list, env="ALERTMANAGER_ALLOWED_TOKENS")

    # Shared database configuration (used by all modules, including AlertManager)
    db_host: str = Field("127.0.0.1", env="DB_HOST")
    db_port: int = Field(3306, env="DB_PORT")
    db_name: str = Field("omnis", env="DB_NAME")
    db_user: str = Field("omnis", env="DB_USER")
    db_password: str = Field("", env="DB_PASSWORD")
    db_charset: str = Field("utf8mb4", env="DB_CHARSET")
    database_url: Optional[str] = Field(None, env="DATABASE_URL")

    # Nexus repository configuration
    nexus_base_url: str = Field("http://newnexus.cenboomh.com", env="NEXUS_BASE_URL")
    nexus_repository: str = Field("releases", env="NEXUS_REPOSITORY")
    nexus_username: Optional[str] = Field("ampeng", env="NEXUS_USERNAME")
    nexus_password: Optional[str] = Field("Cbh12345678!", env="NEXUS_PASSWORD")
    nexus_download_dir: str = Field("D:/tmp/nexus", env="NEXUS_DOWNLOAD_DIR")
    deploy_replace_path: str = Field("D:/tmp/replace", env="DEPLOY_REPLACE_PATH")

    # License defaults
    license_products: List[str] = Field(default_factory=lambda: ["ALL"], env="LICENSE_PRODUCTS")
    license_not_before: datetime = Field(default_factory=_default_not_before, env="LICENSE_NOT_BEFORE")
    license_not_after: datetime = Field(default_factory=_default_not_after, env="LICENSE_NOT_AFTER")
    license_auto_pass_on_windows: bool = Field(True, env="LICENSE_AUTO_PASS_ON_WINDOWS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance for dependency injection."""
    return Settings()
