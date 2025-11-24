"""Utilities for loading AlertManager metadata from repositories."""

from __future__ import annotations

import logging

from app.modules.alertmanager.cache.engine import AlertInfoCache
from app.modules.alertmanager.repositories.mysql import MySQLAlertManagerRepository

log = logging.getLogger(__name__)


def load_cache_from_mysql(repo: MySQLAlertManagerRepository) -> AlertInfoCache:
    """Fetch alert metadata from MySQL and hydrate the cache."""
    alertitems, rules, forbids = repo.load_metadata()
    return AlertInfoCache(alertitems=alertitems, msg_send_rules=rules, forbids=forbids)
