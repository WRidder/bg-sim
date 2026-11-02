"""C/FMU export jobs over HTTP (plan/EXPORT_PLAN.md P-EX1 second half, W-EX1).

Routes (``app.py`` includes the router under ``/api``):

* ``POST /api/projects/{p}/models/{m}/export`` with an ``ExportRequest`` body starts a job
  and answers ``201 {"exportId"}``;
* ``GET /api/exports?project={p}[&model={m}]`` lists the project's jobs as a JSON array of
  ``ExportJob`` documents, newest first (the web app's background tasks indicator reads it on
  load, so a running or finished export survives closing the dialog and reloading the page);
* ``GET /api/exports/{id}`` is the ``ExportJob`` document: status, phase, timings,
  diagnostics and, once done, the report (``ExportReport``) and the FMU's name and size;
* ``GET /api/exports/{id}/fmu`` downloads the FMU;
* ``DELETE /api/exports/{id}`` cancels a queued or running job.

A job lives in ``<project>/exports/<id>/``: ``request.json``, ``job.json`` (the status
document, rewritten on every change), ``export.log`` and ``export/`` (the sources, the model
description, ``export.json`` with the build results and ``<identifier>.fmu``). The last
:data:`EXPORT_HISTORY` jobs of each model are kept.

An export can take minutes (compile, spectrum scan, symbolic Jacobian, gcc), so it never
runs inside the interactive worker, whose supervisor pings it every 5 s. Each job starts a
Julia process of its own (``julia/BGSim/export/export_job.jl``, ``BGSim.Export.export_job``),
which reports its phase on stdout; the backend then builds the FMU with
:mod:`bgsim_server.fmu_build` in a thread. One job runs at a time; later ones wait as
``queued``. With ``BGSIM_FAKE_WORKER`` the :class:`~bgsim_server.fake_export.FakeExportRunner`
answers instead (no Julia, no compiler); there, and only there, an ``X-BGSim-Fake-Export-S``
request header on the POST sets that job's phase duration, so an end-to-end test can hold a
job in ``running`` long enough to close the dialog, reload the page and cancel it.

Environment: ``BGSIM_EXPORT_REF_BUDGET`` (seconds for the reference run, default 120) and
``BGSIM_EXPORT_TIMEOUT`` (seconds for the Julia process, default 3600).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from . import fmu_build
from .config import Settings
from .contracts import ExportRequest
from .fake_export import FakeExportRunner

router = APIRouter()

#: Export jobs kept per model.
EXPORT_HISTORY = 10

_EXPORT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PROJECT_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_MODEL_NAME = re.compile(r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$")
_PHASE_LINE = "@@bgsim "
_TERMINAL = frozenset({"done", "refused", "failed", "cancelled"})
#: The fake runner's per-job phase duration (``BGSIM_FAKE_WORKER`` only; see the docstring).
FAKE_DELAY_HEADER = "x-bgsim-fake-export-s"


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _env_seconds(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


class ExportRunner(Protocol):
    """The two halves of a job: the Julia export, then the FMU build."""

    async def export(self, job_dir: Path, request: dict[str, Any],
                     on_phase: Callable[[str], None]) -> dict[str, Any]: ...

    async def build(self, export_dir: Path) -> dict[str, Any]: ...


def _kill_tree(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], check=False, capture_output=True)
    else:
        with suppress(ProcessLookupError):
            process.kill()


class JuliaExportRunner:
    """One Julia process per job, then :func:`fmu_build.build_fmu` in a thread."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.script = settings.julia_project / "export" / "export_job.jl"
        self.runtime = settings.julia_project / "export" / "runtime"

    async def export(self, job_dir: Path, request: dict[str, Any],
                     on_phase: Callable[[str], None]) -> dict[str, Any]:
        argv = [self.settings.julia, f"--project={self.settings.julia_project}",
                str(self.script), str(job_dir)]
        started = time.monotonic()
        timings: dict[str, float] = {}
        with (job_dir / "export.log").open("ab") as log:
            log.write(f"=== {_utc_now()} {' '.join(argv)}\n".encode())
            log.flush()
            process = await asyncio.create_subprocess_exec(
                *argv, cwd=str(self.settings.repo_root), stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                limit=1 << 20)
            try:
                async with asyncio.timeout(_env_seconds("BGSIM_EXPORT_TIMEOUT", 3600.0)):
                    assert process.stdout is not None
                    async for raw in process.stdout:
                        log.write(raw)
                        log.flush()
                        line = raw.decode("utf-8", "replace").strip()
                        if not line.startswith(_PHASE_LINE):
                            continue
                        with suppress(ValueError):
                            phase = json.loads(line[len(_PHASE_LINE):]).get("phase")
                            if phase == "loaded":
                                timings["juliaS"] = time.monotonic() - started
                            elif phase in ("scope", "flatten", "reference", "export"):
                                on_phase(phase)
                    await process.wait()
            except TimeoutError:
                _kill_tree(process)
                await process.wait()
                return {"status": "failed", "diagnostics": [], "timings": timings, "notes": [],
                        "error": "the export did not finish within BGSIM_EXPORT_TIMEOUT"}
            finally:
                # A cancelled job (DELETE) lands here with CancelledError: stop Julia too.
                _kill_tree(process)
        result_path = job_dir / "result.json"
        if not result_path.is_file():
            tail = (job_dir / "export.log").read_text(encoding="utf-8", errors="replace")
            return {"status": "failed", "diagnostics": [], "timings": timings, "notes": [],
                    "error": "the Julia export process ended without a result "
                             f"(exit code {process.returncode}):\n" + tail[-3000:]}
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result.setdefault("timings", {}).update(timings)
        result["timings"].pop("loadS", None)
        return result

    async def build(self, export_dir: Path) -> dict[str, Any]:
        report = json.loads((export_dir / "export.json").read_text(encoding="utf-8"))
        steps = fmu_build.harness_steps_for(report.get("substeps") or 1)
        result = await asyncio.to_thread(
            fmu_build.build_fmu, export_dir, runtime_dir=self.runtime, harness_steps=steps)
        return {"fmu": result.fmu, "error": result.error}


