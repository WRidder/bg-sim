"""The assistant's debugger tools on the fake worker: they drive one run with the Debug tab."""

from __future__ import annotations

import time

import pytest
from assistant_support import Bench, make_project
from fastapi.testclient import TestClient

from bgsim_server import runs
from bgsim_server.app import create_app
from bgsim_server.assistant import tools


@pytest.fixture
def bench(fake_settings):
    make_project(fake_settings)
    with TestClient(create_app(fake_settings)) as client:
        yield Bench(client)


def paused_run(bench, **args):
    result = bench.tool("debug_start", **args)
    assert result["status"] == "paused", result
    return result


def test_a_debug_run_starts_paused_and_says_where(bench):
    paused = paused_run(bench)
    assert paused["reason"] == "entry"
    assert paused["t"] == 0
    assert paused["runId"] in bench.s.runs
    announced = [e for e in bench.s.events if e["type"] == "simulation"][-1]
    assert announced["debug"] is True
    bench.tool("stop_run", run_id=paused["runId"])


def test_a_time_breakpoint_pauses_there_and_the_run_can_go_on(bench):
    paused = paused_run(bench, breakpoints=[{"kind": "time", "time": {"t": 0.25}}])
    assert paused["reason"] == "time"
    assert paused["t"] == pytest.approx(0.25, abs=0.05)
    finished = bench.tool("debug_continue", run_id=paused["runId"])
    assert finished["status"] == "done"


def test_a_breakpoint_that_does_not_bind_holds_the_run_at_its_start(bench):
    paused = paused_run(bench, breakpoints=[{"kind": "line", "line": {"ref": "project:Nope", "line": 3}}])
    assert paused["reason"] == "entry"
    status = paused["breakpoints"][0]
    assert status["verified"] is False and status["diagnostics"]
    bench.tool("stop_run", run_id=paused["runId"])


def test_a_run_that_ends_says_no_breakpoint_fired(bench):
    finished = bench.tool("debug_start", breakpoints=[{"kind": "time", "time": {"t": 1e6}}])
    assert finished["status"] == "done" and "no breakpoint fired" in finished["note"]
    assert finished["breakpoints"][0]["verified"] is True


def test_it_can_start_without_a_pause_at_entry(bench):
    assert bench.tool("debug_start", pause_on_entry=False)["status"] == "done"


def test_step_and_run_to_wait_for_the_next_pause(bench):
    paused = paused_run(bench)
    stepped = bench.tool("debug_step", run_id=paused["runId"], granularity="solverStep")
    assert stepped["status"] == "paused" and stepped["reason"] == "step"
    later = bench.tool("debug_run_to", run_id=paused["runId"], t=0.5)
    assert later["t"] == pytest.approx(0.5, abs=0.05)
    bench.tool("stop_run", run_id=paused["runId"])


def test_status_finds_the_paused_run_of_the_project(bench):
    paused = paused_run(bench)
    assert bench.tool("debug_status")["runId"] == paused["runId"]
    assert bench.tool("debug_status", run_id=paused["runId"])["status"] == "paused"
    bench.tool("stop_run", run_id=paused["runId"])
    result, failed = bench.call("debug_continue")
    assert failed and "no run is paused" in result["error"]


def test_a_pause_is_inspected_read_only(bench):
    paused = paused_run(bench)
    assert bench.tool("debug_evaluate", run_id=paused["runId"], expr="1 + 2")["value"] == 3
    values = bench.tool("debug_values", run_id=paused["runId"], ids=["Synthetic/sine"])
    assert "values" in values
    bench.tool("stop_run", run_id=paused["runId"])


def test_a_live_edit_changes_the_run_and_not_the_draft(bench):
    paused = paused_run(bench)
    edited = bench.tool("debug_set_parameter", run_id=paused["runId"], name="Motor1/R", value=2.0)
    assert edited["edit"]["kind"] == "parameter"
    assert not bench.s.draft.changed
    finished = bench.tool("debug_continue", run_id=paused["runId"])
    assert finished["status"] == "done"
    replayed = bench.tool("debug_replay", run_id=paused["runId"])
    assert replayed["status"] == "done" and replayed["runId"] != paused["runId"]


def test_rewind_branches_and_pauses_there(bench):
    paused = paused_run(bench)
    finished = bench.tool("debug_continue", run_id=paused["runId"])
    branch = bench.tool("debug_rewind", run_id=finished["runId"], t=0.5)
    assert branch["status"] == "paused" and branch["runId"] != paused["runId"]
    assert branch["t"] == pytest.approx(0.5, abs=0.05)
    bench.tool("stop_run", run_id=branch["runId"])


def test_breakpoints_can_be_replaced_during_a_run(bench):
    paused = paused_run(bench)
    result = bench.tool(
        "debug_set_breakpoints", run_id=paused["runId"], breakpoints=[{"kind": "time", "time": {"t": 0.5}}],
    )
    assert result["breakpoints"][0]["id"] == "bp1"
    assert bench.tool("debug_continue", run_id=paused["runId"])["t"] == pytest.approx(0.5, abs=0.05)
    bench.tool("stop_run", run_id=paused["runId"])


def test_what_the_worker_refuses_is_an_error_and_not_a_value(bench):
    paused = paused_run(bench)
    result, failed = bench.call("debug_evaluate", run_id=paused["runId"], expr="s\"Nope/x\"")
    assert failed and result["diagnostics"][0]["severity"] == "error"
    result, failed = bench.call("debug_set_parameter", run_id=paused["runId"], name="R", value=1.0)
    assert failed and result["diagnostics"][0]["code"] == "E003"
    bench.tool("stop_run", run_id=paused["runId"])


def test_a_bad_breakpoint_is_refused(bench):
    result, failed = bench.call("debug_start", breakpoints=[{"kind": "nonsense"}])
    assert failed and "error" in result


def test_a_conflict_is_a_result_the_model_can_act_on(bench):
    paused = paused_run(bench)
    bench.tool("debug_continue", run_id=paused["runId"])
    result, failed = bench.call("debug_step", run_id=paused["runId"], granularity="tick")
    assert failed and "not active" in result["error"]


def test_every_debug_tool_needs_a_project_and_offers_no_other(bench):
    names = [name for name in tools.TOOLS if name.startswith("debug_")]
    assert len(names) == 13
    for name in names:
        definition = tools.TOOLS[name]
        assert definition.needs_project and "project" not in definition.schema["properties"]


def test_rewinding_a_paused_run_stops_it(bench):
    paused = paused_run(bench)
    bench.tool("debug_run_to", run_id=paused["runId"], t=0.75)
    branch = bench.tool("debug_rewind", run_id=paused["runId"], t=0.25)
    assert branch["status"] == "paused" and branch["t"] == pytest.approx(0.25, abs=0.05)
    assert bench.tool("debug_status")["runId"] == branch["runId"]
    bench.tool("stop_run", run_id=branch["runId"])


def test_closing_the_chat_stops_its_paused_run(bench):
    paused = paused_run(bench)
    manager = bench.client.app.state.assistant
    manager.sessions[bench.s.id] = bench.s
    manager.close(bench.s.id)
    state = runs._store_for(bench.client.app).get(paused["runId"])
    deadline = time.monotonic() + 10
    while state.done is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert state.done is not None
