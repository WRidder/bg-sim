"""Run API tests (plan 3.5-3.7): start, manifest, data, CSV, cancel, prune, WS.

Every endpoint runs against the fixture-driven fake worker, so these tests need
no Julia. The data tests read the run files the fake actually wrote into
``<project>/runs/<id>/`` and compare the binary response with those bytes; the
event test writes a real (small) run directory with duplicated timestamps.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import struct
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDisconnect

from bgsim_server.app import create_app
from bgsim_server.decimate import DEFAULT_POINTS
from bgsim_server.runs import (
    DEFAULT_RUN_HISTORY,
    RUN_HISTORY_ENV,
    _prune_runs,
    run_history_limit,
)

TESTS_DIR = Path(__file__).resolve().parent
REPO = TESTS_DIR.parents[1]
MODEL_FIXTURE = REPO / "contracts" / "fixtures" / "model" / "valid" / "model.dcmotor.json"
SYNTHETIC_IDS = [
    "Synthetic/sine",
    "Synthetic/step",
    "Synthetic/counter",
    "Synthetic/flag",
]


def _model() -> dict[str, Any]:
    return json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))


def _settings() -> dict[str, Any]:
    return _model()["settings"]


def _make_project(settings, name: str = "demo") -> Path:
    project = settings.projects_root / name
    project.mkdir(parents=True, exist_ok=True)
    return project


def _wait_ready(client: TestClient, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.get("/api/health").json()["worker"] == "ready":
            return
        time.sleep(0.02)
    raise AssertionError(f"the worker did not become ready within {timeout:g} s")


def _start(client: TestClient, project: str = "demo", model: dict | None = None) -> str:
    response = client.post(
        f"/api/projects/{project}/runs", json={"model": model or _model()}
    )
    assert response.status_code == 201, response.text
    return response.json()["runId"]


def _wait_status(client: TestClient, run_id: str, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    document: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        document = response.json()
        if document["status"] != "running":
            return document
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} stayed running for {timeout:g} s: {document}")


def _decode(content: bytes) -> np.ndarray:
    assert len(content) >= 8
    n_signals, n_points = struct.unpack("<II", content[:8])
    expected = 8 + (1 + n_signals) * n_points * 8
    assert len(content) == expected, f"{len(content)} bytes, expected {expected}"
    return np.frombuffer(content[8:], dtype="<f8").reshape(1 + n_signals, n_points)


def _read_columns(project: Path, run_id: str) -> np.ndarray:
    return np.fromfile(project / "runs" / run_id / "columns.f64", dtype="<f8").reshape(5, 1001)


def _assert_envelopes(raw: np.ndarray, decimated: np.ndarray, px: int) -> None:
    """Compare every bucket of the response with the raw columns."""
    t = raw[0]
    n = t.size
    k = n // px
    for bucket in range(px):
        start = bucket * k
        stop = (bucket + 1) * k if bucket < px - 1 else n
        rows = (decimated[0] >= t[start]) & (decimated[0] <= t[stop - 1])
        assert rows.any(), f"bucket {bucket} is empty"
        for signal in range(1, raw.shape[0]):
            assert decimated[signal, rows].min() == raw[signal, start:stop].min()
            assert decimated[signal, rows].max() == raw[signal, start:stop].max()


def _write_run(
    project: Path,
    run_id: str,
    t: np.ndarray,
    names: list[str],
    values: np.ndarray,
    *,
    status: str = "done",
    signals: list[dict[str, Any]] | None = None,
) -> Path:
    """Write a real columns.f64 plus a valid manifest for a disk-only run."""
    run_dir = project / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if signals is None:
        signals = [
            {"id": name, "unit": None, "kind": "state", "path": name.split("/")[0], "type": "Real"}
            for name in names
        ]
    np.ascontiguousarray(np.vstack((t, values))).astype("<f8").tofile(run_dir / "columns.f64")
    manifest = {
        "id": run_id,
        "model": "Manual",
        "modelHash": "a" * 64,
        "created": "2026-10-21T09:14:03Z",
        "status": status,
        "settings": _settings(),
        "signals": signals,
        "time": {"n": int(t.size), "t0": float(t[0]), "t1": float(t[-1])},
        "diagnostics": [],
        "layout": "columnar-f64-v1",
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return run_dir


# --------------------------------------------------------------------------- manifest


def test_start_run_returns_the_id_and_a_valid_manifest(fake_settings, schema_validate) -> None:
    project = _make_project(fake_settings)
    app = create_app(fake_settings)
    with TestClient(app) as client:
        _wait_ready(client)
        run_id = _start(client)
        assert re.fullmatch(r"run-\d{8}-\d{6}-[0-9a-f]{6}", run_id)

        live = client.get(f"/api/runs/{run_id}")
        assert live.status_code == 200
        document = live.json()
        assert document["status"] == "running"
        assert document["id"] == run_id
        assert document["model"] == "DCMotorSpeed"
        assert document["layout"] == "columnar-f64-v1"
        assert [signal["id"] for signal in document["signals"]] == SYNTHETIC_IDS
        assert document["settings"] == _model()["settings"]
        schema_validate("run-manifest", document)

        done = _wait_status(client, run_id)
        schema_validate("run-manifest", done)
        assert done["status"] == "done"
        assert done["time"] == {"n": 1001, "t0": 0.0, "t1": 1.0}
        assert done["stats"]["states"] == 2

        run_dir = project / "runs" / run_id
        assert (run_dir / "columns.f64").is_file()
        assert (run_dir / "stream.f64").is_file()
        on_disk = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert on_disk == done, "the GET reflects exactly the worker's manifest"


def test_a_run_on_disk_is_found_by_a_fresh_app(fake_settings) -> None:
    project = _make_project(fake_settings)
    with TestClient(create_app(fake_settings)) as client:
        _wait_ready(client)
        run_id = _start(client)
        _wait_status(client, run_id)

    # A new app has no in-memory store entry; the run is resolved by scanning
    # <projects_root>/<project>/runs/<id> (plan 3.5).
    with TestClient(create_app(fake_settings)) as other:
        _wait_ready(other)
        document = other.get(f"/api/runs/{run_id}").json()
        assert document["status"] == "done"
        raw = _decode(other.get(f"/api/runs/{run_id}/data", params={"px": 0}).content)
        assert raw.shape == (5, 1001)
        assert np.array_equal(raw, _read_columns(project, run_id))


def test_an_invalid_manifest_is_a_named_500(fake_settings) -> None:
    project = _make_project(fake_settings)
    run_dir = project / "runs" / "run-broken"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text('{"id": "run-broken"}', encoding="utf-8")
    with TestClient(create_app(fake_settings)) as client:
        _wait_ready(client)
        response = client.get("/api/runs/run-broken")
        assert response.status_code == 500
        assert "run-manifest" in response.json()["detail"]
        assert "model" in response.json()["detail"]


# --------------------------------------------------------------------------- data


def test_data_returns_raw_columns_decimated_columns_and_a_subset(fake_settings) -> None:
    project = _make_project(fake_settings)
    with TestClient(create_app(fake_settings)) as client:
        _wait_ready(client)
        run_id = _start(client)
        _wait_status(client, run_id)
        raw_disk = _read_columns(project, run_id)

        raw = client.get(f"/api/runs/{run_id}/data", params={"px": 0})
        assert raw.status_code == 200
        assert raw.headers["content-type"] == "application/octet-stream"
        raw_columns = _decode(raw.content)
        assert raw_columns.shape == (5, 1001)
        assert np.array_equal(raw_columns, raw_disk)

        decimated = client.get(f"/api/runs/{run_id}/data", params={"px": 100})
        assert decimated.status_code == 200
        columns = _decode(decimated.content)
        assert columns.shape[0] == 5
        assert columns.shape[1] <= 2 * 100 + 2
        assert np.all(columns[0] >= 0.0) and np.all(columns[0] <= 1.0)
        _assert_envelopes(raw_columns, columns, 100)

        subset = client.get(
            f"/api/runs/{run_id}/data",
            params={"ids": "Synthetic/flag,Synthetic/sine", "px": 0},
        )
        selected = _decode(subset.content)
        assert selected.shape == (3, 1001)
        assert np.array_equal(selected[1], raw_disk[4])
        assert np.array_equal(selected[2], raw_disk[1])

        window = client.get(
            f"/api/runs/{run_id}/data", params={"t0": 0.2, "t1": 0.4, "px": 0}
        )
        windowed = _decode(window.content)
        assert windowed.shape[1] == 201
        assert windowed[0, 0] == pytest.approx(0.2)
        assert windowed[0, -1] == pytest.approx(0.4)
        step = windowed[2]
        assert step[windowed[0] < 0.25].max() == 0.0
        assert step[windowed[0] > 0.25].min() == 2.0

        empty = client.get(f"/api/runs/{run_id}/data", params={"t0": 5.0, "t1": 6.0})
        assert _decode(empty.content).shape == (5, 0)

        # The plan writes the query as ?t0=&t1=&px=1600; empty means "default".
        blank = client.get(
            f"/api/runs/{run_id}/data", params={"t0": "", "t1": "", "px": 10}
        )
        assert blank.status_code == 200
        assert _decode(blank.content).shape[1] <= 2 * 10 + 2


def test_data_preserves_an_event_duplicate(fake_settings) -> None:
    project = _make_project(fake_settings, "manual")
    n = 101
    t = np.linspace(0.0, 1.0, n)
    t[51] = t[50]  # the event instant, recorded as left and right limits
    values = np.vstack((np.linspace(0.0, 1.0, n), np.zeros(n)))
    values[1, 50] = 0.0
    values[1, 51] = 5.0
    signals = [
        {"id": "Dup/ramp", "unit": None, "kind": "state", "path": "Dup", "type": "Real"},
        {"id": "Dup/step", "unit": None, "kind": "state", "path": "Dup", "type": "Real"},
    ]
    _write_run(project, "run-event", t, ["Dup/ramp", "Dup/step"], values, signals=signals)

    with TestClient(create_app(fake_settings)) as client:
        _wait_ready(client)
        exact = _decode(
            client.get(
                "/api/runs/run-event/data",
                params={"t0": float(t[50]), "t1": float(t[50]), "px": 0},
            ).content
        )
        assert exact.shape == (3, 2)
        assert np.array_equal(exact[2], np.array([0.0, 5.0]))

        decimated = _decode(
            client.get("/api/runs/run-event/data", params={"px": 10}).content
        )
        at_event = decimated[0] == t[50]
        assert np.count_nonzero(at_event) == 2, "a min/max decimation must keep both limits"
        assert np.array_equal(decimated[2, at_event], np.array([0.0, 5.0]))


def test_data_reaches_the_stream_of_a_running_run(fake_settings) -> None:
    _make_project(fake_settings)
    with TestClient(create_app(fake_settings)) as client:
        _wait_ready(client)
        run_id = _start(client)
        deadline = time.monotonic() + 5.0
        columns = np.empty((5, 0))
        while time.monotonic() < deadline:
            response = client.get(f"/api/runs/{run_id}/data", params={"px": 0})
            assert response.status_code == 200
            columns = _decode(response.content)
            if columns.shape[1] > 0:
                break
            time.sleep(0.02)
        assert 0 < columns.shape[1] <= 1001, "the running run's stream.f64 is being followed"
        assert columns[0, 0] == 0.0
        assert np.all(np.diff(columns[0]) >= 0.0)
        assert np.allclose(columns[1], np.sin(2.0 * np.pi * columns[0]))

        assert client.delete(f"/api/runs/{run_id}").json() == {"ok": True}
        assert _wait_status(client, run_id)["status"] == "cancelled"


def test_data_errors_point_at_the_request(fake_settings) -> None:
    project = _make_project(fake_settings, "manual")
    t = np.linspace(0.0, 1.0, 50)
    _write_run(project, "run-small", t, ["A/x"], np.zeros((1, 50)))
    with TestClient(create_app(fake_settings)) as client:
        _wait_ready(client)
        assert client.get("/api/runs/nope").status_code == 404
        assert client.get("/api/runs/nope/data").status_code == 404
        assert client.get("/api/runs/nope/export.csv").status_code == 404
        assert client.delete("/api/runs/nope").status_code == 404

        unknown = client.get("/api/runs/run-small/data", params={"ids": "A/x,A/nope"})
        assert unknown.status_code == 400
        assert "A/nope" in unknown.json()["detail"]

        inverted = client.get("/api/runs/run-small/data", params={"t0": 2.0, "t1": 1.0})
        assert inverted.status_code == 400
        assert "less than" in inverted.json()["detail"]

        negative = client.get("/api/runs/run-small/data", params={"px": -1})
        assert negative.status_code == 422

        # A run whose manifest has no signals yet cannot serve /data.
        run_dir = _make_project(fake_settings, "manual") / "runs" / "run-empty"
        run_dir.mkdir()
        manifest = {
            "id": "run-empty",
            "model": "Empty",
            "modelHash": "b" * 64,
            "created": "2026-10-21T09:14:03Z",
            "status": "running",
            "settings": _settings(),
            "signals": [],
            "time": {"n": 0, "t0": 0.0, "t1": 0.0},
            "diagnostics": [],
            "layout": "columnar-f64-v1",
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        pending = client.get("/api/runs/run-empty/data")
        assert pending.status_code == 409
        assert "signals" in pending.json()["detail"]


# --------------------------------------------------------------------------- CSV


def test_export_csv_all_signals_and_a_subset(fake_settings) -> None:
    project = _make_project(fake_settings)
    with TestClient(create_app(fake_settings)) as client:
        _wait_ready(client)
        run_id = _start(client)
        _wait_status(client, run_id)
        columns = _read_columns(project, run_id)

        response = client.get(f"/api/runs/{run_id}/export.csv")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert f'filename="{run_id}.csv"' in response.headers["content-disposition"]
        rows = list(csv.reader(io.StringIO(response.text)))
        assert rows[0] == ["t", *SYNTHETIC_IDS]
        assert len(rows) == 1002
        assert float(rows[1][0]) == 0.0
        assert float(rows[251][2]) == 2.0, "the step at t=0.25"
        assert float(rows[1001][3]) == 10.0, "the counter at t=1.0"
        for index in (0, 500, 1000):
            assert float(rows[index + 1][1]) == pytest.approx(columns[1, index], abs=1e-12)

        subset = client.get(
            f"/api/runs/{run_id}/export.csv", params={"ids": "Synthetic/step"}
        )
        subset_rows = list(csv.reader(io.StringIO(subset.text)))
        assert subset_rows[0] == ["t", "Synthetic/step"]
        assert len(subset_rows) == 1002
        for index in (0, 250, 500, 1000):
            assert float(subset_rows[index + 1][1]) == columns[2, index]

        unknown = client.get(
            f"/api/runs/{run_id}/export.csv", params={"ids": "Synthetic/nope"}
        )
        assert unknown.status_code == 400
        assert "Synthetic/nope" in unknown.json()["detail"]


# --------------------------------------------------------------------------- cancel and history


def test_cancel_a_running_run(fake_settings) -> None:
    project = _make_project(fake_settings)
    with TestClient(create_app(fake_settings)) as client:
        _wait_ready(client)
        run_id = _start(client)
        response = client.delete(f"/api/runs/{run_id}")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

        document = _wait_status(client, run_id)
        assert document["status"] == "cancelled"
        assert 0 < document["time"]["n"] < 1001

        # Nothing is running any more; the worker says so honestly.
        assert client.delete(f"/api/runs/{run_id}").json() == {"ok": False}
        assert (project / "runs" / run_id / "manifest.json").is_file()


def test_run_history_keeps_the_last_n_per_model(fake_settings, monkeypatch) -> None:
    project = _make_project(fake_settings)
    for index in range(5):
        run_dir = project / "runs" / f"run-old-{index}"
        run_dir.mkdir(parents=True)
        manifest = {
            "id": f"run-old-{index}",
            "model": "DCMotorSpeed",
            "status": "done",
            "created": f"2026-10-2{index + 1}T09:00:00Z",
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    other = project / "runs" / "run-other"
    other.mkdir()
    (other / "manifest.json").write_text(
        json.dumps({"model": "OtherModel", "status": "done", "created": "2020-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BGSIM_RUN_HISTORY", "3")

    with TestClient(create_app(fake_settings)) as client:
        _wait_ready(client)
        run_id = _start(client)
        remaining = {path.name for path in (project / "runs").iterdir()}
        assert run_id in remaining
        assert {"run-old-3", "run-old-4"} <= remaining, "the newest two old runs survive"
        assert not {"run-old-0", "run-old-1", "run-old-2"} & remaining
        assert "run-other" in remaining, "another model's history is untouched"
        assert client.delete(f"/api/runs/{run_id}").json() == {"ok": True}
        _wait_status(client, run_id)


def _write_history_entry(
    project: Path,
    run_id: str,
    *,
    model: str = "DCMotorSpeed",
    status: str = "done",
    created: str = "2026-01-01T00:00:00Z",
    raw: str | None = None,
) -> None:
    run_dir = project / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    text = raw or json.dumps(
        {"id": run_id, "model": model, "status": status, "created": created}
    )
    (run_dir / "manifest.json").write_text(text, encoding="utf-8")


def test_run_history_limit_is_twenty_by_default_and_reads_the_environment(monkeypatch) -> None:
    monkeypatch.delenv(RUN_HISTORY_ENV, raising=False)
    assert DEFAULT_RUN_HISTORY == 20
    assert run_history_limit() == 20
    for raw, expected in (("7", 7), ("1", 1), ("0", 1), ("-3", 1), ("", 20), ("nope", 20)):
        monkeypatch.setenv(RUN_HISTORY_ENV, raw)
        assert run_history_limit() == expected, f"BGSIM_RUN_HISTORY={raw!r}"


def test_default_pruning_keeps_nineteen_old_runs_and_spares_active_or_foreign_runs(
    fake_settings,
) -> None:
    project = _make_project(fake_settings, "manual")
    for index in range(25):
        _write_history_entry(
            project,
            f"run-old-{index:02d}",
            created=f"2026-10-{index + 1:02d}T09:00:00Z",
        )
    # These must never be pruned: a live run, another model, a bare directory and
    # an unreadable manifest, plus the oldest run while it is active in memory.
    _write_history_entry(project, "run-live", status="running", created="2020-01-01T00:00:00Z")
    _write_history_entry(project, "run-other", model="OtherModel")
    (project / "runs" / "run-bare").mkdir()
    _write_history_entry(project, "run-bad", raw="{not json")

    # The new run is the twentieth: the nineteen newest old ones survive.
    _prune_runs(project, "DCMotorSpeed", DEFAULT_RUN_HISTORY, {"run-old-00"})

    remaining = {path.name for path in (project / "runs").iterdir()}
    assert remaining & {f"run-old-{index:02d}" for index in range(25)} == {
        f"run-old-{index:02d}" for index in [0, *range(6, 25)]
    }
    for kept in ("run-live", "run-other", "run-bare", "run-bad"):
        assert kept in remaining, f"{kept} must survive pruning"


def test_starting_a_run_without_a_worker_cleans_up(fake_settings) -> None:
    project = _make_project(fake_settings)
    app = create_app(fake_settings)

    async def call() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/api/projects/demo/runs", json={"model": _model()})

    response = asyncio.run(call())
    assert response.status_code == 503
    assert "not connected" in response.json()["detail"]
    assert list((project / "runs").iterdir()) == []


# --------------------------------------------------------------------------- websocket


def test_run_socket_reports_phases_progress_and_a_live_tail(fake_settings) -> None:
    _make_project(fake_settings)
    with TestClient(create_app(fake_settings)) as client:
        _wait_ready(client)
        run_id = _start(client)
        started = time.monotonic()
        messages: list[dict[str, Any]] = []
        with client.websocket_connect(f"/api/ws/runs/{run_id}") as socket:
            socket.send_json({"subscribe": ["Synthetic/sine", "Synthetic/step"]})
            while True:
                message = socket.receive_json()
                messages.append(message)
                if message["method"] == "run.done":
                    break
        elapsed = time.monotonic() - started

        methods = [message["method"] for message in messages]
        assert methods[-1] == "run.done"
        assert "run.phase" in methods and "run.progress" in methods and "run.tail" in methods
        phases = [m["params"]["phase"] for m in messages if m["method"] == "run.phase"]
        assert "simulate" in phases and "write" in phases

        rows = [m["params"]["rows"] for m in messages if m["method"] == "run.progress"]
        assert rows == sorted(rows) and rows[-1] <= 1001
        done = messages[-1]["params"]
        assert done["runId"] == run_id and done["status"] == "done"

        tails = [m["params"] for m in messages if m["method"] == "run.tail"]
        assert tails, "a subscribed socket receives live data"
        assert len(tails) <= 20 * elapsed + 3, "at most 20 tail messages per second"
        for tail in tails:
            assert tail["runId"] == run_id
            assert tail["ids"] == ["Synthetic/sine", "Synthetic/step"]
            assert len(tail["values"]) == 2
            assert len(tail["values"][0]) == len(tail["time"])
            assert len(tail["values"][1]) == len(tail["time"])
            assert tail["t0"] <= tail["t1"]
        assert tails[-1]["t1"] == pytest.approx(1.0)
        times = np.concatenate([np.asarray(tail["time"]) for tail in tails])
        sine = np.concatenate([np.asarray(tail["values"][0]) for tail in tails])
        assert np.all(np.diff(times) >= 0.0)
        assert np.allclose(sine, np.sin(2.0 * np.pi * times), atol=1e-12)


def test_run_socket_aliases_the_unprefixed_path(fake_settings) -> None:
    _make_project(fake_settings)
    with TestClient(create_app(fake_settings)) as client:
        _wait_ready(client)
        run_id = _start(client)
        _wait_status(client, run_id)
        # The data is sent through /ws/runs/{id}, which app.py cannot include
        # under /api; the router's lifespan registers it (see runs.py).
        messages: list[dict[str, Any]] = []
        with client.websocket_connect(f"/ws/runs/{run_id}") as socket:
            while True:
                message = socket.receive_json()
                messages.append(message)
                if message["method"] == "run.done":
                    break
        assert messages[-1]["params"]["status"] == "done"
        tails = [m for m in messages if m["method"] == "run.tail"]
        assert tails and tails[-1]["params"]["ids"] == SYNTHETIC_IDS
        assert len(tails[-1]["params"]["time"]) <= 2 * 200 + 2


def test_run_socket_unknown_run_and_unknown_signal(fake_settings) -> None:
    _make_project(fake_settings)
    with TestClient(create_app(fake_settings)) as client:
        _wait_ready(client)
        with client.websocket_connect("/api/ws/runs/run-nope") as socket:
            error = socket.receive_json()
            assert error["method"] == "run.error"
            assert "run-nope" in error["params"]["message"]
            with pytest.raises(WebSocketDisconnect):
                socket.receive_json()

        run_id = _start(client)
        with client.websocket_connect(f"/api/ws/runs/{run_id}") as socket:
            socket.send_json({"subscribe": ["Synthetic/nope"]})
            error = None
            for _ in range(40):
                message = socket.receive_json()
                if message["method"] == "run.error":
                    error = message
                    break
                if message["method"] == "run.done":
                    break
            assert error is not None and "Synthetic/nope" in error["params"]["message"]
            socket.send_json({"subscribe": ["Synthetic/flag"]})
            tails = []
            while True:
                message = socket.receive_json()
                if message["method"] == "run.tail":
                    tails.append(message["params"])
                if message["method"] == "run.done":
                    break
            assert tails and all(tail["ids"] == ["Synthetic/flag"] for tail in tails)

        # A running run on disk that this backend does not follow has no live
        # notification stream; say so instead of pretending to follow it.
        stale = fake_settings.projects_root / "demo" / "runs" / "run-stale"
        stale.mkdir()
        (stale / "manifest.json").write_text(
            json.dumps(
                {
                    "id": "run-stale",
                    "model": "Stale",
                    "modelHash": "c" * 64,
                    "created": "2026-10-21T09:14:03Z",
                    "status": "running",
                    "settings": _settings(),
                    "signals": [],
                    "time": {"n": 0, "t0": 0.0, "t1": 0.0},
                    "diagnostics": [],
                    "layout": "columnar-f64-v1",
                }
            ),
            encoding="utf-8",
        )
        with client.websocket_connect("/api/ws/runs/run-stale") as socket:
            error = socket.receive_json()
            assert "not being followed" in error["params"]["message"]
            with pytest.raises(WebSocketDisconnect):
                socket.receive_json()


def test_default_data_budget_is_two_rows_per_pixel() -> None:
    # The endpoint's default comes from decimate.DEFAULT_POINTS, not a second
    # constant that could drift (plan 3.7 says px defaults to 1600).
    assert DEFAULT_POINTS == 1600
