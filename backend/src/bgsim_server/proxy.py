"""HTTP proxies for the worker calls of plan section 3.7.

``GET /api/catalog`` proxies ``catalog.get`` and caches the result per project; the
cache entry is dropped as soon as a file in ``<projects_root>/<project>/library``
changes (the file list, mtimes and sizes are compared on every request).
``POST /api/check/block`` proxies ``block.check`` and ``POST /api/check/model``
proxies ``model.check``.

The per-method timeouts stay in :mod:`bgsim_server.worker` (``block.check`` 5 s,
``model.check`` 60 s): this module calls the supervisor without an explicit timeout
so the plan's limits apply in one place.

Worker failures map to HTTP as follows:

* :class:`~bgsim_server.worker.WorkerTimeout` -> 504 ``{"detail": "... timed out ..."}``;
* :class:`~bgsim_server.worker.WorkerRpcError` -> 422 ``{"message", "diagnostics"}``,
  the worker's error object verbatim (rendered by the handler in ``app.py``);
* :class:`~bgsim_server.worker.WorkerNotReady` -> 503;
* any other :class:`~bgsim_server.worker.WorkerError` -> 502.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from .config import Settings
from .contracts import (
    BlockCheckResult,
    Catalog,
    Model,
    ModelCheckResult,
)
from .worker import (
    WorkerError,
    WorkerNotReady,
    WorkerRpcError,
    WorkerSupervisor,
    WorkerTimeout,
)

router = APIRouter()

# Project names follow the Project contract; "." and ".." are excluded separately.
_PROJECT_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")

# One catalog scan entry: relative POSIX path, mtime in ns, size in bytes.
LibrarySignature = tuple[tuple[str, int, int], ...]


class WorkerRpcFailure(Exception):
    """A worker error response, rendered verbatim as HTTP 422 by ``app.py``."""

    def __init__(self, message: str, diagnostics: list[Any]):
        super().__init__(message)
        self.message = message
        self.diagnostics = list(diagnostics)


class BlockCheckBody(BaseModel):
    """``POST /api/check/block`` body; ``ref`` names the block being edited."""

    model_config = ConfigDict(extra="forbid")

    source: str
    ref: str | None = None


class ModelCheckBody(BaseModel):
    """``POST /api/check/model`` body; ``projectDir`` defaults to the project root."""

    model_config = ConfigDict(extra="forbid")

    model: Model
    projectDir: str | None = None


# --------------------------------------------------------------------------- cache


def library_signature(library_dir: Path | None) -> LibrarySignature | None:
    """A fingerprint of every file in the library, or ``None`` when it cannot be read.

    The fingerprint is the sorted ``(path, mtime_ns, size)`` of every file below
    ``library_dir``. Adding, deleting, renaming or rewriting a file changes it. A
    ``None`` result means "do not trust the cache" rather than "empty library".
    """
    if library_dir is None:
        return ()  # the standard library is not watched
    try:
        if not library_dir.is_dir():
            return ()
        entries: list[tuple[str, int, int]] = []
        for path in library_dir.rglob("*"):
            if not path.is_file():
                continue
            stat = path.stat()
            entries.append(
                (path.relative_to(library_dir).as_posix(), stat.st_mtime_ns, stat.st_size)
            )
    except OSError:
        return None
    entries.sort()
    return tuple(entries)


class CatalogCache:
    """The catalog per project, invalidated by the project library's fingerprint.

    ``None`` is the standard-library-only catalog. The cache stores the worker's
    result as sent, so a hit returns exactly what a miss would return.
    """

    def __init__(self) -> None:
        self._entries: dict[str | None, tuple[LibrarySignature, Any]] = {}
        self._locks: dict[str | None, asyncio.Lock] = {}

    def lock_for(self, project: str | None) -> asyncio.Lock:
        """The per-project lock that keeps simultaneous misses to one worker call."""
        lock = self._locks.get(project)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[project] = lock
        return lock

    def peek(self, project: str | None, library_dir: Path | None) -> Any | None:
        """The cached catalog, or ``None`` when absent or stale (then it is dropped)."""
        entry = self._entries.get(project)
        if entry is None:
            return None
        signature = library_signature(library_dir)
        if signature is None or signature != entry[0]:
            self._entries.pop(project, None)
            return None
        return entry[1]

    def store(self, project: str | None, library_dir: Path | None, catalog: Any) -> None:
        """Cache ``catalog``; skip it when the library cannot be fingerprinted."""
        signature = library_signature(library_dir)
        if signature is None:
            return
        self._entries[project] = (signature, catalog)

    def invalidate(self, project: str | None = None, *, all_projects: bool = False) -> None:
        """Drop one project's entry, or everything with ``all_projects=True``."""
        if all_projects:
            self._entries.clear()
        else:
            self._entries.pop(project, None)

    def __len__(self) -> int:
        return len(self._entries)


