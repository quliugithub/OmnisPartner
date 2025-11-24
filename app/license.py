"""License helpers translated from the legacy Spring component."""

from __future__ import annotations

import logging
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Set

from .settings import Settings

log = logging.getLogger(__name__)


class OmnisProductName(str, Enum):
    WEBSQL = "WEBSQL"
    MONITOR = "MONITOR"
    DEPLOY = "DEPLOY"
    ALL = "ALL"


@dataclass
class LicenseInfo:
    """In-memory representation of the loaded license."""

    issued_time: datetime | None = None
    expiry_time: datetime | None = None
    auth: bool = False
    auth_products: Set[OmnisProductName] = field(default_factory=set)

    def set_products(self, products: Iterable[str]) -> None:
        self.auth_products = {
            OmnisProductName(product.strip().upper())
            for product in products
            if product
        }


class Lic4Business:
    """Rudimentary port of the Java static license helper."""

    _license = LicenseInfo()
    _auto_pass_on_windows: bool = True

    @classmethod
    def configure_from_settings(cls, settings: Settings) -> None:
        cls._auto_pass_on_windows = settings.license_auto_pass_on_windows
        cls.set_issue_and_expire_time(settings.license_not_before, settings.license_not_after)
        cls._license.set_products(settings.license_products)
        cls.set_auth(True)

    @classmethod
    def set_issue_and_expire_time(cls, not_before: datetime, not_after: datetime) -> None:
        cls._license.issued_time = not_before
        cls._license.expiry_time = not_after

    @classmethod
    def set_auth(cls, is_auth: bool) -> None:
        cls._license.auth = is_auth

    @classmethod
    def set_check_model_infos(cls, model: LicenseInfo | None) -> None:
        if model is None:
            cls._license.auth = False
        else:
            cls._license = model

    @classmethod
    def get_license_info(cls) -> LicenseInfo:
        return cls._license

    @classmethod
    def have_license(cls, product: OmnisProductName | None) -> bool:
        if cls._auto_pass_on_windows and platform.system().lower().startswith("win"):
            return True

        info = cls._license
        if not info.auth:
            log.warning("License validation failed.")
            return False

        now = datetime.now(timezone.utc)
        if info.issued_time and info.issued_time > now:
            log.warning("License is not yet active.")
            return False
        if info.expiry_time and info.expiry_time < now:
            log.warning("License has expired.")
            return False

        if product is None:
            return True

        if OmnisProductName.ALL in info.auth_products:
            return True
        if product in info.auth_products:
            return True

        log.warning("Product %s not licensed.", product)
        return False
