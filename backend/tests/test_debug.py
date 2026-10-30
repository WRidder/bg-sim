"""Debug API tests (plan 3.8, WP P4.1) against the fake worker's debug runs.

Every endpoint of ``debug.py`` runs against :mod:`bgsim_server.fake_debug`; the tests need no
Julia. A tiny project (``demo``) holds a block ``Ctrl`` with ``@discrete`` code, and the model
is the DC motor fixture plus a ``Ctrl`` node, so line breakpoints resolve against a real
source. The fake paces a run at 10 ms of wall time per tick; the fixture speeds that up
except where a test needs a run that is still going (``debug.pause``).
"""

from __future__ import annotations

import json
import struct
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from bgsim_server import fake_debug
from bgsim_server.app import create_app
from bgsim_server.runs import _prune_runs

REPO = Path(__file__).resolve().parents[2]
MODEL_FIXTURE = REPO / "contracts" / "fixtures" / "model" / "valid" / "model.dcmotor.json"

#: Lines of ``CTRL_SOURCE``: the @discrete statements are 12, 13, 14 and 16.
CTRL_SOURCE = """@block Ctrl begin
    @inputs begin
        u::Real
    end
    @outputs begin
        y::Real = 0.0
    end
    @equations begin
        y ~ u
    end
    @discrete Ts = 1e-2 begin
        a = u
        if a > 1
            y = 2
        end
        y = a
    end
end
"""
STATEMENTS = [12, 13, 14, 16]
SINE_UP_5 = 0.084  # first 1 ms row where sin(2 pi t) > 0.5
SINE_DOWN_5 = 0.584  # first row where sin(2 pi t) < -0.5


def _model(extra_nodes: bool = True) -> dict[str, Any]:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
    if extra_nodes:
        model["diagram"]["nodes"].append(
            {
                "id": "n99",
                "name": "Ctrl",
                "block": {"ref": "project:Ctrl"},
                "position": {"x": 0, "y": 0},
            }
        )
    return model