# --------------------------------------------------------------------------- helpers


def _project_name(project: str | None) -> str | None:
    """Normalise the query value; an empty ``?project=`` means "no project"."""
    if project is None:
        return None
    name = project.strip()
    return name or None


def _project_dir(settings: Settings, project: str) -> Path:
    """``<projects_root>/<project>`` for an existing project, else HTTP 404."""
    if project in {".", ".."} or not _PROJECT_NAME.fullmatch(project):
        raise HTTPException(status_code=404, detail=f"unknown project {project!r}")
    root = settings.projects_root.resolve()
    directory = (root / project).resolve()
    if not directory.is_relative_to(root) or not directory.is_dir():
        raise HTTPException(status_code=404, detail=f"unknown project {project!r}")
    return directory


def _validated(schema: type[BaseModel], result: Any, method: str) -> Any:
    """Reject a worker result that does not match ``contracts/`` with HTTP 502."""
    try:
        schema.model_validate(result)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first.get("loc", ())) or "<root>"
        raise HTTPException(
            status_code=502,
            detail=(
                f"{method} returned a result that violates the contract: "
                f"{location}: {first.get('msg', 'invalid value')}"
            ),
        ) from None
    return result


async def _call_worker(request: Request, method: str, params: dict[str, Any]) -> Any:
    """One request through the shared supervisor, with the plan's error mapping."""
    supervisor: WorkerSupervisor = request.app.state.worker
    try:
        return await supervisor.call(method, params)
    except WorkerTimeout as exc:
        raise HTTPException(status_code=504, detail=f"{method} timed out: {exc}") from exc
    except WorkerRpcError as exc:
        raise WorkerRpcFailure(str(exc), exc.diagnostics) from exc
    except WorkerNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except WorkerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# --------------------------------------------------------------------------- routes


@router.get("/catalog")
async def catalog(
    request: Request,
    project: str | None = Query(
        default=None,
        description="Project name whose library is included; omit for the standard library.",
    ),
) -> Any:
    """Plan 3.7: the library catalog, proxied from ``catalog.get`` and cached."""
    settings: Settings = request.app.state.settings
    cache: CatalogCache = request.app.state.catalog_cache
    name = _project_name(project)
    library_dir = (_project_dir(settings, name) / "library") if name is not None else None

    async with cache.lock_for(name):
        cached = cache.peek(name, library_dir)
        if cached is not None:
            return cached
        params = {
            "projectLibraryDir": str(library_dir.resolve()) if library_dir is not None else None
        }
        result = await _call_worker(request, "catalog.get", params)
        catalog_result = _validated(Catalog, result, "catalog.get")
        cache.store(name, library_dir, catalog_result)
        return catalog_result


@router.post("/check/block")
async def check_block(body: BlockCheckBody, request: Request) -> Any:
    """Plan 3.7: the fast as-you-type check of one block source, 5 s timeout."""
    params = {"source": body.source, "ref": body.ref}
    result = await _call_worker(request, "block.check", params)
    return _validated(BlockCheckResult, result, "block.check")


@router.post("/check/model")
async def check_model(
    body: ModelCheckBody,
    request: Request,
    project: str | None = Query(
        default=None,
        description="Project name used to derive projectDir when the body omits it.",
    ),
) -> Any:
    """Plan 3.7: the model check, 60 s timeout.

    ``projectDir`` comes from the body; when it is absent the ``project`` query
    parameter names the project, and without that the repository root is used.
    """
    settings: Settings = request.app.state.settings
    project_dir = body.projectDir
    if project_dir is None:
        name = _project_name(project)
        if name is not None:
            project_dir = str(_project_dir(settings, name))
        else:
            project_dir = str(settings.repo_root)
    params = {
        "model": body.model.model_dump(by_alias=True, mode="json"),
        "projectDir": project_dir,
    }
    result = await _call_worker(request, "model.check", params)
    return _validated(ModelCheckResult, result, "model.check")
