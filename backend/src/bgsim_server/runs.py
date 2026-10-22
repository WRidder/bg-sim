"""Run creation, manifests, data, CSV and the run WebSocket (plan 3.5-3.7, 6).

The router owns the run lifecycle on the backend side:

* ``POST /api/projects/{project}/runs`` allocates ``<project>/runs/<run-id>/``,
  prunes the model's history (the last 20 runs, ``BGSIM_RUN_HISTORY``), builds a
  running manifest skeleton, calls ``run.start`` on the worker and starts a
  monitor that fans the ``run.*`` notifications out to WebSocket subscribers.
  The worker (fake or Julia) writes ``manifest.json``, ``stream.f64`` and
  ``columns.f64`` into the run directory itself (plan 3.5); the skeleton is only
  served until the worker has published its manifest.
* ``GET /api/runs/{run_id}`` returns the manifest. While a run is still
  simulating the response carries the live status and the rows written so far.
* ``GET /api/runs/{run_id}/data`` returns the binary frame of plan 3.7:
  ``u32 n_signals | u32 n_points | time column | one Float64 column per
  signal``, little-endian. ``px`` (default 1600) min/max decimates each signal
  to at most ``2*px`` points; ``px=0`` returns the raw window.
* ``GET /api/runs/{run_id}/export.csv`` writes the same selection as CSV.
* ``DELETE /api/runs/{run_id}`` asks the worker to cancel.
* ``WS /api/ws/runs/{run_id}`` (also aliased at ``/ws/runs/{run_id}`` because
  ``app.py`` includes this router under ``/api``) forwards ``run.phase``,
  ``run.progress`` and ``run.done`` and, after the client sends
  ``{"subscribe": ["signal/id", ...]}``, a decimated ``run.tail`` at most 20
  times per second::

      {"method": "run.tail", "params": {"runId", "ids", "t0", "t1",
                                        "time": [...], "values": [[...], ...]}}

  A subscriber that joins mid-run first receives the data recorded so far for
  its ids (the backlog is sent on ``subscribe``, not on the next progress
  notification), then follows the tail. ``values`` is in ``ids`` order.
  ``run.error`` carries a user-facing message for an unknown run or signal id.

This module also owns the latest-wins coalescing of ``POST /api/check/block``
(P2.1). The endpoint itself lives in :mod:`bgsim_server.proxy`; because this
work package may only touch ``runs.py``/``stream.py``, the application lifespan
installs the coalesced route ahead of the plain proxy one (the same lifespan
hook that adds the unprefixed WebSocket alias). See
:class:`BlockCheckCoalescer`.

The signal list of a running run comes from the worker's manifest, which the
plan says is written next to the data. The fixture-driven fake writes it only
when the run finishes, so in fake mode the skeleton uses the fake's known
synthetic signal table; without a signal list live tails are unavailable until
the manifest appears (the socket then reports ``run.error`` on ``subscribe``).
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import struct
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, BeforeValidator, ConfigDict, ValidationError
from starlette.routing import WebSocketRoute

from .config import Settings
from .contracts import Model, RunManifest
from .decimate import DEFAULT_POINTS, decimate, open_columns, open_stream
from .proxy import BlockCheckBody, WorkerRpcFailure
from .proxy import check_block as proxy_check_block
from .proxy import router as proxy_router
from .worker import (
    _SYNTHETIC_SIGNALS,
    WorkerError,
    WorkerNotReady,
    WorkerRpcError,
    WorkerSupervisor,
    WorkerTimeout,
)

#: Run history kept per model (plan 3.5: the last 20, configurable).
DEFAULT_RUN_HISTORY = 20
RUN_HISTORY_ENV = "BGSIM_RUN_HISTORY"

#: Horizontal resolution of a live tail; the payload has at most 2*this points.
TAIL_POINTS = 200
#: At most 20 tail messages per second (the plan's rate limit for the run WS).
TAIL_MIN_INTERVAL = 0.05

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PROJECT_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")

#: A query number whose empty value (``?t0=&t1=``) means "not given".
OptionalNumber = Annotated[float | None, BeforeValidator(lambda value: None if value == "" else value)]

router = APIRouter()


class RunCreateBody(BaseModel):
    """``POST /api/projects/{p}/runs`` body: the model document to simulate."""

    model_config = ConfigDict(extra="forbid")

    model: Model


# --------------------------------------------------------------------------- helpers


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _project_dir(settings: Settings, project: str) -> Path:
    """``<projects_root>/<project>`` for an existing project, else HTTP 404."""
    if project in {".", ".."} or not _PROJECT_NAME.fullmatch(project):
        raise HTTPException(status_code=404, detail=f"unknown project {project!r}")
    root = settings.projects_root.resolve()
    directory = (root / project).resolve()
    if not directory.is_relative_to(root) or not directory.is_dir():
        raise HTTPException(status_code=404, detail=f"unknown project {project!r}")
    return directory


def _check_run_id(run_id: str) -> None:
    if not _RUN_ID.fullmatch(run_id) or ".." in run_id:
        raise HTTPException(status_code=404, detail=f"unknown run {run_id!r}")


def _find_run_dir(settings: Settings, run_id: str) -> tuple[Path, Path] | None:
    """``(project_dir, run_dir)`` for a run that is not in this process's store."""
    root = settings.projects_root
    if not root.is_dir():
        return None
    for project in sorted(root.iterdir()):
        if not project.is_dir():
            continue
        candidate = project / "runs" / run_id
        if candidate.is_dir():
            return project, candidate
    return None