@dataclass
class _Job:
    id: str
    project: str
    model: str
    scope: str | None
    job_dir: Path
    created: str
    status: str = "queued"
    phase: str | None = None
    finished: str | None = None
    timings: dict[str, float] = field(default_factory=dict)
    error: str | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    report: dict[str, Any] | None = None
    fmu: dict[str, Any] | None = None
    task: asyncio.Task | None = None

    def document(self) -> dict[str, Any]:
        """The ``ExportJob`` contract."""
        return {
            "id": self.id, "project": self.project, "model": self.model, "scope": self.scope,
            "status": self.status, "phase": self.phase, "created": self.created,
            "finished": self.finished, "timings": self.timings, "error": self.error,
            "diagnostics": self.diagnostics, "notes": self.notes, "report": self.report,
            "fmu": self.fmu,
        }

    def save(self) -> None:
        path = self.job_dir / "job.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.document(), indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def set_phase(self, phase: str | None) -> None:
        self.phase = phase
        self.save()

    def end(self, status: str, error: str | None = None) -> None:
        self.status = status
        self.phase = None
        self.error = error
        self.finished = _utc_now()
        self.save()


def _first_error(diagnostics: list[dict[str, Any]]) -> str | None:
    for d in diagnostics:
        if d.get("severity") == "error":
            return str(d.get("message"))
    return None


