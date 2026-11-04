"""The assistant's tools on the fake worker: editing the draft, reading other projects and docs
read-only, simulating the draft, measuring, and the question gate."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from assistant_support import Bench, make_project, tree
from fastapi.testclient import TestClient

from bgsim_server import docs
from bgsim_server.app import create_app
from bgsim_server.assistant import modelops, tools


@pytest.fixture
def client(fake_settings):
    make_project(fake_settings)
    with TestClient(create_app(fake_settings)) as test_client:
        yield test_client


@pytest.fixture
def bench(client):
    return Bench(client)


def project_dir(client, name: str = "demo"):
    return client.app.state.settings.projects_root / name


def test_every_tool_has_a_closed_schema():
    assert len(tools.TOOLS) >= 40
    for definition in tools.TOOLS.values():
        assert definition.description
        assert definition.schema["additionalProperties"] is False


def test_only_read_tools_take_a_project():
    """Other projects are read-only by construction: no edit tool can name one."""
    for definition in tools.TOOLS.values():
        if definition.edits:
            assert "project" not in definition.schema["properties"], definition.name


def test_edits_stay_in_the_draft_until_apply(client, bench):
    before = tree(project_dir(client))
    bench.tool("add_block", name="R1", ref="stdlib:bondgraph/R", params={"r": 2})
    bench.tool("add_block", name="J", junction="1")
    assert bench.tool("connect", **{"from": "J", "to": "R1.p"})["kind"] == "bond"
    assert tree(project_dir(client)) == before
    proposal = bench.events("proposal")[-1]["proposal"]
    assert proposal["changed"] is True
    assert [f["name"] for f in proposal["files"]] == ["motor"]
    described = bench.tool("get_model")
    names = {node["name"] for node in described["nodes"]}
    assert {"R1", "J"} <= names


def test_add_block_refuses_what_the_block_does_not_have(bench):
    assert "no block" in bench.refused("add_block", name="X", ref="stdlib:nope/Nope")
    message = bench.refused("add_block", name="X", ref="stdlib:bondgraph/R", params={"q": 1})
    assert "no parameter" in message and "'r'" in message
    assert "exactly one" in bench.refused("add_block", name="X")


def test_a_refused_edit_leaves_the_draft_alone(bench):
    bench.tool("add_block", name="R1", ref="stdlib:bondgraph/R")
    held = json.dumps(bench.s.draft.models["motor"], sort_keys=True)
    bench.refused("connect", **{"from": "R1.p", "to": "Nobody.p"})
    assert json.dumps(bench.s.draft.models["motor"], sort_keys=True) == held


def test_undoing_an_edit_empties_the_proposal(bench):
    bench.tool("add_block", name="R1", ref="stdlib:bondgraph/R")
    assert bench.s.draft.changed
    bench.tool("remove_block", node="R1")
    assert not bench.s.draft.changed


def test_subsystem_with_exposed_port(bench):
    bench.tool("add_block", name="Drive", subsystem=True)
    bench.tool("add_block", name="J", parent="Drive", junction="0")
    bench.tool("expose_port", inner="Drive/J", name="shaft", domain="rotational")
    assert bench.tool("get_model", subsystem="Drive")["nodes"][0]["name"] == "J"


def test_create_empty_and_delete(client, bench):
    assert bench.tool("create_model", name="fresh")["created"] == "fresh"
    assert "fresh" in bench.tool("list_models")["models"]
    assert "already exists" in bench.refused("create_model", name="motor")
    assert "open in the editor" in bench.refused("delete_model", model="motor")
    bench.tool("delete_model", model="fresh")
    assert not bench.s.draft.changed


def test_globals_and_settings(bench):
    bench.tool("set_globals", set=[{"name": "k", "value": 3, "unit": "N/m"}])
    bench.tool("set_settings", t_end=2.5)
    document = bench.tool("get_model", raw=True)["document"]
    assert document["parameters"][0]["value"] == "3"
    assert document["settings"]["t_end"] == 2.5


def test_replace_model_is_validated(bench):
    assert "model" in bench.refused("replace_model", document={"format": "nonsense"}).lower()


def test_library_block_in_the_draft(client, bench):
    source = "@block Foo begin\nend\n"
    assert bench.tool("write_library_block", name="Foo", source=source)["ref"] == "project:Foo"
    assert bench.tool("get_block_source", ref="project:Foo")["source"] == source
    assert "Foo" in bench.tool("list_models")["library"]
    assert not (project_dir(client) / "library" / "Foo.jl").exists()


# ---------------------------------------------------------------------------- layout


def positions(bench, model="motor"):
    document = bench.s.draft.model(model)
    return {n["name"]: dict(n["position"]) for n in document["diagram"]["nodes"]}


def test_auto_layout_keeps_the_users_layout(bench):
    before = positions(bench)
    bench.tool("add_block", name="R1", ref="stdlib:bondgraph/R")
    bench.tool("add_block", name="J", junction="1")
    bench.tool("connect", **{"from": "J", "to": "R1.p"})
    result = bench.tool("auto_layout")
    assert set(result["placed"]) == {"R1", "J"} and result["kept"] == len(before)
    assert result["overlapping"] == []
    after = positions(bench)
    assert {k: after[k] for k in before} == before


def test_whole_layout_is_explicit(bench):
    before = positions(bench)
    assert set(bench.tool("auto_layout", whole=True)["placed"]) == set(before)
    assert positions(bench) != before


def test_new_blocks_land_beside_their_neighbour(bench):
    bench.tool("add_block", name="R1", ref="stdlib:bondgraph/R", near="Motor1", side="below")
    spots = positions(bench)
    assert spots["R1"]["x"] == spots["Motor1"]["x"]
    assert spots["R1"]["y"] > spots["Motor1"]["y"]
    assert "no node" in bench.refused("add_block", name="R2", ref="stdlib:bondgraph/R", near="Nobody")


def test_a_new_diagram_gets_a_full_layout(bench):
    bench.tool("create_model", name="fresh")
    bench.tool("add_block", model="fresh", name="J", junction="1")
    bench.tool("add_block", model="fresh", name="Source", ref="stdlib:bondgraph/Se")
    for element in ("R1", "R2"):
        bench.tool("add_block", model="fresh", name=element, ref="stdlib:bondgraph/R")
        bench.tool("connect", model="fresh", **{"from": "J", "to": f"{element}.p"})
    bench.tool("connect", model="fresh", **{"from": "Source.p", "to": "J"})
    assert bench.tool("auto_layout", model="fresh")["overlapping"] == []
    spots = positions(bench, "fresh")
    assert spots["Source"]["x"] < spots["J"]["x"]
    assert spots["R1"]["y"] < spots["J"]["y"] < spots["R2"]["y"]  # hung off the junction
    assert spots["R1"]["x"] == spots["J"]["x"]


def test_the_model_reports_its_layout(bench):
    described = bench.tool("get_model")
    assert described["nodes"][0]["at"]
    assert described["layout"]["flow"] in ("right", "left", "up", "down")


# ---------------------------------------------------------------------------- other projects


def test_other_projects_are_listed_and_read(client, bench):
    make_project(client.app.state.settings, "other", "pendulum")
    listed = bench.tool("list_projects")
    assert listed["current"] == "demo"
    assert {p["name"] for p in listed["projects"]} == {"demo", "other"}
    assert any(e["project"] == "example:dc-motor" for e in listed["examples"])
    assert bench.tool("list_models", project="other")["models"] == ["pendulum"]
    assert bench.tool("get_model", model="pendulum", project="other")["name"] == "pendulum"
    assert "other" not in bench.tool("list_models")["models"]


def test_examples_are_read_like_projects(bench):
    models = bench.tool("list_models", project="example:dc-motor")["models"]
    assert models
    assert bench.tool("get_model", model=models[0], project="example:dc-motor", raw=True)["document"]


def test_an_unknown_project_is_a_clean_refusal(bench):
    assert "nothere" in bench.refused("list_models", project="nothere")
    assert "'..'" in bench.refused("list_models", project="..") or bench.refused(
        "list_models", project=".."
    )


def test_copying_from_another_project_brings_its_blocks(client, bench):
    other = make_project(client.app.state.settings, "other", "pendulum")
    (other / "library").mkdir()
    (other / "library" / "Spring.jl").write_text("@block Spring begin\nend\n", encoding="utf-8")
    document = json.loads((other / "models" / "pendulum.bgmodel.json").read_text(encoding="utf-8"))
    document["diagram"]["nodes"][0]["block"] = {"ref": "project:Spring"}
    (other / "models" / "pendulum.bgmodel.json").write_text(json.dumps(document), encoding="utf-8")
    before = tree(other)
    made = bench.tool("create_model", name="copy", from_model="pendulum", from_project="other")
    assert made["copiedBlocks"] == ["Spring"]
    assert bench.tool("get_block_source", ref="project:Spring")["source"].startswith("@block")
    assert tree(other) == before


def test_docs_of_other_projects_read_only(client, bench):
    settings = client.app.state.settings
    make_project(settings, "other", "pendulum")
    store = client.app.state.assistant.ctx.store
    docs.write_page_text(store, "other", None, "overview", "Overview", "project notes")
    docs.write_page_text(store, "other", "pendulum", "theory", "Theory", "model notes")
    before = tree(project_dir(client, "other"))

    listed = bench.tool("list_docs", project="other")
    assert listed["projectDocs"][0]["id"] == "overview"
    assert listed["models"]["pendulum"][0]["id"] == "theory"
    assert bench.tool("list_docs", project="other", model="pendulum")["pages"][0]["id"] == "theory"
    assert bench.tool("read_doc", page="overview", project="other")["text"] == "project notes"
    assert bench.tool("read_doc", page="theory", model="pendulum", project="other")["text"] == "model notes"
    assert tree(project_dir(client, "other")) == before


def test_docs_of_an_example(bench):
    listed = bench.tool("list_docs", project="example:dc-motor")
    assert "models" in listed


def test_draft_docs(client, bench):
    bench.tool("write_doc", page="notes", title="Notes", text="draft text", model="motor")
    assert bench.tool("read_doc", page="notes", model="motor")["text"] == "draft text"
    assert not (project_dir(client) / "docs").exists()


# ---------------------------------------------------------------------------- simulation


def test_simulating_the_draft(client, bench):
    bench.tool("add_block", name="R1", ref="stdlib:bondgraph/R")
    run = bench.tool("run_simulation", t_end=0.1, wait_s=30)
    assert run["status"] == "done"
    event = bench.events("simulation")[-1]
    assert event["runId"] == run["runId"] and event["draft"] is True
    assert bench.tool("run_status", run_id=run["runId"])["status"] == "done"
    assert bench.s.draft.model("motor")["settings"]["t_end"] != 0.1  # that run only

    found = bench.tool("list_signals", run_id=run["runId"], filter="sine")
    assert found["signals"][0]["id"] == "Synthetic/sine"
    stats = bench.tool("signal_stats", run_id=run["runId"], signals=["Synthetic/sine"])
    assert "max" in stats["signals"]["Synthetic/sine"]
    sampled = bench.tool("sample_signals", run_id=run["runId"], signals=["Synthetic/step"], points=5)
    assert len(sampled["time"]) == 5
    metrics = bench.tool("step_metrics", run_id=run["runId"], signal="Synthetic/step")
    assert metrics
    compared = bench.tool(
        "compare_runs", run_a=run["runId"], run_b=run["runId"], signals=["Synthetic/sine"]
    )
    assert compared["signals"]["Synthetic/sine"]["rmsDifference"] == 0
    assert "did not record" in bench.refused(
        "signal_stats", run_id=run["runId"], signals=["Nope/x"]
    )
    assert run["runId"] in {r["runId"] for r in bench.tool("list_runs")["runs"]}


def test_a_sweep_runs_each_value(bench):
    swept = bench.tool(
        "parameter_sweep", target="Motor1/R", values=[1.0, 2.0], signals=["Synthetic/sine"], t_end=0.1
    )
    assert [row["status"] for row in swept["rows"]] == ["done", "done"]
    assert len({row["runId"] for row in swept["rows"]}) == 2


def test_figures_reach_the_stream(bench):
    run = bench.tool("run_simulation", t_end=0.1, wait_s=30)
    bench.tool("plot_signals", title="Sine", run_id=run["runId"], signals=["Synthetic/sine"])
    bench.tool("show_diagram")
    figures = [event["figure"] for event in bench.events("figure")]
    assert [f["kind"] for f in figures] == ["plot", "diagram"]
    assert figures[1]["nodes"] and figures[1]["edges"]
    assert "did not record" in bench.refused(
        "plot_signals", title="x", run_id=run["runId"], signals=["Nope/x"]
    )


def test_check_model_records_the_verdict(bench):
    bench.tool("add_block", name="R1", ref="stdlib:bondgraph/R")
    assert bench.s.proposal()["checked"] is False
    checked = bench.tool("check_model")
    assert "errors" in checked
    bench.tool("add_block", name="R2", ref="stdlib:bondgraph/R")
    assert bench.s.proposal()["checked"] is False  # a check holds for the state it saw


# ---------------------------------------------------------------------------- reference


def test_reference_search_and_read(bench):
    sections = bench.tool("search_reference", query="causality")["sections"]
    assert sections
    assert bench.tool("read_reference", section=sections[0]["id"])["text"]
    assert "no section" in bench.refused("read_reference", section="spec#no-such-section")


def test_block_search_and_describe(bench):
    found = bench.tool("search_blocks", query="R")["blocks"]
    assert found
    described = bench.tool("describe_block", ref="stdlib:bondgraph/R")
    assert [p["name"] for p in described["parameters"]] == ["r"]
    assert "source" not in described
    assert "@" in bench.tool("get_block_source", ref="stdlib:bondgraph/R")["source"]


# ---------------------------------------------------------------------------- questions


QUESTION = [{"id": "a", "prompt": "Which?", "kind": "single", "options": [
    {"value": "x", "label": "X"}, {"value": "y", "label": "Y"},
]}]


def test_asking_blocks_other_tools_until_answered(bench):
    assert bench.tool("ask_user", questions=QUESTION)["status"] == "shown"
    assert bench.events("question")[-1]["question"]["questions"][0]["id"] == "a"
    assert "not answered" in bench.refused("get_model")


@pytest.mark.parametrize(
    "questions, message",
    [
        ([{"id": "a", "prompt": "?", "kind": "single", "options": [{"value": "x", "label": "X"}]}],
         "two options"),
        ([*QUESTION, *QUESTION], "twice"),
        ([{"id": "a", "prompt": "?", "kind": "single", "options": [
            {"value": "x", "label": "X"}, {"value": "x", "label": "Y"}]}], "repeats"),
    ],
)
def test_bad_questions_are_refused(bench, questions, message):
    assert message in bench.refused("ask_user", questions=questions)


def test_bad_arguments_are_a_result_not_a_crash(bench):
    assert "bad arguments" in bench.refused("add_block", name=3)
    assert "unknown tool" in bench.refused("rm_rf")


def test_events_and_audit(bench):
    bench.tool("list_models")
    bench.refused("describe_block", ref="stdlib:nope/Nope")
    calls = bench.events("tool_call")
    assert [c["isError"] for c in calls] == [False, True]
    time.sleep(0)
    log = bench.s.audit.path.read_text(encoding="utf-8")
    assert '"name": "describe_block"' in log and bench.s.token not in log


SCENE = """<?xml version="1.0"?>
<sdf version="1.9">
  <model name="arm">
    <link name="base">
      <visual name="post"><geometry><box><size>0.1 0.1 1</size></box></geometry></visual>
    </link>
    <link name="tip">
      <visual name="bar"><geometry><cylinder><radius>0.02</radius><length>1</length></cylinder></geometry></visual>
    </link>
    <joint name="shoulder" type="revolute"><parent>base</parent><child>tip</child></joint>
  </model>