def _strip_comments(value: Any) -> Any:
    """Remove ``$comment`` keys from a model document (the worker does not need them)."""
    if isinstance(value, dict):
        return {key: _strip_comments(item) for key, item in value.items() if key != "$comment"}
    if isinstance(value, list):
        return [_strip_comments(item) for item in value]
    return value


def run_history_limit() -> int:
    """The configured number of runs kept per model; at least one."""
    raw = os.environ.get(RUN_HISTORY_ENV)
    if raw is None:
        return DEFAULT_RUN_HISTORY
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_RUN_HISTORY


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "manifest.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=500, detail=f"the manifest of run {path.parent.name!r} is unreadable: {exc}"
        ) from None
    _validate_manifest(document, path)
    return document


def _validate_manifest(document: Any, path: Path) -> None:
    try:
        RunManifest.model_validate(document)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first.get("loc", ())) or "<root>"
        raise HTTPException(
            status_code=500,
            detail=(
                f"the manifest {path.name!r} violates the run-manifest contract: "
                f"{location}: {first.get('msg', 'invalid value')}"
            ),
        ) from None


def _model_document(model: Model) -> dict[str, Any]:
    """The model as the worker's ``run.start`` expects it (JSON aliases, no comments)."""
    return _strip_comments(model.model_dump(by_alias=True, mode="json"))