class ExportStore:
    """The jobs this process started, the runner and the one-at-a-time slot."""

    def __init__(self, settings: Settings, runner: ExportRunner | None = None):
        self.settings = settings
        self.runner = runner or (FakeExportRunner(settings) if settings.fake_worker
                                 else JuliaExportRunner(settings))
        self.jobs: dict[str, _Job] = {}
        self.slot = asyncio.Semaphore(1)

    def start(self, job: _Job, request: dict[str, Any]) -> None:
        self.jobs[job.id] = job
        job.save()
        job.task = asyncio.create_task(self._run(job, request), name=f"export-{job.id}")

    async def _run(self, job: _Job, request: dict[str, Any]) -> None:
        started = time.monotonic()
        try:
            async with self.slot:
                job.status = "running"
                job.set_phase("starting")
                result = await self.runner.export(job.job_dir, request, job.set_phase)
                job.timings.update(result.get("timings") or {})
                job.notes = list(result.get("notes") or [])
                job.diagnostics = list(result.get("diagnostics") or [])
                status = result.get("status")
                if status == "refused":
                    job.timings["totalS"] = time.monotonic() - started
                    job.end("refused", _first_error(job.diagnostics)
                            or "the model cannot be exported")
                    return
                if status != "exported":
                    job.timings["totalS"] = time.monotonic() - started
                    job.end("failed", str(result.get("error") or "the export failed"))
                    return
                job.set_phase("build")
                export_dir = job.job_dir / "export"
                t0 = time.monotonic()
                build = await self.runner.build(export_dir)
                job.timings["buildS"] = time.monotonic() - t0
                job.timings["totalS"] = time.monotonic() - started
                report_path = export_dir / "export.json"
                job.report = json.loads(report_path.read_text(encoding="utf-8"))
                job.diagnostics = list(job.report.get("diagnostics") or [])
                fmu: Path | None = build.get("fmu")
                if fmu is None:
                    job.end("failed", "building the FMU failed: " + str(build.get("error")))
                    return
                b = job.report.get("build") or {}
                source_only = bool(b.get("sourceOnly"))
                if source_only and b.get("note"):
                    job.notes.append("Source-only FMU: " + str(b["note"]) + ".")
                job.fmu = {"file": fmu.name, "bytes": fmu.stat().st_size,
                           "sourceOnly": source_only}
                job.end("done")
        except asyncio.CancelledError:
            job.timings["totalS"] = time.monotonic() - started
            job.end("cancelled", "the export was cancelled")
            raise
        except Exception as exc:  # noqa: BLE001 - an internal error must end the job, not hang it
            job.timings["totalS"] = time.monotonic() - started
            job.end("failed", f"the export failed: {exc}")
        finally:
            job.task = None

    async def cancel(self, job: _Job) -> bool:
        task = job.task
        if task is None or job.status in _TERMINAL:
            return False
        task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task
        return True

    async def aclose(self) -> None:
        for job in list(self.jobs.values()):
            await self.cancel(job)


def _store_for(app: Any) -> ExportStore:
    store = getattr(app.state, "export_store", None)
    if store is None:
        store = ExportStore(app.state.settings, getattr(app.state, "export_runner", None))
        app.state.export_store = store
    return store


def _project_dir(settings: Settings, project: str) -> Path:
    if project in {".", ".."} or not _PROJECT_NAME.fullmatch(project):
        raise HTTPException(status_code=404, detail=f"unknown project {project!r}")
    root = settings.projects_root.resolve()
    directory = (root / project).resolve()
    if not directory.is_relative_to(root) or not directory.is_dir():
        raise HTTPException(status_code=404, detail=f"unknown project {project!r}")
    return directory


def _allocate(exports_dir: Path) -> Path:
    for _attempt in range(10):
        candidate = exports_dir / f"export-{datetime.now(UTC):%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
        try:
            candidate.mkdir(parents=True)
        except FileExistsError:
            continue
        return candidate
    raise HTTPException(status_code=500, detail="could not allocate a unique export id")


def _prune(exports_dir: Path, model: str, keep: int, active: set[str]) -> None:
    """Delete the oldest finished jobs of ``model`` beyond ``keep - 1`` (the new one is last)."""
    entries = []
    for candidate in exports_dir.iterdir():
        path = candidate / "job.json"
        if candidate.name in active or not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if doc.get("model") == model and doc.get("status") in _TERMINAL:
            entries.append((str(doc.get("created") or ""), candidate.name, candidate))
    entries.sort(reverse=True)
    for _, _, directory in entries[max(keep - 1, 0):]:
        shutil.rmtree(directory, ignore_errors=True)


def _strip_comments(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_comments(v) for k, v in value.items() if k != "$comment"}
    if isinstance(value, list):
        return [_strip_comments(v) for v in value]
    return value


def _locate(request: Request, export_id: str) -> tuple[Path, _Job | None]:
    if not _EXPORT_ID.fullmatch(export_id) or ".." in export_id:
        raise HTTPException(status_code=404, detail=f"unknown export {export_id!r}")
    store = _store_for(request.app)
    job = store.jobs.get(export_id)
    if job is not None:
        return job.job_dir, job
    root: Path = request.app.state.settings.projects_root
    if root.is_dir():
        for project in sorted(root.iterdir()):
            candidate = project / "exports" / export_id
            if (candidate / "job.json").is_file():
                return candidate, None
    raise HTTPException(status_code=404, detail=f"unknown export {export_id!r}")


