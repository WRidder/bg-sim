"""The FastAPI application (plan sections 3.7 and 6).

The app exposes ``GET /api/health``, includes the three API routers (``proxy`` with
the catalog and check endpoints, and the ``projects``/``runs`` skeleton routers that
P1.1 and P1.2 fill in) and serves the built web app (``web/dist``) at ``/`` when it
exists, with an SPA fallback; when there is no build, ``/`` answers a small JSON
document. The lifespan hook starts and stops the worker supervisor.
"""

from __future__ import annotations

import platform
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from . import data, docs, meshes, projects, proxy, runs, stream
from .config import BACKEND_VERSION, Settings
from .proxy import CatalogCache, WorkerRpcFailure
from .worker import WorkerLauncher, WorkerSupervisor

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


def create_app(
    settings: Settings | None = None,
    worker_factory: Callable[[int], WorkerLauncher] | None = None,
) -> FastAPI:
    """Build the application.

    ``settings`` defaults to :meth:`Settings.from_env`; ``worker_factory`` replaces
    the worker launcher (tests use it to script the worker, ``BGSIM_FAKE_WORKER``
    does the same from the environment).
    """
    resolved = settings or Settings.from_env()
    supervisor = WorkerSupervisor(resolved, worker_factory)

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
    app.state.catalog_cache = CatalogCache()

    @app.exception_handler(WorkerRpcFailure)
    async def worker_rpc_failure(_request: Request, exc: WorkerRpcFailure) -> JSONResponse:
        """Plan 3.6: a worker error response becomes 422 with its error object."""
        return JSONResponse(
            status_code=422,
            content={"message": exc.message, "diagnostics": exc.diagnostics},
        )

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

    # The routers that own their endpoints; P1.1 and P1.2 add routes to the last two
    # without touching this file. The SPA catch-all below must stay registered last.
    app.include_router(proxy.router, prefix="/api", tags=["proxy"])
    app.include_router(projects.router, prefix="/api", tags=["projects"])
    app.include_router(runs.router, prefix="/api", tags=["runs"])
    app.include_router(meshes.router, prefix="/api", tags=["meshes"])
    app.include_router(data.router, prefix="/api", tags=["data"])
    app.include_router(docs.router, prefix="/api", tags=["docs"])
    app.include_router(stream.router, prefix="/api", tags=["stream"])
    app.include_router(stream.alias_router)  # WS /ws/stream/{id}, as in the plan's API table

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
