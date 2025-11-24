"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from .api import alertmanager_router, health_router
from .bootstrap import ServiceContainer, bootstrap_services
from .license import Lic4Business
from .logging_config import configure_logging
from .settings import get_settings
from .switches import OmnisSwitch
from app.modules.deployfilemanage import deployfile_router


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    Lic4Business.configure_from_settings(settings)

    switches = OmnisSwitch(settings)
    services = ServiceContainer(settings)

    app = FastAPI(title=settings.app_name, version=settings.version)
    app.include_router(health_router)
    app.include_router(alertmanager_router)
    app.include_router(deployfile_router)
    app.state.container = services
    app.state.switches = switches

    @app.on_event("startup")
    async def _startup() -> None:  # pragma: no cover - invoked by FastAPI
        await bootstrap_services(services, switches)

    return app
