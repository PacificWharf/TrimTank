"""FastAPI application for the local TrimTank web UI."""

from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse

from .cli import get_version


def create_app(dev: bool = False) -> FastAPI:
    app = FastAPI(title="TrimTank", version=get_version())

    if dev:
        @app.middleware("http")
        async def add_no_cache_headers(request, call_next):  # type: ignore[no-untyped-def]
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _placeholder_page()

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "app": "trimtank",
            "status": "ok",
            "version": get_version(),
            "dev": dev,
        }

    return app


def _placeholder_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TrimTank</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #101216;
      color: #f2f5f8;
    }

    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #101216;
    }

    main {
      width: min(720px, calc(100vw - 32px));
    }

    h1 {
      margin: 0 0 12px;
      font-size: clamp(2rem, 7vw, 4rem);
      line-height: 1;
    }

    p {
      max-width: 48rem;
      margin: 0;
      color: #c3ccd8;
      font-size: 1.125rem;
      line-height: 1.6;
    }
  </style>
</head>
<body>
  <main>
    <h1>TrimTank</h1>
    <p>Local image dataset preparation is starting here.</p>
  </main>
</body>
</html>
"""