def _skeleton(model: dict[str, Any], run_id: str, settings: Settings) -> dict[str, Any]:
    """The manifest of a run that has not published one yet (plan 3.5)."""
    model_settings = model["settings"]
    signals = [dict(signal) for signal in _SYNTHETIC_SIGNALS] if settings.fake_worker else []
    return {
        "id": run_id,
        "model": str(model["name"]),
        "modelHash": hashlib.sha256(
            json.dumps(model, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "created": _utc_now(),
        "status": "running",
        "settings": model_settings,
        "signals": signals,
        "time": {"n": 0, "t0": float(model_settings["t_start"]), "t1": float(model_settings["t_start"])},
        "diagnostics": [],
        "layout": "columnar-f64-v1",
    }


def _prune_runs(
    project_dir: Path,
    model_name: str,
    keep: int,
    active: set[str],
) -> None:
    """Delete older runs of ``model_name`` beyond ``keep - 1`` (the new run is the last)."""
    runs_dir = project_dir / "runs"
    if not runs_dir.is_dir():
        return
    entries: list[tuple[str, str, Path]] = []
    for candidate in runs_dir.iterdir():
        if not candidate.is_dir() or candidate.name in active:
            continue
        path = candidate / "manifest.json"
        if not path.is_file():
            continue
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if manifest.get("model") != model_name or manifest.get("status") == "running":
            continue
        created = str(manifest.get("created") or "")
        entries.append((created, candidate.name, candidate))
    entries.sort(reverse=True)
    for _, _, directory in entries[max(keep - 1, 0) :]:
        shutil.rmtree(directory, ignore_errors=True)


# --------------------------------------------------------------------------- run store


@dataclass
class _RunState:
    run_id: str
    project_dir: Path
    run_dir: Path
    manifest: dict[str, Any]
    status: str = "running"
    rows: int = 0
    last_phase: dict[str, Any] | None = None
    last_progress: dict[str, Any] | None = None
    done: dict[str, Any] | None = None
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    queue: asyncio.Queue | None = None
    task: asyncio.Task | None = None

    def manifest_document(self) -> dict[str, Any]:
        """The manifest as the API reports it now (file plus live state)."""
        path = self.run_dir / "manifest.json"
        document = _load_manifest(self.run_dir) if path.is_file() else copy.deepcopy(self.manifest)
        if self.done is not None:
            document["status"] = str(self.done.get("status") or self.status)
            if self.done.get("stats") is not None:
                document["stats"] = self.done["stats"]
            if self.done.get("diagnostics") is not None:
                document["diagnostics"] = self.done["diagnostics"]
        elif document.get("status") == "running":
            document["status"] = self.status
            if self.last_progress is not None:
                # ``last_progress`` is the notification, not its params; reading
                # the rows from the envelope left a live manifest at n=0 (P2.1).
                progress = self.last_progress.get("params") or {}
                document["time"] = {
                    "n": int(progress.get("rows") or 0),
                    "t0": document["time"]["t0"],
                    "t1": float(progress.get("t", document["time"]["t0"])),
                }
        _validate_manifest(document, path)
        return document


class RunStore:
    """Per-application run registry: notifications, live state and subscribers."""

    def __init__(self, settings: Settings, supervisor: WorkerSupervisor):
        self.settings = settings
        self.supervisor = supervisor
        self.runs: dict[str, _RunState] = {}

    def get(self, run_id: str) -> _RunState | None:
        return self.runs.get(run_id)

    def active_ids(self) -> set[str]:
        return {run_id for run_id, state in self.runs.items() if state.task is not None}

    async def start(self, state: _RunState) -> None:
        """Subscribe the monitor *before* ``run.start`` so no notification is lost."""
        self.runs[state.run_id] = state
        state.queue = self.supervisor.subscribe(state.run_id)
        state.task = asyncio.create_task(self._monitor(state), name=f"run-monitor-{state.run_id}")

    def forget(self, run_id: str) -> None:
        state = self.runs.pop(run_id, None)
        if state is None:
            return
        if state.queue is not None:
            self.supervisor.unsubscribe(run_id, state.queue)
        if state.task is not None:
            state.task.cancel()
            state.task = None

    async def _monitor(self, state: _RunState) -> None:
        queue = state.queue
        assert queue is not None
        try:
            while True:
                message = await queue.get()
                method = message.get("method")
                params = message.get("params") or {}
                if method == "run.phase":
                    state.last_phase = message
                elif method == "run.progress":
                    state.last_progress = message
                    state.rows = int(params.get("rows") or 0)
                elif method == "run.done":
                    state.done = params
                    state.status = str(params.get("status") or "done")
                for subscriber in list(state.subscribers):
                    subscriber.put_nowait(message)
                if method == "run.done":
                    break
        finally:
            self.supervisor.unsubscribe(state.run_id, queue)
            state.queue = None
            state.task = None

    def subscribe(self, state: _RunState) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        state.subscribers.add(queue)
        return queue

    def unsubscribe(self, state: _RunState, queue: asyncio.Queue) -> None:
        state.subscribers.discard(queue)

    async def aclose(self) -> None:
        tasks = [state.task for state in self.runs.values() if state.task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task
        for state in self.runs.values():
            state.subscribers.clear()


def _store_for(app: Any) -> RunStore:
    store = getattr(app.state, "run_store", None)
    if store is None:
        store = RunStore(app.state.settings, app.state.worker)
        app.state.run_store = store
    return store


def _locate(request: Request | WebSocket, run_id: str) -> tuple[Path, _RunState | None]:
    """The run directory and, when this process started the run, its live state."""
    _check_run_id(run_id)
    store = _store_for(request.app)
    state = store.get(run_id)
    if state is not None:
        return state.run_dir, state
    found = _find_run_dir(request.app.state.settings, run_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"unknown run {run_id!r}")
    return found[1], None


async def _worker_call(request: Request, method: str, params: dict[str, Any]) -> Any:
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


# --------------------------------------------------------------------------- block check


@dataclass
class _BlockCheckJob:
    """One ``block.check`` call and the HTTP callers waiting for its answer."""

    call: Callable[[], Awaitable[Any]]
    waiters: list[asyncio.Future] = field(default_factory=list)


@dataclass
class _BlockCheckKey:
    """The in-flight call of one key and, at most, one queued replacement."""

    running: _BlockCheckJob | None = None
    task: asyncio.Task | None = None
    pending: _BlockCheckJob | None = None


class BlockCheckCoalescer:
    """Latest-wins request coalescing for ``POST /api/check/block`` (P2.1).

    The editor checks a block on every (debounced) keystroke. When a request
    arrives for a key that already has a call in flight, the newer source
    replaces the *queue*: there is at most one running worker call and one
    pending call per key. Every caller waiting for the key is resolved with the
    newest answer, so no older answer is ever returned and five rapid requests
    cause at most two ``block.check`` calls (the abandoned one and the newest).

    The worker protocol has no request cancellation, so an abandoned call is not
    stopped on the wire: the backend stops waiting for it and discards its
    result (and its error). The key is ``(client host, ref scope, ref)``; ``ref``
    already carries the project/stdlib scope, for example ``project:Foo`` or
    ``stdlib:bondgraph/C``.
    """

    def __init__(self) -> None:
        self._keys: dict[tuple[str, str, str], _BlockCheckKey] = {}

    def stats(self) -> dict[str, int]:
        """Counts for diagnostics and tests: live keys, calls and waiters."""
        return {
            "keys": len(self._keys),
            "running": sum(1 for state in self._keys.values() if state.running is not None),
            "pending": sum(1 for state in self._keys.values() if state.pending is not None),
            "waiters": sum(
                len(job.waiters)
                for state in self._keys.values()
                for job in (state.running, state.pending)
                if job is not None
            ),
        }

    async def check(
        self, key: tuple[str, str, str], call: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Coalesce ``call`` under ``key`` and return the newest answer."""
        waiter: asyncio.Future = asyncio.get_running_loop().create_future()
        state = self._keys.get(key)
        if state is None:
            state = _BlockCheckKey()
            self._keys[key] = state
            state.running = _BlockCheckJob(call, [waiter])
            state.task = asyncio.create_task(
                self._run(key, state, state.running), name=f"block-check-{key[2] or 'unnamed'}"
            )
        elif state.pending is None:
            assert state.running is not None
            state.pending = _BlockCheckJob(call, [*state.running.waiters, waiter])
            state.running.waiters.clear()
        else:
            state.pending.call = call
            state.pending.waiters.append(waiter)
        return await waiter

    async def _run(
        self,
        key: tuple[str, str, str],
        state: _BlockCheckKey,
        job: _BlockCheckJob,
    ) -> None:
        result: Any = None
        error: Exception | None = None
        try:
            result = await job.call()
        except asyncio.CancelledError:
            self._abandon(key, state, job)
            raise
        except Exception as exc:  # noqa: BLE001 - the newest caller renders this failure
            error = exc
        if state.pending is not None:
            # This answer is stale: a newer source arrived while it ran. Hand the
            # accumulated callers to the newest call instead of answering them.
            pending, state.pending = state.pending, None
            pending.waiters = [*job.waiters, *pending.waiters]
            state.running = pending
            state.task = asyncio.create_task(
                self._run(key, state, pending), name=f"block-check-{key[2] or 'unnamed'}"
            )
            return
        state.running = None
        state.task = None
        if self._keys.get(key) is state:
            self._keys.pop(key, None)
        for waiter in job.waiters:
            if waiter.done():
                continue  # the HTTP client went away while the call ran
            if error is None:
                waiter.set_result(result)
            else:
                waiter.set_exception(error)

    def _abandon(
        self,
        key: tuple[str, str, str],
        state: _BlockCheckKey,
        job: _BlockCheckJob,
    ) -> None:
        """Cancel the callers of a task that is itself being cancelled."""
        for waiter in job.waiters:
            if not waiter.done():
                waiter.cancel()
        pending, state.pending = state.pending, None
        if pending is not None:
            for waiter in pending.waiters:
                if not waiter.done():
                    waiter.cancel()
        state.running = None
        state.task = None
        if self._keys.get(key) is state:
            self._keys.pop(key, None)

    async def aclose(self) -> None:
        """Cancel every in-flight call (application shutdown)."""
        tasks = [state.task for state in self._keys.values() if state.task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task
        self._keys.clear()


#: The path of the coalesced block-check route (the proxy registers it too).
BLOCK_CHECK_PATH = "/api/check/block"


def _coalescer_for(app: Any) -> BlockCheckCoalescer:
    coalescer = getattr(app.state, "block_check_coalescer", None)
    if coalescer is None:
        coalescer = BlockCheckCoalescer()
        app.state.block_check_coalescer = coalescer
    return coalescer


def block_check_key(request: Request, ref: str | None) -> tuple[str, str, str]:
    """The coalescing key of a block check: client host, ref scope and ref."""
    host = request.client.host if request.client is not None else "local"
    value = ref or ""
    scope = value.split(":", 1)[0] if ":" in value else value
    return host, scope, value


async def check_block_coalesced(body: BlockCheckBody, request: Request) -> Any:
    """``POST /api/check/block`` with latest-wins coalescing (installed at startup)."""
    coalescer = _coalescer_for(request.app)
    key = block_check_key(request, body.ref)
    return await coalescer.check(key, lambda: proxy_check_block(body, request))


def _install_block_check_coalescing(app: Any) -> None:
    """Put the coalesced block check ahead of the plain proxy route at startup.

    P2.1 refines ``proxy.check_block`` but owns only ``runs.py``/``stream.py``,
    so the application lifespan -- the extension point P1.2 already uses for the
    unprefixed run-socket alias -- installs the route. The body contract and the
    HTTP error mapping stay those of the proxy function, which the coalesced
    endpoint calls; only the waiting and cancellation policy differs.

    FastAPI 0.159 includes routers lazily (``_IncludedRouter``), so the proxy's
    routes are not individual entries in ``app.router.routes``. A direct route is
    inserted ahead of the proxy include; older FastAPI versions, whose routes are
    flattened, get the coalesced route in place of the plain one.
    """
    _coalescer_for(app)
    routes = app.router.routes
    for index, route in enumerate(routes):
        if isinstance(route, APIRoute) and getattr(route, "path", None) == BLOCK_CHECK_PATH:
            if route.endpoint is check_block_coalesced:
                return
            routes[index] = _block_check_route(app)
            return
        if getattr(route, "original_router", None) is proxy_router:
            if any(
                isinstance(entry, APIRoute) and entry.endpoint is check_block_coalesced
                for entry in routes
            ):
                return
            routes.insert(index, _block_check_route(app))
            return


def _block_check_route(app: Any) -> APIRoute:
    return APIRoute(
        BLOCK_CHECK_PATH,
        endpoint=check_block_coalesced,
        methods=["POST"],
        name="check-block-coalesced",
        tags=["proxy"],
        dependency_overrides_provider=app,
    )


# --------------------------------------------------------------------------- data access


def _choose_signals(signals: list[dict[str, Any]], ids: str | None) -> list[int]:
    """Column indices for the ``ids`` query parameter, in request order."""
    if ids is None or not ids.strip():
        return list(range(len(signals)))
    wanted = [part.strip() for part in ids.split(",") if part.strip()]
    if not wanted:
        return list(range(len(signals)))
    lookup = {str(signal["id"]): index for index, signal in enumerate(signals)}
    missing = [name for name in wanted if name not in lookup]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown signal id {missing[0]!r}; this run records "
                + ", ".join(repr(str(signal["id"])) for signal in signals[:8])
                + (" ..." if len(signals) > 8 else "")
            ),
        )
    return [lookup[name] for name in wanted]


def _manifest_and_signals(
    run_dir: Path, state: _RunState | None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    document = state.manifest_document() if state is not None else _load_manifest(run_dir)
    signals = list(document.get("signals") or [])
    if not signals:
        raise HTTPException(
            status_code=409,
            detail=f"run {document['id']!r} has not recorded any signals yet",
        )
    return document, signals


def _read_series(
    run_dir: Path,
    document: dict[str, Any],
    signals: list[dict[str, Any]],
    chosen: list[int],
    t0: float | None = None,
    t1: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """``(time, values)`` for the chosen columns, from columns.f64 or stream.f64.

    The window is applied while reading so a zoomed request copies only its
    slice of the (possibly huge) run file.
    """
    running = document.get("status") == "running"
    columns_path = run_dir / "columns.f64"
    stream_path = run_dir / "stream.f64"

    if columns_path.is_file() and (not running or not stream_path.is_file()):
        data = open_columns(columns_path, len(signals))
        start, stop = _window(data[0], t0, t1)
        return (
            np.array(data[0, start:stop], dtype=np.float64),
            np.array(data[1:, start:stop][chosen], dtype=np.float64),
        )
    if stream_path.is_file():
        data = open_stream(stream_path, len(signals))
        start, stop = _window(data[:, 0], t0, t1)
        return (
            np.array(data[start:stop, 0], dtype=np.float64),
            np.array(data[start:stop, 1:][:, chosen].T, dtype=np.float64),
        )
    return (
        np.empty(0, dtype=np.float64),
        np.empty((len(chosen), 0), dtype=np.float64),
    )


def _window(time: np.ndarray, t0: float | None, t1: float | None) -> tuple[int, int]:
    if time.size == 0:
        return 0, 0
    lo = float(time[0]) if t0 is None else t0
    hi = float(time[-1]) if t1 is None else t1
    return (
        int(np.searchsorted(time, lo, side="left")),
        int(np.searchsorted(time, hi, side="right")),
    )


def _validate_window(t0: float | None, t1: float | None) -> None:
    if t0 is not None and not np.isfinite(t0):
        raise HTTPException(status_code=400, detail="t0 must be finite")
    if t1 is not None and not np.isfinite(t1):
        raise HTTPException(status_code=400, detail="t1 must be finite")
    if t0 is not None and t1 is not None and t1 < t0:
        raise HTTPException(status_code=400, detail=f"t1 ({t1}) must not be less than t0 ({t0})")


# --------------------------------------------------------------------------- routes


@router.post("/projects/{project}/runs", status_code=201)
async def start_run(project: str, body: RunCreateBody, request: Request) -> dict[str, str]:
    """Plan 3.7: start a run and return ``{runId}``."""
    settings: Settings = request.app.state.settings
    store = _store_for(request.app)
    project_dir = _project_dir(settings, project)
    model = _model_document(body.model)

    runs_dir = project_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    _prune_runs(project_dir, str(model["name"]), run_history_limit(), store.active_ids())

    run_dir: Path | None = None
    for _attempt in range(10):
        run_id = f"run-{datetime.now(UTC):%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
        candidate = runs_dir / run_id
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        run_dir = candidate
        break
    if run_dir is None:
        raise HTTPException(status_code=500, detail="could not allocate a unique run id")
    run_id = run_dir.name

    state = _RunState(
        run_id=run_id,
        project_dir=project_dir,
        run_dir=run_dir,
        manifest=_skeleton(model, run_id, settings),
    )
    await store.start(state)
    params = {
        "runId": run_id,
        "model": model,
        "projectDir": str(project_dir.resolve()),
        "runDir": str(run_dir.resolve()),
    }
    try:
        await _worker_call(request, "run.start", params)
    except (HTTPException, WorkerRpcFailure):
        store.forget(run_id)
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    return {"runId": run_id}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> Any:
    """Plan 3.7: the manifest, including the live state of a running run."""
    run_dir, state = _locate(request, run_id)
    if state is not None:
        return state.manifest_document()
    return _load_manifest(run_dir)


@router.delete("/runs/{run_id}")
async def cancel_run(run_id: str, request: Request) -> dict[str, bool]:
    """Plan 3.7: cancel a running simulation through ``run.cancel``."""
    _locate(request, run_id)
    result = await _worker_call(request, "run.cancel", {"runId": run_id})
    if not isinstance(result, dict) or "ok" not in result:
        raise HTTPException(
            status_code=502, detail="run.cancel returned a result without an 'ok' field"
        )
    return {"ok": bool(result["ok"])}


@router.get("/runs/{run_id}/data")
async def run_data(
    run_id: str,
    request: Request,
    ids: str | None = Query(default=None, description="Comma-separated signal ids; default all."),
    t0: Annotated[OptionalNumber, Query(description="Window start; default first sample.")] = None,
    t1: Annotated[OptionalNumber, Query(description="Window end; default last sample.")] = None,
    px: int = Query(default=DEFAULT_POINTS, ge=0, le=1_000_000, description="Pixels; 0 = raw."),
) -> Response:
    """Plan 3.7: ``u32 n_signals | u32 n_points | time | value columns``, Float64 LE."""
    _validate_window(t0, t1)
    run_dir, state = _locate(request, run_id)
    document, signals = _manifest_and_signals(run_dir, state)
    chosen = _choose_signals(signals, ids)
    time_column, values = await asyncio.to_thread(
        _read_series, run_dir, document, signals, chosen, t0, t1
    )

    result = await asyncio.to_thread(decimate, time_column, values, None, None, px)

    header = struct.pack("<II", len(chosen), result.n_points)
    columns = np.ascontiguousarray(result.values, dtype="<f8").tobytes()
    body = header + np.ascontiguousarray(result.time, dtype="<f8").tobytes() + columns
    return Response(content=body, media_type="application/octet-stream")


@router.get("/runs/{run_id}/export.csv")
async def export_csv(
    run_id: str,
    request: Request,
    ids: str | None = Query(default=None, description="Comma-separated signal ids; default all."),
) -> StreamingResponse:
    """Plan 3.7: CSV export, one column per signal, with ``t`` first."""
    run_dir, state = _locate(request, run_id)
    document, signals = _manifest_and_signals(run_dir, state)
    chosen = _choose_signals(signals, ids)
    time_column, values = await asyncio.to_thread(
        _read_series, run_dir, document, signals, chosen
    )
    header = "t," + ",".join(str(signals[index]["id"]) for index in chosen) + "\n"

    def rows() -> Iterator[bytes]:
        yield header.encode("utf-8")
        block = 8192
        for start in range(0, time_column.size, block):
            stop = min(start + block, time_column.size)
            matrix = np.column_stack((time_column[start:stop], values[:, start:stop].T))
            yield _format_csv_block(matrix).encode("utf-8")

    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.csv"'},
    )


def _format_csv_block(matrix: np.ndarray) -> str:
    """Format a ``(rows, columns)`` block with round-trip precision."""
    buffer = io.StringIO()
    np.savetxt(buffer, matrix, delimiter=",", fmt="%.17g", newline="\n")
    return buffer.getvalue()


# --------------------------------------------------------------------------- websocket


async def _safe_send(
    websocket: WebSocket,
    message: dict[str, Any],
    lock: asyncio.Lock | None = None,
) -> bool:
    """Send one JSON message; ``lock`` serialises sends from the two socket tasks."""
    try:
        if lock is None:
            await websocket.send_json(message)
        else:
            async with lock:
                await websocket.send_json(message)
    except (WebSocketDisconnect, RuntimeError):
        return False
    return True


def _error_message(text: str) -> dict[str, Any]:
    return {"method": "run.error", "params": {"message": text}}


def _done_message(document: dict[str, Any], state: _RunState | None) -> dict[str, Any]:
    if state is not None and state.done is not None:
        return {"method": "run.done", "params": state.done}
    stats = document.get("stats") or {
        "compile_s": 0.0,
        "sim_s": 0.0,
        "steps": 0,
        "events": 0,
        "states": 0,
        "equations": 0,
    }
    return {
        "method": "run.done",
        "params": {
            "runId": document["id"],
            "status": document["status"],
            "stats": stats,
            "diagnostics": document.get("diagnostics") or [],
        },
    }


def _tail_payload(
    run_dir: Path,
    signals: list[dict[str, Any]],
    ids: list[int],
    id_names: list[str],
    start_row: int,
    end_row: int | None,
) -> tuple[dict[str, Any], int] | None:
    """A decimated tail of rows ``[start_row, end_row)``, and the row it reached."""
    width = 1 + len(signals)
    stream_path = run_dir / "stream.f64"
    columns_path = run_dir / "columns.f64"
    try:
        if stream_path.is_file():
            available = int(stream_path.stat().st_size // (width * 8))
            path, is_stream = stream_path, True
        elif columns_path.is_file():
            available = int(columns_path.stat().st_size // (width * 8))
            path, is_stream = columns_path, False
        else:
            return None
        end = available if end_row is None else min(end_row, available)
        start = min(start_row, end)
        if end <= start:
            return None
        if is_stream:
            data = open_stream(path, len(signals), rows=end)
            chunk_t = np.array(data[start:end, 0], dtype=np.float64)
            chunk_v = np.array(data[start:end, 1:][:, ids].T, dtype=np.float64)
        else:
            data = open_columns(path, len(signals))
            chunk_t = np.array(data[0, start:end], dtype=np.float64)
            chunk_v = np.array(data[1:][ids, start:end], dtype=np.float64)
    except (OSError, ValueError):
        return None
    result = decimate(chunk_t, chunk_v, px=TAIL_POINTS)
    payload = {
        "runId": run_dir.name,
        "ids": id_names,
        "t0": float(result.time[0]),
        "t1": float(result.time[-1]),
        "time": result.time.tolist(),
        "values": result.values.tolist(),
    }
    return payload, end


@dataclass
class _Subscription:
    ids: list[int] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    rows_sent: int = 0
    last_tail: float = 0.0
    #: Serialises the progress-driven tail and the backlog send of a (re)subscribe,
    #: so the row cursor and the 20/s budget have one owner at a time.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


async def _serve_run_socket(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    try:
        run_dir, state = _locate(websocket, run_id)
        document = state.manifest_document() if state is not None else _load_manifest(run_dir)
        signals = list(document.get("signals") or [])
    except HTTPException as exc:
        await _safe_send(websocket, _error_message(str(exc.detail)))
        await websocket.close(code=4404)
        return

    if state is not None:
        if state.last_phase is not None:
            await _safe_send(websocket, state.last_phase)
        if state.last_progress is not None:
            await _safe_send(websocket, state.last_progress)
    if state is None and document.get("status") == "running":
        # This backend did not start the run and has no notification stream for
        # it (for example after a backend restart); no live data will arrive.
        await _safe_send(
            websocket,
            _error_message(f"run {run_id!r} is not being followed by this backend"),
        )
        await websocket.close(code=4409)
        return
    if state is None or state.done is not None:
        # The run is over (or this backend did not start it): replay what is known.
        tail = await asyncio.to_thread(
            _tail_payload,
            run_dir,
            signals,
            list(range(len(signals))),
            [str(signal["id"]) for signal in signals],
            0,
            None,
        )
        if tail is not None:
            await _safe_send(websocket, {"method": "run.tail", "params": tail[0]})
        await _safe_send(websocket, _done_message(document, state))
        await websocket.close()
        return

    assert state is not None
    queue = _store_for(websocket.app).subscribe(state)
    subscription = _Subscription()
    send_lock = asyncio.Lock()
    try:
        sender = asyncio.create_task(
            _send_loop(websocket, state, run_dir, signals, queue, subscription, send_lock),
            name=f"run-ws-send-{run_id}",
        )
        receiver = asyncio.create_task(
            _receive_loop(websocket, state, run_dir, signals, subscription, send_lock),
            name=f"run-ws-receive-{run_id}",
        )
        _done, pending = await asyncio.wait(
            {sender, receiver}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in pending:
            with suppress(asyncio.CancelledError, Exception):
                await task
    finally:
        _store_for(websocket.app).unsubscribe(state, queue)
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close()


async def _send_tail(
    websocket: WebSocket,
    run_dir: Path,
    signals: list[dict[str, Any]],
    subscription: _Subscription,
    end_row: int | None,
    *,
    throttle: bool,
    send_lock: asyncio.Lock,
) -> None:
    """Send the next decimated tail, at most 20 times per second.

    The budget is shared by the progress-driven tail and the backlog of a
    (re)subscribe, so even a client that resubscribes in a loop cannot exceed
    20 tail messages per second. The final tail at ``run.done`` is the one
    exception (``throttle=False``): it closes the run.
    """
    if not subscription.ids:
        return
    async with subscription.lock:
        now = time.monotonic()
        if throttle and now - subscription.last_tail < TAIL_MIN_INTERVAL:
            return
        ids = list(subscription.ids)
        names = list(subscription.names)
        tail = await asyncio.to_thread(
            _tail_payload,
            run_dir,
            signals,
            ids,
            names,
            subscription.rows_sent,
            end_row,
        )
        if tail is None:
            return
        payload, reached = tail
        subscription.rows_sent = reached
        # Count the message when it actually leaves; an empty read must not
        # consume part of the 20/s budget.
        subscription.last_tail = time.monotonic()
        await _safe_send(
            websocket, {"method": "run.tail", "params": payload}, send_lock
        )


async def _send_loop(
    websocket: WebSocket,
    state: _RunState,
    run_dir: Path,
    signals: list[dict[str, Any]],
    queue: asyncio.Queue,
    subscription: _Subscription,
    send_lock: asyncio.Lock,
) -> None:
    while True:
        message = await queue.get()
        method = message.get("method")
        if method == "run.done":
            # The final tail reads to the end of the file, not just the last
            # progress row: the last notification may lag the last flush. It
            # goes out before run.done so a client may stop at run.done.
            await _send_tail(
                websocket,
                run_dir,
                signals,
                subscription,
                None,
                throttle=False,
                send_lock=send_lock,
            )
            await _safe_send(websocket, message, send_lock)
            return
        if not await _safe_send(websocket, message, send_lock):
            return
        if method == "run.progress":
            await _send_tail(
                websocket,
                run_dir,
                signals,
                subscription,
                state.rows,
                throttle=True,
                send_lock=send_lock,
            )


async def _receive_loop(
    websocket: WebSocket,
    state: _RunState,
    run_dir: Path,
    signals: list[dict[str, Any]],
    subscription: _Subscription,
    send_lock: asyncio.Lock,
) -> None:
    while True:
        try:
            message = await websocket.receive_json()
        except (WebSocketDisconnect, RuntimeError):
            return
        if not isinstance(message, dict) or "subscribe" not in message:
            continue
        wanted = message["subscribe"]
        if not isinstance(wanted, list) or not all(isinstance(name, str) for name in wanted):
            await _safe_send(websocket, _error_message("subscribe must be a list of signal ids"))
            continue
        lookup = {str(signal["id"]): index for index, signal in enumerate(signals)}
        missing = [name for name in wanted if name not in lookup]
        if missing:
            await _safe_send(websocket, _error_message(f"unknown signal id {missing[0]!r}"))
            continue
        # A (re)subscription starts with the history so far, then follows the
        # live tail. Reset the cursor and send that backlog now, not on the next
        # progress notification (the run may be paused between progress events).
        # ``last_tail`` is kept so a resubscribe loop cannot exceed the 20/s cap.
        async with subscription.lock:
            subscription.ids = [lookup[name] for name in wanted]
            subscription.names = list(wanted)
            subscription.rows_sent = 0
        await _send_tail(
            websocket,
            run_dir,
            signals,
            subscription,
            state.rows,
            throttle=True,
            send_lock=send_lock,
        )


@router.websocket("/ws/runs/{run_id}")
async def run_socket(websocket: WebSocket, run_id: str) -> None:
    """Plan 3.7: run phases, progress, done and subscribed live tails."""
    await _serve_run_socket(websocket, run_id)


# app.py includes this router under /api, so the plan's /ws/runs/{id} path needs
# an alias outside that prefix. The router's lifespan adds it to the app once,
# before the app starts serving, without touching app.py. The same lifespan swaps
# the plain /api/check/block proxy route for the coalesced one (P2.1).
async def _run_socket_alias(websocket: WebSocket) -> None:
    await _serve_run_socket(websocket, str(websocket.path_params["run_id"]))


@asynccontextmanager
async def _router_lifespan(app: Any) -> AsyncIterator[None]:
    _install_block_check_coalescing(app)
    alias = "/ws/runs/{run_id}"
    if not any(getattr(route, "path", None) == alias for route in app.router.routes):
        app.router.routes.append(
            WebSocketRoute(alias, endpoint=_run_socket_alias, name="run-socket-alias")
        )
    try:
        yield
    finally:
        coalescer = getattr(app.state, "block_check_coalescer", None)
        if coalescer is not None:
            await coalescer.aclose()
        store = getattr(app.state, "run_store", None)
        if store is not None:
            await store.aclose()


# ``router`` is created at the top (the route decorators need it); the lifespan
# is attached here, after its definition, and read by ``include_router``.
router.lifespan_context = _router_lifespan
