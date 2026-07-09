"""FastAPI application for the local TrimTank web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .cli import get_version


APP_NAME = "TrimTank"
PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
TEMPLATES_DIR = PACKAGE_DIR / "templates"


def create_app(dev: bool = False) -> FastAPI:
    version = get_version()
    app = FastAPI(title=APP_NAME, version=version)
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    if dev:
        @app.middleware("http")
        async def add_no_cache_headers(request, call_next):  # type: ignore[no-untyped-def]
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Response:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "app_name": APP_NAME,
                "version": version,
                "dev": dev,
            },
        )

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "app": "trimtank",
            "status": "ok",
            "version": version,
            "dev": dev,
        }

    return app
