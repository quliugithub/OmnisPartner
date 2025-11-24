"""Database helpers for the FastAPI application."""

from __future__ import annotations

import pymysql
from pymysql.connections import Connection

from app.settings import Settings


def build_mysql_dsn(settings: Settings) -> dict:
    """Return kwargs for pymysql based on shared DB settings."""
    if settings.database_url:
        # Users can supply a full DSN string when preferred.
        return {"dsn": settings.database_url}

    return {
        "host": settings.db_host,
        "port": settings.db_port,
        "user": settings.db_user,
        "password": settings.db_password,
        "db": settings.db_name,
        "charset": settings.db_charset,
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": True,
    }


def mysql_connection(settings: Settings) -> Connection:
    """Create a raw pymysql connection."""
    kwargs = build_mysql_dsn(settings)
    if "dsn" in kwargs:
        return pymysql.connect(kwargs["dsn"])
    return pymysql.connect(**kwargs)
