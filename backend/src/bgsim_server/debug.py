"""The debug endpoints of plan 3.8 (WP P4.1).

``PUT /api/runs/{id}/breakpoints``
    ``debug.setBreakpoints`` with the full set; answers ``{breakpoints: [BreakpointStatus]}``.
``POST /api/runs/{id}/debug/{command}``
    ``pause | continue | step | runTo | setParameter | setState``. The body is the method's
    params without ``runId`` (the backend injects it) and is validated with the generated
    models (422). An unknown command or run is 404.
``POST /api/runs/{id}/evaluate``, ``GET /api/runs/{id}/values?ids=a,b``
    ``debug.evaluate`` and ``debug.values``.
``POST /api/runs/{id}/replay``, ``POST /api/runs/{id}/branch`` (``{t}``)
    Create the new run exactly like ``POST /api/projects/{p}/runs`` does (a new run id and
    folder in the same project and history, registered with the run store so
    ``/ws/runs/{newId}``, ``/data`` and cancel work), call ``run.replay`` / ``run.branch``
    and answer ``{runId}`` (201). The new run's manifest records ``parentRun`` (and
    ``branchAt`` for a branch).
``POST /api/check/explain``
    ``model.explain`` (``projectDir`` is resolved like ``/api/check/model`` does).

Error mapping: a worker error on a debug call (for example ``"run is not paused"``) is
HTTP **409** with ``{"detail": message, "message": message, "diagnostics": [...]}``, never
500. Starting a replay or branch maps worker errors like ``run.start`` (422). The
``debug.paused`` / ``debug.resumed`` notifications ride the run WebSocket (``runs.py``).
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import runs
from .config import Settings
from .contracts import (
    Breakpoint,
    DebugContinueParams,
    DebugEditResult,
    DebugPauseParams,
    DebugRunToParams,
    DebugSetBreakpointsResult,
    DebugSetParameterParams,
    DebugSetStateParams,
    DebugStepParams,
    EvaluateResult,
    ExplainResult,
    Model,
    OkResult,
    RunBranchParams,
    RunReplayParams,
    ValuesResult,
)
from .proxy import _call_worker, _project_dir, _project_name, _validated
from .worker import (
    WorkerError,
    WorkerNotReady,
    WorkerRpcError,
    WorkerSupervisor,
    WorkerTimeout,
)

router = APIRouter()


class DebugConflict(Exception):
    """A worker error on a debug call; rendered as HTTP 409 by the handler in ``app.py``."""

    def __init__(self, message: str, diagnostics: list[Any]):
        super().__init__(message)
        self.message = message
        self.diagnostics = list(diagnostics)


#: command -> (worker method, params model, result model)
COMMANDS: dict[str, tuple[str, type[BaseModel], type[BaseModel]]] = {
    "pause": ("debug.pause", DebugPauseParams, OkResult),
    "continue": ("debug.continue", DebugContinueParams, OkResult),
    "step": ("debug.step", DebugStepParams, OkResult),
    "runTo": ("debug.runTo", DebugRunToParams, OkResult),
    "setParameter": ("debug.setParameter", DebugSetParameterParams, DebugEditResult),
    "setState": ("debug.setState", DebugSetStateParams, DebugEditResult),
}


class BreakpointsBody(BaseModel):
    """``PUT /api/runs/{id}/breakpoints`` body: always the full set."""

    model_config = ConfigDict(extra="forbid")

    breakpoints: list[Breakpoint]


class EvaluateBody(BaseModel):
    """``POST /api/runs/{id}/evaluate`` body."""

    model_config = ConfigDict(extra="forbid")

    expr: str
    context: str | None = None


class BranchBody(BaseModel):
    """``POST /api/runs/{id}/branch`` body: the time at which the branch diverges."""

    model_config = ConfigDict(extra="forbid")

    t: float = Field(allow_inf_nan=False)


class ExplainBody(BaseModel):
    """``POST /api/check/explain`` body; ``projectDir`` defaults like ``/api/check/model``."""

    model_config = ConfigDict(extra="forbid")

    model: Model
    projectDir: str | None = None
    signal: str


# --------------------------------------------------------------------------- helpers


async def _debug_call(request: Request, method: str, params: dict[str, Any]) -> Any:
    """One debug request: worker errors become 409 (a state conflict), not 500."""
    supervisor: WorkerSupervisor = request.app.state.worker
    try:
        return await supervisor.call(method, params)
    except WorkerTimeout as exc:
        raise HTTPException(status_code=504, detail=f"{method} timed out: {exc}") from exc
    except WorkerRpcError as exc:
        raise DebugConflict(str(exc), exc.diagnostics) from exc
    except WorkerNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except WorkerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _validate_params(schema: type[BaseModel], params: dict[str, Any]) -> dict[str, Any]:
    """Validate params with the generated model; 422 with the field errors otherwise."""
    try:
        schema.model_validate(params)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=json.loads(exc.json(include_url=False))) from exc
    return params


def _dump(model: BaseModel) -> dict[str, Any]:
    return runs._strip_comments(model.model_dump(by_alias=True, mode="json"))


# --------------------------------------------------------------------------- routes


@router.put("/runs/{run_id}/breakpoints")
async def set_breakpoints(run_id: str, body: BreakpointsBody, request: Request) -> Any:
    """Plan 3.8: replace the full breakpoint set; answers the status of every breakpoint."""
    runs._locate(request, run_id)
    params = {
        "runId": run_id,
        "breakpoints": [_dump(breakpoint_) for breakpoint_ in body.breakpoints],
    }
    result = await _debug_call(request, "debug.setBreakpoints", params)
    return _validated(DebugSetBreakpointsResult, result, "debug.setBreakpoints")


@router.post("/runs/{run_id}/debug/{command}")
async def debug_command(
    run_id: str,
    command: str,
    request: Request,
    body: Annotated[dict[str, Any] | None, Body()] = None,
) -> Any:
    """Plan 3.8: ``pause | continue | step | runTo | setParameter | setState``."""
    entry = COMMANDS.get(command)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown debug command {command!r}; use " + ", ".join(COMMANDS),
        )
    method, params_model, result_model = entry
    runs._locate(request, run_id)
    params = _validate_params(params_model, {**(body or {}), "runId": run_id})
    result = await _debug_call(request, method, params)
    return _validated(result_model, result, method)


@router.post("/runs/{run_id}/evaluate")
async def evaluate(run_id: str, body: EvaluateBody, request: Request) -> Any:
    """Plan 3.8: evaluate an expression at the pause (read-only)."""
    runs._locate(request, run_id)
    params = {"runId": run_id, "expr": body.expr, "context": body.context}
    result = await _debug_call(request, "debug.evaluate", params)
    return _validated(EvaluateResult, result, "debug.evaluate")


@router.get("/runs/{run_id}/values")
async def values(
    run_id: str,
    request: Request,
    ids: str = Query(description="Comma-separated signal ids."),
) -> Any:
    """Plan 3.8: the values of signals at the pause."""
    runs._locate(request, run_id)
    wanted = [part.strip() for part in ids.split(",") if part.strip()]
    if not wanted:
        raise HTTPException(status_code=422, detail="ids must name at least one signal")
    result = await _debug_call(request, "debug.values", {"runId": run_id, "ids": wanted})
    return _validated(ValuesResult, result, "debug.values")


async def _derive_run(
    request: Request, parent_id: str, method: str, branch_at: float | None
) -> dict[str, str]:
    """Create the replay/branch run of ``parent_id`` and start it; ``{runId}``."""
    parent_dir, parent_state = runs._locate(request, parent_id)
    parent = parent_state.manifest_document() if parent_state else runs._load_manifest(parent_dir)
    project_dir = parent_dir.parent.parent
    store = runs._store_for(request.app)

    runs_dir = project_dir / "runs"
    runs._prune_runs(
        project_dir,
        str(parent["model"]),
        runs.run_history_limit(),
        store.active_ids() | {parent_id},
    )
    run_dir = runs.allocate_run_dir(runs_dir)
    run_id = run_dir.name

    edits = list((parent.get("debug") or {}).get("edits") or [])
    if branch_at is not None:
        edits = [edit for edit in edits if edit["t"] < branch_at]
    t0 = float(parent["time"]["t0"])
    skeleton = {
        "id": run_id,
        "model": parent["model"],
        "modelHash": parent["modelHash"],
        "created": runs._utc_now(),
        "status": "running",
        "settings": parent["settings"],
        "signals": parent["signals"],
        "time": {"n": 0, "t0": t0, "t1": t0},
        "diagnostics": [],
        "layout": "columnar-f64-v1",
        "debug": {"breakpoints": [], "edits": edits, "pauses": []},
        "parentRun": parent_id,
    }
    params: dict[str, Any] = {
        "runId": parent_id,
        "newRunId": run_id,
        "runDir": str(run_dir.resolve()),
    }
    if branch_at is not None:
        skeleton["branchAt"] = branch_at
        params["t"] = branch_at
    _validate_params(RunBranchParams if branch_at is not None else RunReplayParams, params)
    await runs.begin_run(request, project_dir, run_dir, skeleton, method, params)
    return {"runId": run_id}


@router.post("/runs/{run_id}/replay", status_code=201)
async def replay_run(run_id: str, request: Request) -> dict[str, str]:
    """Plan 3.8: a normal run that applies the parent's edits (``run.replay``)."""
    return await _derive_run(request, run_id, "run.replay", None)


@router.post("/runs/{run_id}/branch", status_code=201)
async def branch_run(run_id: str, body: BranchBody, request: Request) -> dict[str, str]:
    """Plan 3.8: a debug run that replays the parent up to ``t`` and pauses (``run.branch``)."""
    return await _derive_run(request, run_id, "run.branch", body.t)


@router.post("/check/explain")
async def check_explain(
    body: ExplainBody,
    request: Request,
    project: str | None = Query(
        default=None,
        description="Project name used to derive projectDir when the body omits it.",
    ),
) -> Any:
    """Plan 3.8: ``model.explain`` for one signal; needs no run."""
    settings: Settings = request.app.state.settings
    project_dir = body.projectDir
    if project_dir is None:
        name = _project_name(project)
        project_dir = (
            str(_project_dir(settings, name)) if name is not None else str(settings.repo_root)
        )
    params = {
        "model": runs._model_document(body.model),
        "projectDir": project_dir,
        "signal": body.signal,
    }
    result = await _call_worker(request, "model.explain", params)
    return _validated(ExplainResult, result, "model.explain")
