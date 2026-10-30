"""A debug run against the real Julia worker (WP P4.1; needs J4.5 for the worker side).

Marked ``julia`` and deselected by default; the gate runs it (``tools/check.py --lane x`` or
``uv run pytest backend/tests -m julia``). It follows the 3.8 worker protocol through the
backend's own endpoints: start a debug run of ``examples/dc-motor`` (iconic), pause on a watch
on the winding current, change the winding resistance, continue, and expect the run to finish
with the edit in the manifest's ``debug.edits``.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bgsim_server.app import create_app

pytestmark = pytest.mark.julia

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "dc-motor"
COLD_START_TIMEOUT = 600.0  # a cold `using BGSim` may recompile the package first

#: The step to 12 V at t = 0.01 s drives the winding current to about 5.9 A within a
#: millisecond (V / R = 12 V / 2 Ohm, minus the back-EMF of a rotor that has hardly moved),
#: so the watch below crosses upward exactly once.
WATCH = 's"Motor1/i" > 5'


def _wait_ready(client: TestClient) -> None:
    deadline = time.monotonic() + COLD_START_TIMEOUT
    while client.get("/api/health").json()["worker"] != "ready":
        assert time.monotonic() < deadline, "the Julia worker did not become ready"
        time.sleep(0.25)


def _until(socket: Any, method: str, log: list[dict[str, Any]]) -> dict[str, Any]:
    while True:
        message = socket.receive_json()
        log.append(message)
        if message["method"] == method:
            return message["params"]


def test_debug_run_of_dc_motor_pauses_on_a_watch_edits_and_finishes(
    real_settings, schema_validate
) -> None:
    project = real_settings.projects_root / "dc-motor"
    shutil.copytree(EXAMPLE, project)
    model = json.loads((project / "models" / "iconic.bgmodel.json").read_text(encoding="utf-8"))
    breakpoints = [
        {
            "id": "bp1",
            "enabled": True,
            "kind": "watch",
            "watch": {"expr": WATCH, "context": None},
            "hitCount": None,
        }
    ]

    with TestClient(create_app(real_settings)) as client:
        _wait_ready(client)
        started = client.post(
            "/api/projects/dc-motor/runs",
            json={"model": model, "debug": {"breakpoints": breakpoints, "pauseOnEntry": False}},
        )
        assert started.status_code == 201, started.text
        run_id = started.json()["runId"]

        log: list[dict[str, Any]] = []
        with client.websocket_connect(f"/ws/runs/{run_id}") as socket:
            socket.send_json({"subscribe": ["Motor1/i"]})
            paused = _until(socket, "debug.paused", log)
            schema_validate("debug", paused)
            assert paused["runId"] == run_id
            assert paused["reason"] == "breakpoint" and paused["breakpointId"] == "bp1"
            assert 0.01 <= paused["t"] < 0.1, "the current crosses 5 A right after the step"
            assert paused["frame"] is None  # a watch pause has no statement frame

            manifest = client.get(f"/api/runs/{run_id}").json()
            schema_validate("run-manifest", manifest)
            assert manifest["status"] == "paused"
            assert manifest["debug"]["breakpoints"] == breakpoints
            assert manifest["debug"]["pauses"][-1] == {"t": paused["t"], "reason": "breakpoint"}

            values = client.get(
                f"/api/runs/{run_id}/values", params={"ids": "Motor1/i"}
            ).json()
            assert values["t"] == pytest.approx(paused["t"], abs=1e-9)
            assert values["values"]["Motor1/i"] >= 5.0 - 1e-6

            evaluated = client.post(
                f"/api/runs/{run_id}/evaluate", json={"expr": WATCH, "context": None}
            ).json()
            assert evaluated["value"] is True and evaluated["diagnostics"] == []

            edit = client.post(
                f"/api/runs/{run_id}/debug/setParameter",
                json={"name": "Motor1/R", "value": 2.5},
            )
            assert edit.status_code == 200, edit.text
            result = edit.json()
            assert result["ok"] is True and result["diagnostics"] == []
            assert result["edit"]["kind"] == "parameter" and result["edit"]["target"] == "Motor1/R"
            assert result["edit"]["value"] == 2.5
            assert result["edit"]["t"] == pytest.approx(paused["t"], abs=1e-9)

            resumed = client.post(f"/api/runs/{run_id}/debug/continue", json={})
            assert resumed.status_code == 200 and resumed.json() == {"ok": True}
            _until(socket, "debug.resumed", log)
            done = _until(socket, "run.done", log)

        assert done["runId"] == run_id and done["status"] == "done", done["diagnostics"]
        final = client.get(f"/api/runs/{run_id}").json()
        schema_validate("run-manifest", final)
        assert final["status"] == "done"
        assert final["debug"]["edits"] == [result["edit"]]
        assert paused["t"] in [pause["t"] for pause in final["debug"]["pauses"]]

        # A debug command on a finished run is a state conflict, not a server error.
        late = client.post(f"/api/runs/{run_id}/debug/continue", json={})
        assert late.status_code == 409
        assert "not paused" in late.json()["message"]