def line_bp(
    bp_id: str,
    line: int,
    *,
    ref: str = "project:Ctrl",
    path: str | None = "Ctrl",
    condition: str | None = None,
    hit_count: int | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    return {
        "id": bp_id,
        "enabled": enabled,
        "kind": "line",
        "line": {"ref": ref, "line": line, "path": path},
        "condition": condition,
        "hitCount": hit_count,
    }


def watch_bp(bp_id: str, expr: str, context: str | None = None) -> dict[str, Any]:
    return {
        "id": bp_id,
        "enabled": True,
        "kind": "watch",
        "watch": {"expr": expr, "context": context},
        "hitCount": None,
    }


def time_bp(bp_id: str, t: float) -> dict[str, Any]:
    return {"id": bp_id, "enabled": True, "kind": "time", "time": {"t": t}}


def event_bp(bp_id: str, path: str | None = None) -> dict[str, Any]:
    return {"id": bp_id, "enabled": True, "kind": "event", "event": {"path": path}}


@dataclass
class Env:
    client: TestClient
    project: Path

    def start(
        self,
        breakpoints: list[dict[str, Any]] | None = None,
        *,
        entry: bool = False,
        debug: bool = True,
        model: dict[str, Any] | None = None,
    ) -> str:
        body: dict[str, Any] = {"model": model or _model()}
        if debug:
            body["debug"] = {"breakpoints": breakpoints or [], "pauseOnEntry": entry}
        response = self.client.post("/api/projects/demo/runs", json=body)
        assert response.status_code == 201, response.text
        return response.json()["runId"]

    def command(self, run_id: str, name: str, body: dict[str, Any] | None = None):
        return self.client.post(f"/api/runs/{run_id}/debug/{name}", json=body or {})

    def ok(self, run_id: str, name: str, body: dict[str, Any] | None = None) -> Any:
        response = self.command(run_id, name, body)
        assert response.status_code == 200, response.text
        return response.json()

    def put_breakpoints(self, run_id: str, breakpoints: list[dict[str, Any]]) -> list[dict]:
        response = self.client.put(
            f"/api/runs/{run_id}/breakpoints", json={"breakpoints": breakpoints}
        )
        assert response.status_code == 200, response.text
        return response.json()["breakpoints"]

    def manifest(self, run_id: str) -> dict[str, Any]:
        response = self.client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        return response.json()

    def wait_status(self, run_id: str, wanted: str, timeout: float = 10.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        document: dict[str, Any] = {}
        while time.monotonic() < deadline:
            document = self.manifest(run_id)
            if document["status"] == wanted:
                return document
            time.sleep(0.01)
        raise AssertionError(f"run {run_id} did not reach {wanted!r}: {document['status']!r}")

    def data(self, run_id: str, ids: str = "Synthetic/sine") -> np.ndarray:
        response = self.client.get(f"/api/runs/{run_id}/data", params={"ids": ids, "px": 0})
        assert response.status_code == 200, response.text
        n_signals, n_points = struct.unpack("<II", response.content[:8])
        return np.frombuffer(response.content[8:], dtype="<f8").reshape(1 + n_signals, n_points)


class Feed:
    """The messages of a run socket, read until a wanted method arrives."""

    def __init__(self, socket: Any):
        self.socket = socket
        self.log: list[dict[str, Any]] = []

    def until(self, method: str) -> dict[str, Any]:
        while True:
            message = self.socket.receive_json()
            self.log.append(message)
            if message["method"] == method:
                return message["params"]

    def paused(self) -> dict[str, Any]:
        return self.until("debug.paused")

    def methods(self) -> list[str]:
        return [message["method"] for message in self.log]


@pytest.fixture
def env(fake_settings, monkeypatch) -> Iterator[Env]:
    monkeypatch.setattr(fake_debug, "TICK_WALL_S", 0.0005)
    project = fake_settings.projects_root / "demo"
    (project / "library").mkdir(parents=True)
    (project / "library" / "Ctrl.jl").write_text(CTRL_SOURCE, encoding="utf-8")
    with TestClient(create_app(fake_settings)) as client:
        deadline = time.monotonic() + 5.0
        while client.get("/api/health").json()["worker"] != "ready":
            assert time.monotonic() < deadline, "the worker did not become ready"
            time.sleep(0.02)
        yield Env(client, project)


def _finish(env: Env, run_id: str, feed: Feed) -> dict[str, Any]:
    """Continue until the run ends; returns the ``run.done`` params."""
    env.ok(run_id, "continue")
    return feed.until("run.done")


# --------------------------------------------------------------------------- start and manifest


def test_debug_start_records_breakpoints_and_pauses_on_entry(env, schema_validate) -> None:
    breakpoints = [line_bp("bp1", 13), watch_bp("bp2", 's"Synthetic/sine" > 0.5')]
    run_id = env.start(breakpoints, entry=True)
    manifest = env.wait_status(run_id, "paused")
    schema_validate("run-manifest", manifest)
    assert manifest["debug"]["breakpoints"] == breakpoints
    assert manifest["debug"]["edits"] == []
    assert manifest["debug"]["pauses"] == [{"t": 0.0, "reason": "entry"}]
    assert manifest["time"]["n"] == 1 and manifest["time"]["t1"] == 0.0

    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        info = feed.paused()  # a late socket gets the current pause
        assert info["reason"] == "entry" and info["t"] == 0.0 and info["tick"] is None
        assert info["location"] is None and info["frame"] is None
        schema_validate("debug", info)


def test_plain_run_has_no_debug_block(env) -> None:
    run_id = env.start(debug=False)
    document = env.wait_status(run_id, "done")
    assert "debug" not in document


# --------------------------------------------------------------------------- validation, 404, 409


def test_unknown_run_and_command_are_404(env) -> None:
    run_id = env.start(entry=True)
    env.wait_status(run_id, "paused")
    assert env.command(run_id, "rewind").status_code == 404
    assert env.command("run-nope", "continue").status_code == 404
    assert env.client.put("/api/runs/run-nope/breakpoints", json={"breakpoints": []}).status_code == 404
    assert (
        env.client.post("/api/runs/run-nope/evaluate", json={"expr": "t"}).status_code == 404
    )
    assert env.client.get("/api/runs/run-nope/values", params={"ids": "a"}).status_code == 404
    assert env.client.post("/api/runs/run-nope/replay").status_code == 404
    assert env.client.post("/api/runs/run-nope/branch", json={"t": 0.1}).status_code == 404


def test_invalid_bodies_are_422(env) -> None:
    run_id = env.start(entry=True)
    env.wait_status(run_id, "paused")
    assert env.command(run_id, "step", {}).status_code == 422
    assert env.command(run_id, "step", {"granularity": "leap"}).status_code == 422
    assert env.command(run_id, "runTo", {"t": "soon"}).status_code == 422
    assert env.command(run_id, "setParameter", {"name": "Motor1/R"}).status_code == 422
    assert env.command(run_id, "continue", {"extra": 1}).status_code == 422
    response = env.command(run_id, "step", {"granularity": "leap"})
    assert any("granularity" in str(error["loc"]) for error in response.json()["detail"])

    bad = {"breakpoints": [{"id": "x", "enabled": True, "kind": "bogus"}]}
    assert env.client.put(f"/api/runs/{run_id}/breakpoints", json=bad).status_code == 422
    assert env.client.put(f"/api/runs/{run_id}/breakpoints", json={}).status_code == 422
    assert env.client.post(f"/api/runs/{run_id}/evaluate", json={}).status_code == 422
    assert env.client.get(f"/api/runs/{run_id}/values", params={"ids": " , "}).status_code == 422
    assert env.client.get(f"/api/runs/{run_id}/values").status_code == 422
    assert env.client.post(f"/api/runs/{run_id}/branch", json={}).status_code == 422
    start = env.client.post(
        "/api/projects/demo/runs",
        json={"model": _model(), "debug": {"breakpoints": [], "pauseOnEntry": "maybe"}},
    )
    assert start.status_code == 422


def test_commands_on_a_run_that_is_not_paused_are_409(env) -> None:
    plain = env.start(debug=False)
    env.wait_status(plain, "done")
    for name, body in (
        ("continue", {}),
        ("step", {"granularity": "tick"}),
        ("runTo", {"t": 0.5}),
        ("setParameter", {"name": "Motor1/R", "value": 1.0}),
        ("setState", {"id": "Motor1/w", "value": 1.0}),
    ):
        response = env.command(plain, name, body)
        assert response.status_code == 409, (name, response.text)
        assert response.json()["detail"] == "run is not paused"
        assert response.json()["message"] == "run is not paused"
    assert env.command(plain, "pause").status_code == 409
    assert env.client.post(f"/api/runs/{plain}/evaluate", json={"expr": "t"}).status_code == 409
    assert env.client.get(f"/api/runs/{plain}/values", params={"ids": "a"}).status_code == 409
    assert (
        env.client.put(f"/api/runs/{plain}/breakpoints", json={"breakpoints": []}).status_code
        == 409
    )

    # A debug run that is running (not paused) refuses the paused-only commands too.
    run_id = env.start([line_bp("bp1", 13)], entry=True)
    env.wait_status(run_id, "paused")
    env.ok(run_id, "continue")
    env.wait_status(run_id, "paused")  # the breakpoint
    env.put_breakpoints(run_id, [])
    env.ok(run_id, "continue")
    done = env.wait_status(run_id, "done")
    assert done["status"] == "done"
    assert env.command(run_id, "continue").status_code == 409


# --------------------------------------------------------------------------- line breakpoints


def test_line_breakpoint_statuses(env, schema_validate) -> None:
    run_id = env.start(entry=True)
    env.wait_status(run_id, "paused")
    statuses = env.put_breakpoints(
        run_id,
        [
            line_bp("ok", 13),
            line_bp("every", 12, path=None),
            line_bp("equation", 9),
            line_bp("header", 11),
            line_bp("end", 15),
            line_bp("outside", 99),
            line_bp("unused", 3, ref="project:Unused"),
            line_bp("wrongpath", 13, path="Elsewhere"),
            line_bp("stdlib-unused", 7, ref="stdlib:discrete/Quantizer", path=None),
        ],
    )
    by_id = {status["id"]: status for status in statuses}
    assert [status["id"] for status in statuses] == [
        "ok", "every", "equation", "header", "end", "outside", "unused", "wrongpath",
        "stdlib-unused",
    ]  # fmt: skip
    for status in statuses:
        schema_validate("debug", status)

    assert by_id["ok"]["verified"] is True
    assert by_id["ok"]["resolved"] == {"hooks": 1, "paths": ["Ctrl"]}
    assert by_id["every"]["verified"] is True and by_id["every"]["resolved"]["hooks"] == 1

    e401 = by_id["equation"]["diagnostics"][0]
    assert by_id["equation"]["verified"] is False and by_id["equation"]["resolved"]["hooks"] == 0
    assert e401["code"] == "E401" and e401["severity"] == "error"
    assert "equations do not execute in order" in e401["hint"]
    assert e401["scope"] == "@equations" and e401["block"] == "project:Ctrl"
    assert e401["source"]["kind"] == "project" and e401["source"]["range"]["line"] == 9
    for name in ("header", "end", "outside"):
        assert by_id[name]["verified"] is False
        assert by_id[name]["diagnostics"][0]["code"] == "E401", name

    for name in ("unused", "wrongpath", "stdlib-unused"):
        assert by_id[name]["verified"] is False, name
        assert by_id[name]["diagnostics"][0]["code"] == "W401", name
        assert by_id[name]["diagnostics"][0]["severity"] == "warning"
    assert by_id["unused"]["diagnostics"][0]["block"] == "project:Unused"
    assert "not used in this model" in by_id["unused"]["diagnostics"][0]["message"]

    # The manifest follows the full set.
    manifest = env.manifest(run_id)
    assert [bp["id"] for bp in manifest["debug"]["breakpoints"]] == [s["id"] for s in statuses]


def test_stdlib_and_inline_sources_resolve(env) -> None:
    model = _model()
    model["diagram"]["nodes"] += [
        {
            "id": "n50",
            "name": "Quant",
            "block": {"ref": "stdlib:discrete/Quantizer"},
            "position": {"x": 0, "y": 0},
        },
        {
            "id": "n51",
            "name": "Inl",
            "block": {"inline": {"source": CTRL_SOURCE}},
            "position": {"x": 0, "y": 0},
        },
    ]
    run_id = env.start(entry=True, model=model)
    env.wait_status(run_id, "paused")
    statuses = {
        s["id"]: s
        for s in env.put_breakpoints(
            run_id,
            [
                line_bp("q-stmt", 7, ref="stdlib:discrete/Quantizer", path="Quant"),
                line_bp("q-decl", 3, ref="stdlib:discrete/Quantizer", path="Quant"),
                line_bp("i-stmt", 14, ref="inline:n51", path="Inl"),
                line_bp("i-eq", 9, ref="inline:n51", path="Inl"),
            ],
        )
    }
    assert statuses["q-stmt"]["verified"] and statuses["q-stmt"]["resolved"]["paths"] == ["Quant"]
    assert statuses["q-decl"]["diagnostics"][0]["code"] == "E401"
    assert statuses["q-decl"]["diagnostics"][0]["source"]["kind"] == "stdlib"
    assert statuses["i-stmt"]["verified"] is True
    assert statuses["i-eq"]["diagnostics"][0]["code"] == "E401"


def test_line_breakpoint_pauses_every_tick_with_a_changing_frame(env, schema_validate) -> None:
    run_id = env.start([line_bp("bp1", 13)])
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        seen = []
        for tick in range(4):
            info = feed.paused()
            schema_validate("debug", info)
            seen.append(info)
            assert info["reason"] == "breakpoint" and info["breakpointId"] == "bp1"
            assert info["tick"] == tick and info["t"] == pytest.approx(0.01 * tick)
            assert info["location"]["path"] == "Ctrl"
            assert info["location"]["ref"] == "project:Ctrl"
            assert info["location"]["scope"] == "@discrete"
            assert info["location"]["range"] == {"line": 13, "col": 9, "endLine": 13, "endCol": 17}
            env.ok(run_id, "continue")
        locals_ = [{v["name"]: v["value"] for v in info["frame"]["locals"]} for info in seen]
        assert [item["k"] for item in locals_] == [0, 1, 2, 3]
        assert len({item["v"] for item in locals_}) == 4, "the frame changes per tick"
        frame = seen[3]["frame"]
        assert {v["name"] for v in frame["locals"]} >= {"k", "v", "y", "on", "xhat"}
        assert frame["held"] and frame["previous"]
        xhat = next(v for v in frame["locals"] if v["name"] == "xhat")
        assert xhat["size"] == [2] and len(xhat["value"]) == 2


def test_condition_and_hit_count(env) -> None:
    run_id = env.start([line_bp("bp1", 13, condition="k == 5")])
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        info = feed.paused()
        assert info["tick"] == 5 and info["t"] == pytest.approx(0.05)
        done = _finish(env, run_id, feed)
        assert done["status"] == "done"
        assert feed.methods().count("debug.paused") == 1, "k == 5 holds at one tick only"

    run_id = env.start([line_bp("bp1", 13, hit_count=3)])
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        assert feed.paused()["tick"] == 2  # ticks 0, 1, 2: the third hit
        _finish(env, run_id, feed)
        assert feed.methods().count("debug.paused") == 1, "the n-th hit only"

    run_id = env.start([line_bp("bp1", 13, condition="k > 2", hit_count=2)])
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        assert feed.paused()["tick"] == 4  # hits are k = 3 and k = 4

    bad = env.start(entry=True)
    env.wait_status(bad, "paused")
    statuses = env.put_breakpoints(
        bad,
        [
            line_bp("unknown", 13, condition="nope == 1"),
            line_bp("syntax", 13, condition="k =="),
            line_bp("flag", 13, condition="on && k > 1"),
        ],
    )
    assert statuses[0]["verified"] is False and statuses[0]["diagnostics"][0]["code"] == "E003"
    assert statuses[1]["verified"] is False and statuses[1]["diagnostics"][0]["code"] == "E001"
    assert statuses[2]["verified"] is True


def test_disabled_breakpoints_do_not_pause_and_resets_count(env) -> None:
    run_id = env.start([line_bp("bp1", 13, enabled=False)])
    document = env.wait_status(run_id, "done")
    assert document["debug"]["pauses"] == []


def test_statement_tick_and_solver_stepping(env, schema_validate) -> None:
    run_id = env.start([line_bp("bp1", 12, condition="k == 3")])
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        info = feed.paused()
        assert info["tick"] == 3 and info["location"]["range"]["line"] == 12

        lines = []
        for _ in range(4):  # 13, 14, 16, then the first statement of the next tick
            env.ok(run_id, "step", {"granularity": "statement"})
            info = feed.paused()
            schema_validate("debug", info)
            assert info["reason"] == "step" and info["frame"] is not None
            lines.append((info["tick"], info["location"]["range"]["line"]))
        assert lines == [(3, 13), (3, 14), (3, 16), (4, 12)]

        env.ok(run_id, "step", {"granularity": "tick"})
        info = feed.paused()
        assert info["reason"] == "step" and info["tick"] == 4 and info["t"] == pytest.approx(0.04)
        assert info["location"] is None and info["frame"] is None
        env.ok(run_id, "step", {"granularity": "tick"})
        assert feed.paused()["t"] == pytest.approx(0.05)

        env.ok(run_id, "step", {"granularity": "solverStep"})
        info = feed.paused()
        assert info["reason"] == "step" and info["t"] == pytest.approx(0.051)
        assert info["tick"] is None

        env.ok(run_id, "step", {"granularity": "event"})
        info = feed.paused()
        assert info["reason"] == "step" and info["t"] == pytest.approx(0.25)
        assert info["location"]["scope"] == "@events"
        env.ok(run_id, "step", {"granularity": "event"})
        assert feed.paused()["t"] == pytest.approx(0.5)


def test_statement_step_without_hooks_is_a_tick_step(env) -> None:
    run_id = env.start(entry=True, model=_model(extra_nodes=False))
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        feed.paused()
        env.ok(run_id, "step", {"granularity": "statement"})
        info = feed.paused()
        assert info["reason"] == "step" and info["tick"] == 0
        env.ok(run_id, "step", {"granularity": "statement"})
        assert feed.paused()["tick"] == 1


# --------------------------------------------------------------------------- other pauses


def test_pause_request_pauses_a_running_run(env, monkeypatch) -> None:
    monkeypatch.setattr(fake_debug, "TICK_WALL_S", 0.01)  # real pace: the run lasts a second
    run_id = env.start()
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        time.sleep(0.1)
        env.ok(run_id, "pause")
        info = feed.paused()
        assert info["reason"] == "pause" and info["breakpointId"] is None
        assert 0.0 < info["t"] < 1.0
        assert env.ok(run_id, "pause") == {"ok": True}  # already paused: nothing to do
        assert _finish(env, run_id, feed)["status"] == "done"


def test_run_to_and_time_breakpoint(env) -> None:
    run_id = env.start(entry=True)
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        feed.paused()
        assert env.command(run_id, "runTo", {"t": 0.0}).status_code == 409  # not in the future
        assert env.command(run_id, "runTo", {"t": 5.0}).status_code == 409  # after the end
        env.ok(run_id, "runTo", {"t": 0.2503})
        info = feed.paused()
        assert info["reason"] == "time" and info["t"] == pytest.approx(0.251)
        assert info["breakpointId"] is None

        env.put_breakpoints(run_id, [time_bp("bt", 0.3), time_bp("bt2", 0.1)])
        env.ok(run_id, "continue")
        info = feed.paused()  # the time breakpoint in the past fires at once, once
        assert info["reason"] == "time" and info["breakpointId"] == "bt2"
        env.ok(run_id, "continue")
        info = feed.paused()
        assert info["breakpointId"] == "bt" and info["t"] == pytest.approx(0.3)
        env.ok(run_id, "continue")
        assert feed.until("run.done")["status"] == "done"
        assert feed.methods().count("debug.paused") == 4  # entry, runTo, bt2, bt


def test_event_breakpoint_pauses_at_the_step_and_flag_switches(env) -> None:
    run_id = env.start([event_bp("ev")])
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        first = feed.paused()
        assert first["reason"] == "event" and first["breakpointId"] == "ev"
        assert first["t"] == pytest.approx(0.25) and first["frame"] is None
        assert first["location"]["scope"] == "@events"
        env.ok(run_id, "continue")
        assert feed.paused()["t"] == pytest.approx(0.5)
        statuses = env.put_breakpoints(run_id, [event_bp("ev", "Ball"), event_bp("ev2", "Synthetic")])
        assert statuses[0]["verified"] is False and statuses[0]["diagnostics"][0]["code"] == "W401"
        assert statuses[1]["verified"] is True


# --------------------------------------------------------------------------- watch breakpoints


@pytest.mark.parametrize(
    ("expr", "wanted"),
    [
        ('s"Synthetic/sine" > 0.5', SINE_UP_5),
        ('s"Synthetic/sine" < -0.5', SINE_DOWN_5),
        ('s"Synthetic/step" >= 2', 0.25),
        ('s"Synthetic/counter" <= 0 && s"Synthetic/sine" > 0.2', 0.033),
        ('s"Synthetic/sine" > s"Synthetic/step"', 0.001),
        ('t > 0.4', 0.401),
    ],
)
def test_watch_fires_on_the_upward_crossing(env, expr: str, wanted: float, schema_validate) -> None:
    run_id = env.start([watch_bp("w", expr)])
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        info = feed.paused()
        schema_validate("debug", info)
        assert info["reason"] == "breakpoint" and info["breakpointId"] == "w"
        assert info["t"] == pytest.approx(wanted, abs=1e-9)
        assert info["frame"] is None and info["tick"] is None
        assert info["location"]["scope"] == "watch"


def test_watch_pause_data_ends_at_the_pause_time(env) -> None:
    run_id = env.start(entry=True)
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        socket.send_json({"subscribe": ["Synthetic/sine"]})
        feed.paused()
        feed.until("run.tail")  # the subscription is live
        env.put_breakpoints(run_id, [watch_bp("w", 's"Synthetic/sine" > 0.5')])
        env.ok(run_id, "continue")
        info = feed.paused()
        document = env.manifest(run_id)
        assert document["status"] == "paused"
        assert document["time"]["t1"] == pytest.approx(info["t"])

        data = env.data(run_id)  # /data while paused: time row, then the sine column
        assert data[0, -1] == pytest.approx(info["t"]) and data.shape[1] == 85
        assert data[1, -1] > 0.5 and data[1, -2] <= 0.5
        csv = env.client.get(f"/api/runs/{run_id}/export.csv", params={"ids": "Synthetic/sine"})
        assert csv.status_code == 200
        lines = csv.text.strip().splitlines()
        assert len(lines) == 1 + 85 and float(lines[-1].split(",")[0]) == pytest.approx(info["t"])

        values = env.client.get(
            f"/api/runs/{run_id}/values", params={"ids": "Synthetic/sine,Synthetic/step"}
        ).json()
        assert values["t"] == pytest.approx(info["t"])
        assert values["values"]["Synthetic/sine"] == pytest.approx(float(data[1, -1]))

        # The live tail reaches the pause time before debug.paused is forwarded.
        order = feed.methods()
        paused_at = len(order) - 1 - order[::-1].index("debug.paused")
        tails = [m["params"] for m in feed.log[:paused_at] if m["method"] == "run.tail"]
        assert tails and tails[-1]["time"][-1] == pytest.approx(info["t"])

        time.sleep(0.15)
        assert env.data(run_id).shape[1] == 85, "nothing is written while paused"
        assert _finish(env, run_id, feed)["status"] == "done"
        assert env.manifest(run_id)["time"]["n"] == 1001
        assert env.data(run_id).shape[1] == 1001


def test_watch_pool_limit_and_expression_errors(env) -> None:
    run_id = env.start(entry=True)
    env.wait_status(run_id, "paused")
    many = [watch_bp(f"w{i}", f's"Synthetic/sine" > {0.01 * i + 2}') for i in range(17)]
    statuses = env.put_breakpoints(run_id, many)
    assert [s["verified"] for s in statuses] == [True] * 16 + [False]
    refused = statuses[16]["diagnostics"][0]
    assert refused["severity"] == "error" and "at most 16 watch breakpoints" in refused["message"]

    statuses = env.put_breakpoints(
        run_id,
        [
            watch_bp("unknown", 's"Nope/x" > 1'),
            watch_bp("name", "foo > 1"),
            watch_bp("notbool", 's"Synthetic/sine" + 1'),
            watch_bp("syntax", 's"Synthetic/sine" >'),
            watch_bp("relative", "sine > 0.5", context="Synthetic"),
            watch_bp("ctx-unknown", "sine > 0.5", context="Other"),
        ],
    )
    codes = {s["id"]: [d["code"] for d in s["diagnostics"]] for s in statuses}
    assert codes == {
        "unknown": ["E003"],
        "name": ["E003"],
        "notbool": ["E004"],
        "syntax": ["E001"],
        "relative": [],
        "ctx-unknown": ["E003"],
    }
    assert all(
        d["scope"] == "watch" for s in statuses for d in s["diagnostics"]
    ), "watch diagnostics carry scope watch"
    assert [s["verified"] for s in statuses] == [False] * 4 + [True, False]


def test_changing_watches_while_paused_never_pauses_spuriously(env) -> None:
    run_id = env.start([watch_bp("w", 's"Synthetic/sine" > 0.5')])
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        assert feed.paused()["breakpointId"] == "w"
        # Already true at this row: a new watch must not fire for the existing state.
        env.put_breakpoints(
            run_id,
            [
                watch_bp("w", 's"Synthetic/sine" > 0.5'),
                watch_bp("late", 's"Synthetic/sine" > 0.4'),
                watch_bp("also", 's"Synthetic/step" >= 0'),
            ],
        )
        env.ok(run_id, "continue")
        done = feed.until("run.done")
        assert done["status"] == "done"
        assert feed.methods().count("debug.paused") == 1
        assert env.manifest(run_id)["debug"]["pauses"] == [{"t": SINE_UP_5, "reason": "breakpoint"}]


def test_watch_hit_count_and_toggle(env) -> None:
    run_id = env.start([{**watch_bp("w", 't > 0.0'), "hitCount": 2}])
    document = env.wait_status(run_id, "done")  # t > 0 crosses once: the second hit never comes
    assert document["debug"]["pauses"] == []


# --------------------------------------------------------------------------- evaluate and values


def test_evaluate(env, schema_validate) -> None:
    run_id = env.start([line_bp("bp1", 13, condition="k == 4")])
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        info = feed.paused()
        frame = {v["name"]: v["value"] for v in info["frame"]["locals"]}

        def evaluate(expr: str, context: str | None = None) -> dict[str, Any]:
            response = env.client.post(
                f"/api/runs/{run_id}/evaluate", json={"expr": expr, "context": context}
            )
            assert response.status_code == 200, response.text
            result = response.json()
            schema_validate("debug", result)
            return result

        assert evaluate("k + 1")["value"] == 5.0
        assert evaluate("v * 2")["value"] == pytest.approx(2 * frame["v"])
        assert evaluate("(k + 2) * 3 - 1 / 4")["value"] == pytest.approx(17.75)
        assert evaluate("t")["value"] == pytest.approx(0.04)
        assert evaluate("k == 4") | {"diagnostics": []} == {
            "value": True, "type": "Bool", "size": [], "unit": None, "diagnostics": [],
        }  # fmt: skip
        assert evaluate("k > 9 || k == 4")["value"] is True
        sine = evaluate('s"Synthetic/sine"')
        assert sine["unit"] == "V" and sine["value"] == pytest.approx(frame["v"])
        assert evaluate("sine", context="Synthetic")["value"] == pytest.approx(frame["v"])
        assert evaluate("abs(0 - 3) + max(1, 2)")["value"] == 5.0
        vector = evaluate("xhat")
        assert vector["size"] == [2] and len(vector["value"]) == 2

        for expr, code in (
            ("nope + 1", "E003"),
            ('s"Nope/x"', "E003"),
            ("k +", "E001"),
            ("k $ 2", "E001"),
            ("1 / 0", "E004"),
            ("on + 1", "E004"),
            ("k && 1", "E004"),
            ("fancy(1)", "E003"),
        ):
            result = evaluate(expr)
            assert [d["code"] for d in result["diagnostics"]] == [code], expr
            assert result["diagnostics"][0]["scope"] == "watch"
            assert result["value"] == 0.0 and result["type"] == "Real"
        assert evaluate("sine")["diagnostics"][0]["code"] == "E003", "no context, no name"


def test_evaluate_without_a_frame_has_no_locals(env) -> None:
    run_id = env.start(entry=True)
    env.wait_status(run_id, "paused")
    ok = env.client.post(f"/api/runs/{run_id}/evaluate", json={"expr": 's"Synthetic/flag" + 1'})
    assert ok.json()["value"] == 1.0
    result = env.client.post(f"/api/runs/{run_id}/evaluate", json={"expr": "k"}).json()
    assert result["diagnostics"][0]["code"] == "E003"


# --------------------------------------------------------------------------- edits


def test_edits_are_recorded_in_the_manifest(env, schema_validate) -> None:
    run_id = env.start([watch_bp("w", 's"Synthetic/sine" > 0.5')])
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        info = feed.paused()
        result = env.ok(run_id, "setParameter", {"name": "Motor1/R", "value": 2.5})
        schema_validate("debug", result["edit"])
        assert result["ok"] is True and result["diagnostics"] == []
        assert result["edit"] == {"t": info["t"], "kind": "parameter", "target": "Motor1/R", "value": 2.5}
        state = env.ok(run_id, "setState", {"id": "Motor1/shaft.f", "value": 12.0})
        assert state["ok"] is True and state["edit"]["kind"] == "state"

        refused = env.ok(run_id, "setState", {"id": "Plant/x_alg", "value": 1.0})
        assert refused["ok"] is False and refused["edit"] is None
        assert refused["diagnostics"][0]["code"] == "E402"
        assert refused["diagnostics"][0]["severity"] == "error"
        assert "algebraic" in refused["diagnostics"][0]["message"]
        bad = env.ok(run_id, "setParameter", {"name": "R", "value": 1.0})
        assert bad["ok"] is False and bad["diagnostics"][0]["code"] == "E003"

        manifest = env.manifest(run_id)
        schema_validate("run-manifest", manifest)
        assert manifest["debug"]["edits"] == [result["edit"], state["edit"]]
        assert _finish(env, run_id, feed)["status"] == "done"
        final = env.manifest(run_id)
        assert final["debug"]["edits"] == [result["edit"], state["edit"]]
        assert final["debug"]["pauses"][0]["reason"] == "breakpoint"


# --------------------------------------------------------------------------- websocket


def test_socket_forwards_paused_and_resumed(env, schema_validate) -> None:
    run_id = env.start([line_bp("bp1", 13, condition="k == 2")], entry=True)
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        socket.send_json({"subscribe": ["Synthetic/sine", "Synthetic/step"]})
        assert feed.paused()["reason"] == "entry"
        env.ok(run_id, "continue")
        assert feed.until("debug.resumed") == {"runId": run_id}
        info = feed.paused()
        assert info["reason"] == "breakpoint" and info["tick"] == 2
        schema_validate("debug", info)
        env.ok(run_id, "continue")
        feed.until("debug.resumed")
        done = feed.until("run.done")
        assert done["status"] == "done"
        methods = feed.methods()
        assert methods.index("debug.paused") < methods.index("debug.resumed") < methods.index(
            "run.done"
        )
        # Each tail ends at (or before) the pause and the last tail reaches the end of the run.
        tails = [m["params"] for m in feed.log if m["method"] == "run.tail"]
        assert tails[-1]["time"][-1] == pytest.approx(1.0)


def test_a_socket_joining_a_paused_run_gets_the_pause_once(env) -> None:
    run_id = env.start([watch_bp("w", 't > 0.1')])
    env.wait_status(run_id, "paused")
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        info = feed.paused()
        assert info["t"] == pytest.approx(0.101)
        env.ok(run_id, "continue")
        feed.until("run.done")
        assert feed.methods().count("debug.paused") == 1


def test_cancel_while_paused_ends_the_run_cancelled(env, schema_validate) -> None:
    run_id = env.start([watch_bp("w", 's"Synthetic/sine" > 0.5')])
    with env.client.websocket_connect(f"/ws/runs/{run_id}") as socket:
        feed = Feed(socket)
        info = feed.paused()
        response = env.client.delete(f"/api/runs/{run_id}")
        assert response.status_code == 200 and response.json() == {"ok": True}
        done = feed.until("run.done")
        assert done["status"] == "cancelled"
    manifest = env.manifest(run_id)
    schema_validate("run-manifest", manifest)
    assert manifest["status"] == "cancelled" and manifest["time"]["t1"] == pytest.approx(info["t"])
    run_dir = env.project / "runs" / run_id
    columns = np.fromfile(run_dir / "columns.f64", dtype="<f8")
    assert columns.size == manifest["time"]["n"] * (1 + len(manifest["signals"]))
    assert env.command(run_id, "continue").status_code == 409


# --------------------------------------------------------------------------- replay and branch


def _edited_run(env: Env) -> tuple[str, list[dict[str, Any]]]:
    """A finished debug run with an edit at 0.0 (entry pause) and one at 0.2."""
    run_id = env.start(entry=True)
    env.wait_status(run_id, "paused")
    first = env.ok(run_id, "setParameter", {"name": "Motor1/R", "value": 3.0})["edit"]
    env.ok(run_id, "runTo", {"t": 0.2})
    env.wait_status(run_id, "paused")
    deadline = time.monotonic() + 5
    while env.manifest(run_id)["time"]["t1"] < 0.2 - 1e-9:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    second = env.ok(run_id, "setParameter", {"name": "Motor1/R", "value": 2.0})["edit"]
    env.ok(run_id, "continue")
    env.wait_status(run_id, "done")
    return run_id, [first, second]


def test_replay_creates_a_normal_run_with_the_parents_edits(env, schema_validate) -> None:
    parent, edits = _edited_run(env)
    response = env.client.post(f"/api/runs/{parent}/replay")
    assert response.status_code == 201, response.text
    new_id = response.json()["runId"]
    assert new_id != parent and (env.project / "runs" / new_id).is_dir()

    with env.client.websocket_connect(f"/ws/runs/{new_id}") as socket:
        feed = Feed(socket)
        assert feed.until("run.done")["status"] == "done"
        assert "debug.paused" not in feed.methods()
    manifest = env.manifest(new_id)
    schema_validate("run-manifest", manifest)
    assert manifest["parentRun"] == parent and "branchAt" not in manifest
    assert manifest["debug"]["edits"] == edits and manifest["debug"]["pauses"] == []
    assert manifest["modelHash"] == env.manifest(parent)["modelHash"]
    assert manifest["id"] == new_id and manifest["model"] == env.manifest(parent)["model"]
    assert np.array_equal(env.data(new_id), env.data(parent))
    assert env.command(new_id, "continue").status_code == 409


def test_branch_replays_to_t_and_pauses(env, schema_validate) -> None:
    parent, edits = _edited_run(env)
    response = env.client.post(f"/api/runs/{parent}/branch", json={"t": 0.1})
    assert response.status_code == 201, response.text
    new_id = response.json()["runId"]

    with env.client.websocket_connect(f"/ws/runs/{new_id}") as socket:
        feed = Feed(socket)
        info = feed.paused()
        assert info["reason"] == "time" and info["t"] == pytest.approx(0.1)
        assert info["breakpointId"] is None and info["runId"] == new_id
        manifest = env.wait_status(new_id, "paused")
        schema_validate("run-manifest", manifest)
        assert manifest["parentRun"] == parent and manifest["branchAt"] == 0.1
        assert manifest["debug"]["edits"] == [edits[0]], "only the edits before t are replayed"
        assert manifest["debug"]["pauses"] == [{"t": pytest.approx(0.1), "reason": "time"}]
        assert env.data(new_id)[0, -1] == pytest.approx(0.1)
        assert np.array_equal(env.data(new_id), env.data(parent)[:, :101])

        # It is a debug run in every respect: edit, evaluate, continue, finish.
        assert env.ok(new_id, "setParameter", {"name": "Motor1/R", "value": 1.0})["ok"] is True
        assert env.client.post(f"/api/runs/{new_id}/evaluate", json={"expr": "t"}).json()[
            "value"
        ] == pytest.approx(0.1)
        env.ok(new_id, "continue")
        assert feed.until("run.done")["status"] == "done"
    assert env.manifest(new_id)["debug"]["edits"][-1]["t"] == pytest.approx(0.1)

    outside = env.client.post(f"/api/runs/{parent}/branch", json={"t": 7.0})
    assert outside.status_code == 422
    assert "outside the run" in outside.json()["message"]


def test_branch_can_be_cancelled_and_listed_in_the_same_project(env) -> None:
    parent, _ = _edited_run(env)
    new_id = env.client.post(f"/api/runs/{parent}/branch", json={"t": 0.3}).json()["runId"]
    env.wait_status(new_id, "paused")
    assert env.client.delete(f"/api/runs/{new_id}").json() == {"ok": True}
    env.wait_status(new_id, "cancelled")
    runs = sorted(path.name for path in (env.project / "runs").iterdir())
    assert runs == sorted([parent, new_id])


def test_replay_of_an_unknown_parent_manifest_fails_cleanly(env) -> None:
    parent, _ = _edited_run(env)
    (env.project / "runs" / parent / "manifest.json").unlink()
    response = env.client.post(f"/api/runs/{parent}/replay")
    assert response.status_code == 422 or response.status_code == 500
    # No half-created run folder is left behind.
    assert [p.name for p in (env.project / "runs").iterdir()] == [parent]


# --------------------------------------------------------------------------- explain


def test_explain(env, schema_validate) -> None:
    body = {"model": _model(), "signal": "Synthetic/step"}
    response = env.client.post("/api/check/explain?project=demo", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    schema_validate("debug", result)
    assert result["signal"] == "Synthetic/step" and result["kind"] == "alias"
    assert result["aliasOf"] == "Synthetic/step_cmd"

    kinds = {}
    for signal in ("Synthetic/sine", "Synthetic/counter", "Synthetic/flag", "Motor1/i", "Other/x"):
        result = env.client.post(
            "/api/check/explain", json={"model": _model(), "signal": signal, "projectDir": str(env.project)}
        ).json()
        schema_validate("debug", result)
        kinds[signal] = result["kind"]
        origin = result["equations"][0]["origin"]
        assert origin["ref"] and origin["range"]["line"] >= 1
    assert kinds == {
        "Synthetic/sine": "observed",
        "Synthetic/counter": "state",
        "Synthetic/flag": "algebraic",
        "Motor1/i": "observed",
        "Other/x": "observed",
    }
    motor = env.client.post(
        "/api/check/explain", json={"model": _model(), "signal": "Motor1/i"}
    ).json()
    assert motor["expression"] and motor["equations"][0]["origin"]["ref"].startswith("stdlib:")
    assert env.client.post("/api/check/explain", json={"model": _model()}).status_code == 422
    unknown = env.client.post("/api/check/explain?project=nope", json=body)
    assert unknown.status_code == 404


# --------------------------------------------------------------------------- pruning


def _fake_run(project: Path, name: str, created: str, **extra: Any) -> None:
    run_dir = project / "runs" / name
    run_dir.mkdir(parents=True)
    manifest = {"id": name, "model": "M", "created": created, "status": "done", **extra}
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_pruning_keeps_the_parent_of_a_kept_run(tmp_path: Path) -> None:
    project = tmp_path / "p"
    _fake_run(project, "root", "2026-01-01T00:00:00Z")
    _fake_run(project, "mid", "2026-01-02T00:00:00Z", parentRun="root", branchAt=0.1)
    _fake_run(project, "plain", "2026-01-03T00:00:00Z")
    _fake_run(project, "branch", "2026-01-04T00:00:00Z", parentRun="mid", branchAt=0.2)
    _fake_run(project, "paused", "2026-01-00T00:00:00Z", status="paused")
    _fake_run(project, "old-orphan", "2026-01-00T12:00:00Z")

    _prune_runs(project, "M", keep=2, active=set())  # keeps 1 old run + the new run
    names = {path.name for path in (project / "runs").iterdir()}
    # "branch" is the newest and stays; it keeps "mid", which keeps "root".
    assert names == {"branch", "mid", "root", "paused"}


def test_pruning_deletes_a_parent_whose_branches_are_gone(tmp_path: Path) -> None:
    project = tmp_path / "p"
    _fake_run(project, "parent", "2026-01-01T00:00:00Z")
    _fake_run(project, "child", "2026-01-02T00:00:00Z", parentRun="parent")
    _fake_run(project, "newest", "2026-01-03T00:00:00Z")
    _prune_runs(project, "M", keep=2, active=set())  # only "newest" stays
    assert {path.name for path in (project / "runs").iterdir()} == {"newest"}

    _fake_run(project, "kept-child", "2026-01-04T00:00:00Z", parentRun="gone")
    _prune_runs(project, "M", keep=5, active=set())
    assert {path.name for path in (project / "runs").iterdir()} == {"newest", "kept-child"}


def test_a_branch_resolves_line_breakpoints_like_its_parent(env) -> None:
    parent, _ = _edited_run(env)
    branch = env.client.post(f"/api/runs/{parent}/branch", json={"t": 0.1}).json()["runId"]
    env.wait_status(branch, "paused")
    statuses = env.put_breakpoints(branch, [line_bp("a", 14), line_bp("b", 9)])
    assert statuses[0]["verified"] is True and statuses[1]["diagnostics"][0]["code"] == "E401"
    with env.client.websocket_connect(f"/ws/runs/{branch}") as socket:
        feed = Feed(socket)
        feed.paused()
        env.ok(branch, "continue")
        info = feed.paused()
        assert info["reason"] == "breakpoint" and info["location"]["range"]["line"] == 14
        assert info["tick"] == 10  # the time pause comes before the partitions of tick 10


# --------------------------------------------------------------------------- scanner, evaluator


def test_source_scanner_on_the_lqg_controller_and_stdlib() -> None:
    source = (REPO / "examples" / "drivetrain-kalman" / "library" / "LQGController.jl").read_text(
        encoding="utf-8"
    )
    lines = source.splitlines()
    info = fake_debug.analyse_source(source)
    header = next(n for n, text in enumerate(lines, 1) if text.strip().startswith("@discrete"))
    texts = [lines[n - 1].strip() for n in info.statements]
    assert info.statements[0] == header + 1 and all(n > header for n in info.statements)
    assert texts[0] == "for j in 1:ny" and texts[-1] == "w_load_hat = xhat[4]"
    assert "if abs(v) > umax" in texts and "end" not in texts
    assert not any(text.startswith("#") or not text for text in texts)
    assert len(texts) == 11  # the 3 loop/if headers and 8 plain statements, no `end`
    assert info.scopes[header] == "@discrete"

    quantizer = (REPO / "julia" / "BGSim" / "stdlib" / "discrete" / "Quantizer.jl").read_text(
        encoding="utf-8"
    )
    assert fake_debug.analyse_source(quantizer).statements == [7]
    motor = (REPO / "julia" / "BGSim" / "stdlib" / "converters" / "DCMotor.jl").read_text(
        encoding="utf-8"
    )
    assert fake_debug.analyse_source(motor).statements == [], "no @discrete code, no statements"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 + 2 * 3", 7.0),
        ("(1 + 2) * 3", 9.0),
        ("-3 + 5", 2.0),
        ("10 / 4", 2.5),
        ("2 > 1", True),
        ("2 >= 3", False),
        ("1 != 2 && 3 == 3", True),
        ("!(1 > 2)", True),
        ("max(1, 5) - min(2, 3)", 3.0),
        ("1e-1 * 10", 1.0),
        ('s"Synthetic/step" * 3', 6.0),
        ("t * 100", 25.0),
        ("k", 7.0),
    ],
)
def test_expression_evaluator(text: str, expected: float | bool) -> None:
    table = fake_debug._Table()
    env = fake_debug.Env(0.25, table.signals(250), {"k": 7.0})
    result = fake_debug.evaluate_node(fake_debug.parse_expression(text), env)
    assert result == expected and type(result) is type(expected)


def test_history_keeps_a_parent_while_its_branch_exists(env, monkeypatch) -> None:
    monkeypatch.setenv("BGSIM_RUN_HISTORY", "1")  # every finished run is a pruning candidate
    parent, _ = _edited_run(env)
    branch = env.client.post(f"/api/runs/{parent}/branch", json={"t": 0.1}).json()["runId"]
    env.wait_status(branch, "paused")
    first = env.start(debug=False)
    env.wait_status(first, "done")
    second = env.start(debug=False)
    env.wait_status(second, "done")
    names = {path.name for path in (env.project / "runs").iterdir()}
    # "first" was pruned; the parent stays because its branch (paused, never pruned) needs it.
    assert names == {parent, branch, second}