</sdf>
"""


def cards(bench, *items):
    return bench.call("set_model_field", field="dashboard", value={"cards": list(items)})


def card(kind, **more):
    return {"id": kind, "kind": kind, "size": "1x1", "title": kind, **more}


def test_a_dashboard_reads_back(bench):
    bench.tool("set_globals", set=[{"name": "k", "value": 3}])
    result = bench.tool(
        "set_model_field", field="dashboard",
        value={"autoRerun": True, "cards": [
            card("plot", signals=["Motor/w"]),
            card("slider", parameter="global:k", options={"min": 0, "max": 10, "step": 1}),
            card("text", options={"text": "Drag k."}),
        ]},
    )
    assert result["cards"][1] == {"id": "slider", "kind": "slider", "bound": "global:k"}
    back = bench.tool("get_model", part="dashboard")["dashboard"]
    assert back["autoRerun"] is True
    assert back["cards"][1]["parameter"] == "global:k"


def test_a_card_with_the_wrong_binding_is_refused(bench):
    bench.tool("set_globals", set=[{"name": "k", "value": 3}])
    result, is_error = cards(bench, card("slider", signals=["Motor/w"]))
    assert is_error
    assert any("input cards bind through `parameter`" in p for p in result["problems"])
    result, is_error = cards(bench, card("gauge", parameter="global:k"))
    assert is_error
    assert any("display cards bind through `signals`" in p for p in result["problems"])
    result, is_error = cards(bench, card("knob"))
    assert is_error
    assert not bench.s.draft.changed or "dashboard" not in bench.s.draft.models.get("motor", {})


def test_a_card_on_something_missing_is_refused(bench):
    result, is_error = cards(bench, card("slider", parameter="global:nothing"))
    assert is_error and any("set_globals" in p for p in result["problems"])
    result, is_error = cards(bench, card("number", parameter="Nobody/k"))
    assert is_error and any("Nobody" in p for p in result["problems"])


def test_every_shipped_dashboard_passes_the_card_check():
    examples = Path(__file__).resolve().parents[2] / "examples"
    seen = 0
    for path in examples.glob("*/models/*.bgmodel.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        if (document.get("dashboard") or {}).get("cards"):
            seen += 1
            assert modelops.card_problems(document) == [], path.name
    assert seen > 0


def test_a_scene_goes_through_the_draft(client, bench):
    written = bench.tool("write_scene", file="arm.sdf", text=SCENE)
    assert written["joints"] == ["shoulder"]
    assert written["links"] == ["base", "tip"]
    assert not (project_dir(client) / "scenes" / "arm.sdf").exists()
    assert bench.tool("list_scenes")["scenes"] == ["arm.sdf"]
    assert bench.tool("read_scene", file="arm.sdf")["text"] == SCENE
    assert bench.s.proposal()["files"][0] == {"kind": "scene", "name": "arm.sdf", "change": "added", "rows": []}
    bench.tool("set_model_field", field="scene", value={"file": "scenes/arm.sdf"})
    result = bench.tool(
        "set_model_field", field="bindings",
        value=[{"target": "joint:shoulder", "property": "position", "signal": "Motor/w"},
               {"target": "joint:elbow", "property": "position", "signal": "Motor/w"}],
    )
    assert len(result["warnings"]) == 1 and "joint:elbow" in result["warnings"][0]
    assert bench.s.draft.apply(None, "session")["applied"][-1] == "scene:arm.sdf"
    assert (project_dir(client) / "scenes" / "arm.sdf").read_text(encoding="utf-8") == SCENE
    assert not bench.s.draft.scenes


def test_a_scene_field_needs_the_file(bench):
    message = bench.refused("set_model_field", field="scene", value={"file": "scenes/none.sdf"})
    assert "write_scene" in message


@pytest.mark.parametrize(("text", "says"), [
    ("<sdf><model", "well-formed"),
    ("<scene/>", "<sdf>"),
    ("<sdf/>", "no <model>"),
    ('<sdf><model name="a"><link name="b"/></model></sdf>', "no <visual>"),
    ('<!DOCTYPE x [<!ENTITY a "b">]><sdf/>', "DOCTYPE"),
    (SCENE.replace("<box><size>0.1 0.1 1</size></box>", "<torus/>"), "<geometry>"),
    (SCENE.replace('type="revolute"', 'type="gearbox"'), "type must be"),
])
def test_a_scene_the_viewer_cannot_draw_is_refused(bench, text, says):
    assert says in bench.refused("write_scene", file="arm.sdf", text=text)
    assert not bench.s.draft.changed


def test_a_scene_name_cannot_leave_the_folder(bench):
    assert "invalid scene file name" in bench.refused("write_scene", file="../arm.sdf", text=SCENE)
    assert "invalid scene file name" in bench.refused("read_scene", file="../../secret.sdf")


def test_a_discarded_scene_is_gone(client, bench):
    bench.tool("write_scene", file="arm.sdf", text=SCENE)
    bench.s.discard()
    assert bench.tool("list_scenes")["scenes"] == []
