"""The FastAPI application (plan sections 3.7 and 6).

M0.4 exposes ``GET /api/health`` and serves the built web app (``web/dist``) at
``/`` when it exists, with an SPA fallback; when there is no build, ``/`` answers a
small JSON document. The lifespan hook starts and stops the worker supervisor.
"""

from __future__ import annotations

import platform
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from .config import BACKEND_VERSION, Settings
from .worker import WorkerSupervisor

# API prefixes that must never fall through to the SPA fallback.
_API_PREFIXES = ("api/", "ws/")


def _resolve_web_file(dist: Path, relative: str) -> Path | None:
    """A file inside ``dist`` for a URL path, or ``None`` (also for path escapes)."""
    if not dist.is_dir():
        return None
    root = dist.resolve()
    candidate = (root / relative).resolve() if relative else root / "index.html"
    if not candidate.is_relative_to(root):
        return None
    return candidate if candidate.is_file() else None


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application; ``settings`` defaults to :meth:`Settings.from_env`."""
    resolved = settings or Settings.from_env()
    supervisor = WorkerSupervisor(resolved)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await app.state.worker.start()
        try:
            yield
        finally:
            await app.state.worker.stop()

    app = FastAPI(title="bg-sim backend", version=BACKEND_VERSION, lifespan=lifespan)
    app.state.settings = resolved
    app.state.worker = supervisor

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        """Plan 3.7: ``{ backend, worker, versions }``."""
        return {
            "backend": BACKEND_VERSION,
            "worker": supervisor.state,
            "versions": {
                "backend": BACKEND_VERSION,
                "python": platform.python_version(),
                "julia": supervisor.julia_version,
            },
        }

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> Response:
        if path.startswith(_API_PREFIXES):
            raise HTTPException(status_code=404, detail="not found")
        dist = resolved.web_dist_path
        file = _resolve_web_file(dist, path)
        if file is not None:
            return FileResponse(file)
        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index)  # SPA fallback
        if not path:
            return JSONResponse(
                {
                    "message": "bg-sim backend",
                    "web": "web/dist is not built",
                    "health": "/api/health",
                }
            )
        raise HTTPException(status_code=404, detail="not found")

    return app
