"""FastAPI application for the local TrimTank web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .cli import get_version
from .projects import (
    browse_directory,
    create_directory,
    create_project,
    get_filesystem_roots,
    get_source_image_path,
    inspect_project,
    list_project_images,
    open_project,
    update_image_crop,
    update_image_status,
)


APP_NAME = "TrimTank"
PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
TEMPLATES_DIR = PACKAGE_DIR / "templates"


class CreateFolderRequest(BaseModel):
    parent_path: str
    name: str


class ProjectPathRequest(BaseModel):
    path: str
    name: str | None = None


class ImageStatusRequest(BaseModel):
    path: str
    filename: str
    status: str


class ImageCropRequest(BaseModel):
    path: str
    filename: str
    crop: dict[str, float] | None = None

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

    @app.get("/api/filesystem/roots")
    async def filesystem_roots() -> dict[str, object]:
        return {"roots": get_filesystem_roots()}

    @app.get("/api/filesystem/browse")
    async def filesystem_browse(path: str | None = Query(default=None)) -> dict[str, object]:
        try:
            return browse_directory(path)
        except Exception as exc:
            raise _filesystem_error(exc) from exc

    @app.post("/api/filesystem/create-folder")
    async def filesystem_create_folder(payload: CreateFolderRequest) -> dict[str, object]:
        try:
            directory = create_directory(payload.parent_path, payload.name)
            return {
                "directory": {
                    "name": directory.name,
                    "path": str(directory),
                },
                "browse": browse_directory(str(directory)),
            }
        except Exception as exc:
            raise _filesystem_error(exc) from exc

    @app.post("/api/projects/inspect")
    async def project_inspect(payload: ProjectPathRequest) -> dict[str, object]:
        try:
            return inspect_project(payload.path)
        except Exception as exc:
            raise _filesystem_error(exc) from exc

    @app.post("/api/projects/create")
    async def project_create(payload: ProjectPathRequest) -> dict[str, object]:
        try:
            return create_project(payload.path, payload.name)
        except Exception as exc:
            raise _filesystem_error(exc) from exc

    @app.post("/api/projects/open")
    async def project_open(payload: ProjectPathRequest) -> dict[str, object]:
        try:
            return open_project(payload.path)
        except Exception as exc:
            raise _filesystem_error(exc) from exc

    @app.get("/api/projects/images")
    async def project_images(path: str = Query()) -> dict[str, object]:
        try:
            return list_project_images(path)
        except Exception as exc:
            raise _filesystem_error(exc) from exc

    @app.get("/api/projects/images/source")
    async def project_image_source(path: str = Query(), filename: str = Query()) -> FileResponse:
        try:
            source_path = get_source_image_path(path, filename)
            return FileResponse(source_path)
        except Exception as exc:
            raise _filesystem_error(exc) from exc

    @app.post("/api/projects/images/status")
    async def project_image_status(payload: ImageStatusRequest) -> dict[str, object]:
        try:
            return update_image_status(payload.path, payload.filename, payload.status)
        except Exception as exc:
            raise _filesystem_error(exc) from exc

    @app.post("/api/projects/images/crop")
    async def project_image_crop(payload: ImageCropRequest) -> dict[str, object]:
        try:
            return update_image_crop(payload.path, payload.filename, payload.crop)
        except Exception as exc:
            raise _filesystem_error(exc) from exc

    return app

def _filesystem_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (FileExistsError, NotADirectoryError, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))

    return HTTPException(status_code=500, detail="Unexpected filesystem error.")