def _job_document(job_dir: Path, job: _Job | None) -> dict[str, Any]:
    if job is not None:
        return job.document()
    doc = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    if doc.get("status") not in _TERMINAL:
        # A job of an earlier backend process that never finished.
        doc.update(status="failed", phase=None, error="the backend stopped during the export")
    return doc


@router.post("/projects/{project}/models/{model:path}/export", status_code=201)
async def start_export(project: str, model: str, body: ExportRequest,
                       request: Request) -> dict[str, str]:
    """Start an export job of ``body.model`` (optionally scoped to a subsystem)."""
    settings: Settings = request.app.state.settings
    if not _MODEL_NAME.fullmatch(model) or ".." in model:
        raise HTTPException(status_code=404, detail=f"unknown model {model!r}")
    project_dir = _project_dir(settings, project)
    store = _store_for(request.app)
    exports_dir = project_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    active = {job_id for job_id, job in store.jobs.items() if job.status not in _TERMINAL}
    _prune(exports_dir, model, EXPORT_HISTORY, active)
    job_dir = _allocate(exports_dir)
    document = _strip_comments(body.model_dump(by_alias=True, mode="json"))
    document["projectDir"] = str(project_dir)
    document["referenceBudgetS"] = _env_seconds("BGSIM_EXPORT_REF_BUDGET", 120.0)
    fake_delay = request.headers.get(FAKE_DELAY_HEADER)
    if settings.fake_worker and fake_delay is not None:
        with suppress(ValueError):
            document["fakeDelayS"] = max(0.0, min(float(fake_delay), 60.0))
    (job_dir / "request.json").write_text(json.dumps(document, indent=2), encoding="utf-8")
    job = _Job(id=job_dir.name, project=project, model=model, scope=body.scope or None,
               job_dir=job_dir, created=_utc_now())
    store.start(job, document)
    return {"exportId": job.id}


@router.get("/exports")
async def list_exports(project: str, request: Request,
                       model: str | None = None) -> list[dict[str, Any]]:
    """The ``ExportJob`` documents of ``project`` (optionally one model), newest first."""
    project_dir = _project_dir(request.app.state.settings, project)
    store = _store_for(request.app)
    exports_dir = project_dir / "exports"
    entries: list[tuple[str, int, dict[str, Any]]] = []
    if exports_dir.is_dir():
        for candidate in exports_dir.iterdir():
            if not (candidate / "job.json").is_file() or not _EXPORT_ID.fullmatch(candidate.name):
                continue
            job = store.jobs.get(candidate.name)
            try:
                doc = _job_document(candidate, job)
                # ``created`` has whole seconds; the request's write time orders a burst.
                written = (candidate / "request.json").stat().st_mtime_ns
            except (OSError, ValueError):
                continue  # a job.json being replaced or damaged: the next poll sees it
            if model is None or doc.get("model") == model:
                entries.append((str(doc.get("created") or ""), written, doc))
    entries.sort(key=lambda entry: entry[:2], reverse=True)
    return [doc for _, _, doc in entries]


@router.get("/exports/{export_id}")
async def get_export(export_id: str, request: Request) -> dict[str, Any]:
    """The ``ExportJob`` document."""
    job_dir, job = _locate(request, export_id)
    return _job_document(job_dir, job)


@router.delete("/exports/{export_id}")
async def cancel_export(export_id: str, request: Request) -> dict[str, bool]:
    """Cancel a queued or running export; ``ok`` is false when it had already ended."""
    _, job = _locate(request, export_id)
    if job is None:
        return {"ok": False}
    return {"ok": await _store_for(request.app).cancel(job)}


@router.get("/exports/{export_id}/fmu")
async def download_fmu(export_id: str, request: Request) -> FileResponse:
    """The FMU of a finished export."""
    job_dir, job = _locate(request, export_id)
    doc = _job_document(job_dir, job)
    fmu = doc.get("fmu") or {}
    name = fmu.get("file")
    path = job_dir / "export" / str(name) if name else None
    if doc.get("status") != "done" or path is None or not path.is_file():
        raise HTTPException(status_code=404, detail=f"export {export_id!r} has no FMU")
    return FileResponse(path, media_type="application/octet-stream", filename=str(name))


@asynccontextmanager
async def _router_lifespan(app: Any) -> AsyncIterator[None]:
    try:
        yield
    finally:
        store = getattr(app.state, "export_store", None)
        if store is not None:
            await store.aclose()


router.lifespan_context = _router_lifespan
