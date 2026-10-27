"""The real Julia worker (plan 3.6, WP J1.6): marked `julia`, deselected by default.

Run with:  uv run --directory backend pytest -q -m julia -s

The module starts one real worker (about 20 s cold, including the start-up warm-up) and then
exercises the plan 3.6 methods over the real socket: `ping`, `catalog.get`, `block.check`,
`model.check` and a `run.start` that writes a running manifest (REQ-1), streams notifications
and ends with a final manifest plus `columns.f64`. These are the acceptance tests of J1.6.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import numpy as np
import pytest
import pytest_asyncio

from bgsim_server.config import Settings, default_julia
from bgsim_server.worker import WorkerRpcError, WorkerSupervisor

pytestmark = pytest.mark.julia

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "contracts" / "fixtures"
MODEL_FIXTURE = FIXTURES / "model" / "valid" / "model.dcmotor.json"
CATALOG_FIXTURE = FIXTURES / "catalog" / "valid" / "catalog.min.json"
STDLIB = REPO / "julia" / "BGSim" / "stdlib"

COLD_START_TIMEOUT = 600.0  # a cold `using BGSim` may recompile the package first
COLD_START_TARGET = 60.0  # plan 5.12
BLOCK_CHECK_TARGET = 0.150  # plan 5.12, warm


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def julia_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """One isolated settings object for the whole module (one worker, one log)."""
    root = tmp_path_factory.mktemp("julia-worker")
    return Settings(
        repo_root=REPO,
        projects_root=root / "projects",
        julia=default_julia(),
        fake_worker=False,
        worker_log=root / "logs" / "worker.log",
        web_dist=root / "web-dist",
    )


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def worker(julia_settings: Settings):
    """Start the real worker once; yield `(supervisor, cold_start_seconds)`."""
    supervisor = WorkerSupervisor(julia_settings)
    started = time.perf_counter()
    await supervisor.start()
    try:
        await supervisor.wait_ready(timeout=COLD_START_TIMEOUT)
        yield supervisor, time.perf_counter() - started
    finally:
        await supervisor.stop()


@pytest.mark.asyncio(loop_scope="module")
async def test_ping_catalog_and_protocol_edges(worker, schema_validate) -> None:
    supervisor, cold_start = worker
    print(f"\njulia cold start to ready: {cold_start:.2f} s")
    assert cold_start < COLD_START_TARGET

    result = await supervisor.call("ping")
    assert result["version"] == "0.1.0"
    assert result["julia"].startswith("1.13")
    assert result["warm"] is True

    catalog = await supervisor.call("catalog.get", {"projectLibraryDir": None})
    schema_validate("catalog", catalog)
    expected = _load(CATALOG_FIXTURE)
    expected_refs = {block["ref"] for block in expected["blocks"]}
    actual_refs = {block["ref"] for block in catalog["blocks"]}
    assert expected_refs <= actual_refs, sorted(expected_refs - actual_refs)
    assert len(catalog["blocks"]) >= len(expected["blocks"])
    assert catalog["language"] == "0.1.0"

    # A broken project block is reported, not raised: `catalog.get` still answers.
    empty = supervisor.settings.projects_root / "no-library"
    library = await supervisor.call("catalog.get", {"projectLibraryDir": str(empty)})
    assert {b["ref"] for b in library["blocks"]} >= expected_refs

    with pytest.raises(WorkerRpcError) as info:
        await supervisor.call("no.such.method")
    assert "not implemented" in str(info.value)
    assert info.value.diagnostics == []

    # A binary frame is not protocol; the worker logs it and keeps serving.
    await supervisor.send_binary(b"\x00\x01\x02")
    assert (await supervisor.call("ping"))["warm"] is True

    log = supervisor.settings.worker_log_path.read_text(encoding="utf-8", errors="replace")
    assert "[BGSim.Worker] connected; serving frames" in log
    assert "rejecting binary frame" in log


@pytest.mark.asyncio(loop_scope="module")
async def test_block_check(worker) -> None:
    supervisor, _ = worker
    source = (STDLIB / "converters" / "DCMotor.jl").read_text(encoding="utf-8")

    checked = await supervisor.call("block.check", {"source": source, "ref": "inline:DCMotor"})
    assert checked["diagnostics"] == []
    interface = checked["interface"]
    assert interface is not None
    assert {port["name"] for port in interface["ports"]} == {"p", "n", "shaft", "housing"}

    timings = []
    for _ in range(5):
        started = time.perf_counter()
        assert (
            await supervisor.call("block.check", {"source": source, "ref": "inline:DCMotor"})
        )["diagnostics"] == []
        timings.append(time.perf_counter() - started)
    timings.sort()
    median = timings[len(timings) // 2]
    print(f"block.check warm median: {median * 1000:.2f} ms")
    assert median < BLOCK_CHECK_TARGET

    broken = source.replace("connect(p, resistor.p)", "connect(p, resistor.p, extra)")
    failed = await supervisor.call("block.check", {"source": broken, "ref": "inline:DCMotor"})
    assert any(d["code"] == "E001" for d in failed["diagnostics"])
    first = failed["diagnostics"][0]
    assert first["source"]["ref"] == "inline:DCMotor"
    assert first["source"]["range"]["line"] >= 1
    assert first["hint"]


@pytest.mark.asyncio(loop_scope="module")
async def test_model_check(worker, schema_validate) -> None:
    supervisor, _ = worker
    model = _load(MODEL_FIXTURE)
    started = time.perf_counter()
    result = await supervisor.call("model.check", {"model": model, "projectDir": None})
    elapsed = time.perf_counter() - started
    print(f"model.check DC motor: {elapsed * 1000:.0f} ms, {len(result['signals'])} signals")
    assert elapsed < 1.5

    errors = [d for d in result["diagnostics"] if d["severity"] == "error"]
    assert errors == [], errors
    assert result["stats"]["states"] == 3
    assert result["stats"]["equations"] == 41
    assert len(result["signals"]) == 73
    ids = [signal["id"] for signal in result["signals"]]
    assert len(ids) == len(set(ids))
    assert "Motor1/shaft.f" in ids
    assert "Motor1/i" in ids
    assert "Motor1/p.P" in ids  # every power port also reports its power e*f (D15)
    # `domains` has one entry per power connection (the signal connection c1 has none); the
    # composite's five internal wires add their own entries (J2.6b).
    assert len(result["domains"]) == 11
    assert result["domains"]["c2"] == "Electrical"
    assert result["domains"]["c5"] == "Rotation"
    assert set(result["domains"].values()) == {"Electrical", "Rotation"}
    for diagnostic in result["diagnostics"]:
        schema_validate("diagnostic", diagnostic)

    incomplete = _load(MODEL_FIXTURE)
    incomplete["diagram"]["connections"] = incomplete["diagram"]["connections"][:-1]
    failed = await supervisor.call("model.check", {"model": incomplete, "projectDir": None})
    assert any(d["code"] == "E101" for d in failed["diagnostics"])


@pytest.mark.asyncio(loop_scope="module")
async def test_run_start_end_to_end(worker, schema_validate, julia_settings) -> None:
    supervisor, _ = worker
    model = _load(MODEL_FIXTURE)
    # Long enough that the run is still simulating when `run.start` returns (REQ-1).
    model["settings"]["output"] = {"mode": "points", "points": 200_000}
    run_id = "j16-backend-e2e"
    run_dir = julia_settings.projects_root / "runs" / run_id
    manifest_path = run_dir / "manifest.json"

    queue = supervisor.subscribe(run_id)
    try:
        accepted = await supervisor.call(
            "run.start",
            {
                "runId": run_id,
                "model": model,
                "projectDir": None,
                "runDir": str(run_dir),
            },
            timeout=120.0,
        )
        assert accepted == {"accepted": True}

        # REQ-1: the running manifest with the full signal list is already on disk, and the
        # run task has not started (the answer is written before the deferred spawn).
        assert manifest_path.exists()
        running = _load(manifest_path)
        assert running["status"] == "running"
        assert running["time"]["n"] == 0
        # J2.6b: DCMotor is a textual composite, so its internal port/observed
        # signals are recorded alongside the old top-level ids (73 signals).
        assert len(running["signals"]) == 73
        running_ids = {signal["id"] for signal in running["signals"]}
        assert {"Motor1/i", "Motor1/w_rel", "Motor1/shaft.f"} <= running_ids
        assert running["layout"] == "columnar-f64-v1"
        assert len(running["modelHash"]) == 64

        # The run is simulating: other requests are served concurrently.
        checked = await supervisor.call(
            "block.check", {"source": "broken = 1", "ref": "inline:while-running"}
        )
        assert checked["diagnostics"]
        assert (await supervisor.call("ping"))["warm"] is True

        notifications = []
        done = None
        deadline = asyncio.get_running_loop().time() + 300.0
        while done is None:
            remaining = deadline - asyncio.get_running_loop().time()
            assert remaining > 0, "run.done did not arrive within 300 s"
            message = await asyncio.wait_for(queue.get(), remaining)
            notifications.append(message)
            if message["method"] == "run.done":
                done = message["params"]
    finally:
        supervisor.unsubscribe(run_id, queue)

    assert done["runId"] == run_id
    assert done["status"] == "done", done["diagnostics"]
    assert done["diagnostics"] == []
    # J2.6b: the composite's winding + rotor are three differential states.
    assert done["stats"]["states"] == 3
    assert done["stats"]["equations"] == 41

    methods = [message["method"] for message in notifications]
    phases = [
        message["params"]["phase"]
        for message in notifications
        if message["method"] == "run.phase"
    ]
    for phase in ("parse", "flatten", "causality", "mtkcompile", "init", "simulate", "write"):
        assert phase in phases, phases
    assert "run.progress" in methods
    assert methods[-1] == "run.done"

    final = _load(manifest_path)
    schema_validate("run-manifest", final)
    assert final["status"] == "done"
    # The recorder keeps the 200k-point output grid plus the two rows of an
    # event instant (the Step edge); event rows are extra by design.
    assert final["time"]["n"] >= 200_000
    assert final["time"]["t0"] == 0.0
    assert final["time"]["t1"] == 1.0
    signal_ids = [signal["id"] for signal in final["signals"]]
    columns = np.fromfile(run_dir / "columns.f64", dtype="<f8")
    assert columns.size == final["time"]["n"] * (len(signal_ids) + 1)
    # `columns.f64` is column-major: the whole time column, then one column per signal.
    table = columns.reshape(len(signal_ids) + 1, final["time"]["n"])
    speed = table[1 + signal_ids.index("Motor1/shaft.f"), -1]
    # Plan 9.1: k*V/(R*d + k^2) = 239.80815347721824 rad/s at 12 V.
    assert speed == pytest.approx(239.80815347721824, rel=1e-4)
    assert np.isfinite(columns).all()
    assert (run_dir / "stream.f64").stat().st_size == columns.nbytes

    cancelled = await supervisor.call("run.cancel", {"runId": "no-such-run"})
    assert cancelled == {"ok": False}
