"""Code cells on the fake worker (the interpreter has its own tests in julia/BGSim/test/test_cells.jl),
diagnostics, results and what the model is told about a selection."""

from __future__ import annotations

import json

import pytest
from assistant_support import Bench, make_project
from fastapi.testclient import TestClient

from bgsim_server.app import create_app
from bgsim_server.assistant import selection
from bgsim_server.assistant.draft import Draft


@pytest.fixture
def bench(fake_settings):
    make_project(fake_settings)
    with TestClient(create_app(fake_settings)) as client:
        yield Bench(client)


def test_a_cell_reads_the_latest_run_and_shows_figures(bench):
    run_id = bench.tool("run_simulation", t_end=0.1, wait_s=30)["runId"]
    out = bench.tool("run_code", code='plot("x", t, s"Synthetic/step")\ns"Motor1/R"')
    assert out["ok"] and out["runId"] == run_id
    assert out["shown"] == ["table: Size", "chart: Fake"]
    event = bench.events("code")[-1]
    assert event["runId"] == run_id and event["output"]
    kinds = [e["figure"]["kind"] for e in bench.events("figure")]
    assert kinds == ["table", "chart"]
    chart = bench.events("figure")[-1]["figure"]
    assert chart["series"][0]["name"] == "Synthetic/step" and chart["x"]


def test_a_cell_without_a_run_still_has_the_model(bench):
    out = bench.tool("run_code", code="Kp * 2")
    assert out["ok"] and out["runId"] is None


def test_a_failing_cell_is_a_result_for_the_model(bench):
    out = bench.tool("run_code", code="fail")
    assert out["ok"] is False
    assert out["diagnostics"][0]["code"] == "E004"
    assert bench.events("code")[-1]["error"] == "the cell failed: fake"


def test_no_python_tool_is_left():
    from bgsim_server.assistant import tools

    assert "Python" not in tools.TOOLS["run_code"].description


def test_diagnostics_cover_model_blocks_and_the_latest_run(bench):
    bench.tool("run_simulation", t_end=0.1, wait_s=30)
    found = bench.tool("get_diagnostics")
    assert found["model"]["diagnostics"]
    assert found["latestRun"]["status"] == "done"
    assert "source" in json.dumps(found["model"]["diagnostics"])


def test_worker_log_tail(bench):
    log = bench.s.ctx.settings.worker_log
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("one\ntwo\nthree\n", encoding="utf-8")
    assert bench.tool("worker_log", lines=2)["lines"] == ["two", "three"]


def test_results_of_a_run(bench):
    run_id = bench.tool("run_simulation", t_end=0.1, wait_s=30)["runId"]
    status = bench.tool("run_status")
    assert status["runId"] == run_id and status["settings"]["t_end"] == 0.1
    sampled = bench.tool("sample_signals", run_id=run_id, signals=["Synthetic/step"], times=[0.0, 0.05])
    assert sampled["time"] == [0.0, 0.05]
    assert "no finished run" in Bench(bench.client, model="other").refused("run_status", model="other")


# ---------------------------------------------------------------------------- selections


def test_selection_text(fake_settings):
    make_project(fake_settings)
    with TestClient(create_app(fake_settings)) as client:
        draft = Draft(client.app.state.assistant.ctx.store, "demo")
        text = selection.describe(draft, [
            {"kind": "diagram", "model": "motor", "path": [], "nodes": ["Motor1", "Gone"],
             "connections": ["Step1.y -> V1.u"]},
            {"kind": "code", "source": "project:Foo", "text": "x = 1", "fromLine": 3, "toLine": 3},
            {"kind": "doc", "model": None, "page": "intro", "text": "some words"},
        ])
    assert text.startswith("[Selected by the user:")
    assert "Motor1 (DCMotor" in text
    assert "Gone (not in the draft)" in text
    assert "Step1.y -> V1.u" in text
    assert "lines 3-3" in text and "x = 1" in text
    assert "project docs" in text and "some words" in text


def test_no_selection_adds_nothing():
    assert selection.describe(None, []) == ""
