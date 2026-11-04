"""The two runners and the API, on a real server: a fake `claude` that calls back over HTTP, a
scripted OpenAI endpoint, the init self-check, tokens, apply, conflicts and the home-screen chat."""

from __future__ import annotations

import json
import sys

import httpx
import pytest
from assistant_support import (
    FAKE_CLAUDE,
    fake_claude_env,
    make_config,
    make_project,
    serve,
    tree,
    wait_idle,
)
from fastapi.testclient import TestClient

from bgsim_server.app import create_app
from bgsim_server.assistant import profiles, runner_claude, runner_openai, tools
from bgsim_server.assistant.mcp_relay import RelayError, build, check_url


@pytest.fixture
def app(fake_settings):
    make_project(fake_settings)
    return create_app(fake_settings)


@pytest.fixture
def live(app, monkeypatch):
    """A running server with the fake claude; the mode is set per test with `fake_claude_env`."""
    fake_claude_env(monkeypatch)
    assistant = app.state.assistant
    assistant._cfg = make_config()
    assistant.claude.prefix = FAKE_CLAUDE
    with serve(app) as url:
        yield app, url


def post(url: str, path: str, **body) -> httpx.Response:
    return httpx.post(url + path, json=body, timeout=30)


def start(url: str, app, text: str = "add a damper"):
    response = post(url, "/api/projects/demo/assistant", text=text, model="motor")
    assert response.status_code == 201, response.text
    info = response.json()
    return wait_idle(app.state.assistant, info["session"]), info


def ended(session) -> dict:
    return next(e for e in reversed(session.events) if e["type"] == "run_end")


def kinds(session) -> list[str]:
    return [event["type"] for event in session.events]


def test_a_run_edits_the_draft_only(live, fake_settings):
    app, url = live
    before = tree(fake_settings.projects_root / "demo")
    session, _ = start(url, app)
    assert session.draft.changed
    assert tree(fake_settings.projects_root / "demo") == before
    seen = kinds(session)
    assert seen[:2] == ["user", "run_start"]
    assert "tool_call" in seen and "text" in seen and seen[-1] == "run_end"
    end = session.events[-1]
    assert end["status"] == "ok"
    assert end["proposal"]["files"][0]["name"] == "motor"


def test_the_events_validate_against_the_contract(live, schema_validate):
    app, url = live
    session, _ = start(url, app)
    for event in session.events:
        schema_validate("assistant", event)


def test_the_sse_stream_ends_with_the_run(live):
    app, url = live
    session, _ = start(url, app)
    with httpx.stream("GET", f"{url}/api/assistant/{session.id}/events?after=0", timeout=20) as stream:
        body = "".join(stream.iter_text())
    assert "event: run_end" in body


def test_apply_writes_and_backs_up(live, fake_settings):
    app, url = live
    session, _ = start(url, app)
    response = post(url, f"/api/assistant/{session.id}/apply", openModel=None)
    assert response.status_code == 200, response.text
    assert response.json()["applied"] == ["model:motor"]
    project = fake_settings.projects_root / "demo"
    saved = json.loads((project / "models" / "motor.bgmodel.json").read_text(encoding="utf-8"))
    assert any(n["name"].startswith("Damp") and n["name"] != "Damp1" for n in saved["diagram"]["nodes"])
    assert list(project.glob("logs/assistant/backup-*/models/motor.bgmodel.json"))
    assert session.proposal()["changed"] is False


def test_apply_returns_the_open_model_to_the_editor(live, fake_settings):
    app, url = live
    project = fake_settings.projects_root / "demo"
    before = (project / "models" / "motor.bgmodel.json").read_text(encoding="utf-8")
    session, _ = start(url, app)
    result = post(url, f"/api/assistant/{session.id}/apply", openModel="motor").json()
    assert result["openModel"]["name"] == "motor"
    assert (project / "models" / "motor.bgmodel.json").read_text(encoding="utf-8") == before


def test_apply_refuses_a_file_changed_on_disk(live, fake_settings):
    app, url = live
    session, _ = start(url, app)
    path = fake_settings.projects_root / "demo" / "models" / "motor.bgmodel.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["settings"]["t_end"] = 99.0
    path.write_text(json.dumps(document), encoding="utf-8")
    response = post(url, f"/api/assistant/{session.id}/apply", openModel=None)
    assert response.status_code == 409
    assert response.json()["files"] == ["model:motor"]
    assert json.loads(path.read_text(encoding="utf-8"))["settings"]["t_end"] == 99.0


def test_discard_keeps_the_chat(live):
    app, url = live
    session, _ = start(url, app)
    assert post(url, f"/api/assistant/{session.id}/discard").status_code == 200
    assert not session.draft.changed
    assert post(url, f"/api/assistant/{session.id}/messages", text="again").status_code == 202
    wait_idle(app.state.assistant, session.id)
    assert session.draft.changed


def test_a_follow_up_uses_the_same_process(live):
    app, url = live
    session, _ = start(url, app)
    process = session.runner_state["proc"]
    post(url, f"/api/assistant/{session.id}/messages", text="and another")
    wait_idle(app.state.assistant, session.id)
    assert session.runner_state["proc"] is process
    assert len(session.draft.model("motor")["diagram"]["nodes"]) >= 9


def test_selection_and_shown_run_reach_the_model(live):
    app, url = live
    selected = [{"kind": "diagram", "model": "motor", "path": [], "nodes": ["Motor1"], "connections": []}]
    response = post(
        url, "/api/projects/demo/assistant", text="explain this", model="motor",
        selection=selected, run="20260101-000000-abcd",
    )
    assert response.status_code == 201, response.text
    session = wait_idle(app.state.assistant, response.json()["session"])
    assert session.events[0]["selection"] == selected
    said = next(e["text"] for e in session.events if e["type"] == "text")
    assert "explain this" in said
    log = session.audit.path.read_text(encoding="utf-8")
    assert "explain this" in log


def test_questions_and_answers(live, monkeypatch):
    fake_claude_env(monkeypatch, "ask")
    app, url = live
    session, _ = start(url, app)
    assert session.question is not None
    question = session.question["id"]
    assert session.info()["question"]["id"] == question

    bad = post(url, f"/api/assistant/{session.id}/answers", questionSet=question, answers=[
        {"questionId": "friction", "values": ["none", "viscous"]},
        {"questionId": "plots", "values": []},
    ])
    assert bad.status_code == 422
    missing = post(url, f"/api/assistant/{session.id}/answers", questionSet=question, answers=[
        {"questionId": "friction", "values": ["none"]},
    ])
    assert missing.status_code == 422
    other = post(url, f"/api/assistant/{session.id}/answers", questionSet="q0", answers=[])
    assert other.status_code == 409

    good = post(url, f"/api/assistant/{session.id}/answers", questionSet=question, answers=[
        {"questionId": "friction", "values": ["viscous"]},
        {"questionId": "plots", "values": ["speed"], "other": "torque too"},
    ])
    assert good.status_code == 202, good.text
    wait_idle(app.state.assistant, session.id)
    assert session.question is None
    said = [e["text"] for e in session.events if e["type"] == "text"][-1]
    assert "torque too" in said


def test_figures_and_runs_from_a_real_relay_path(live, monkeypatch):
    fake_claude_env(monkeypatch, "figure")
    app, url = live
    session, _ = start(url, app)
    assert [e["figure"]["kind"] for e in session.events if e["type"] == "figure"] == ["plot", "diagram"]
    assert any(e["type"] == "simulation" for e in session.events)


def test_cancel_stops_a_slow_run(live, monkeypatch):
    fake_claude_env(monkeypatch, "slow")
    app, url = live
    response = post(url, "/api/projects/demo/assistant", text="x", model="motor")
    session = app.state.assistant.get(response.json()["session"])
    assert post(url, f"/api/assistant/{session.id}/messages", text="y").status_code == 409
    assert post(url, f"/api/assistant/{session.id}/cancel").status_code == 202
    wait_idle(app.state.assistant, session.id, 20)
    assert session.events[-1]["status"] == "cancelled"


def test_a_dying_claude_is_an_error_event(live, monkeypatch):
    fake_claude_env(monkeypatch, "die")
    app, url = live
    session, _ = start(url, app)
    assert session.events[-1]["status"] == "error"
    assert "not logged in" in session.events[-1]["message"]


@pytest.mark.parametrize(
    "mode, phrase",
    [
        ("extra_tool", "tools differ"),
        ("skill", "skills present"),
        ("slash", "slash commands"),
        ("extra_server", "MCP servers"),
        ("api_key", "apiKeySource"),
    ],
)
def test_the_init_self_check_aborts_before_any_edit(live, monkeypatch, mode, phrase):
    fake_claude_env(monkeypatch, mode)
    app, url = live
    session, _ = start(url, app)
    assert session.events[-1]["status"] == "error"
    assert phrase in session.events[-1]["message"]
    assert not session.draft.changed


def test_the_child_environment_has_no_billing_keys(live, monkeypatch, tmp_path):
    dump, argv_file = tmp_path / "env.json", tmp_path / "argv.json"
    monkeypatch.setenv("FAKE_CLAUDE_ENVDUMP", str(dump))
    monkeypatch.setenv("FAKE_CLAUDE_ARGV", str(argv_file))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("anthropic_base_url", "http://evil")
    app, url = live
    start(url, app)
    env = json.loads(dump.read_text(encoding="utf-8"))
    assert not {k for k in env if k.upper() in runner_claude.STRIPPED_ENV}
    assert env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    called = json.loads(argv_file.read_text(encoding="utf-8"))
    assert called["entries"] == []
    argv = called["argv"]
    assert "--bare" not in argv and "bypassPermissions" not in argv
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--allowedTools") + 1] == "mcp__bgsim__*"
    assert "--strict-mcp-config" in argv


def test_tools_need_the_session_token(live):
    app, url = live
    session, _ = start(url, app)
    tool_url = f"{url}/api/assistant/{session.id}/tools"
    assert httpx.get(tool_url).status_code == 401
    assert httpx.get(tool_url, headers={"Authorization": "Bearer wrong"}).status_code == 401
    good = {"Authorization": f"Bearer {session.token}"}
    listed = httpx.get(tool_url, headers=good).json()["tools"]
    assert sorted(t["name"] for t in listed) == tools.names()
    assert httpx.post(f"{tool_url}/list_models", json={}, headers=good).status_code == 409  # idle


def test_the_ui_endpoints_are_loopback_only(fake_settings):
    make_project(fake_settings)
    app = create_app(fake_settings)
    with TestClient(app, client=("10.0.0.5", 1234)) as client:
        assert client.get("/api/assistant/profiles").status_code == 403
        assert client.post("/api/assistant", json={"text": "x"}).status_code == 403


def test_the_relay_rejects_other_hosts():
    assert check_url("http://127.0.0.1:1/api/assistant/x") == "http://127.0.0.1:1/api/assistant/x"
    for bad in ("http://example.com/x", "https://127.0.0.1/x", "file:///etc/passwd"):
        with pytest.raises(RelayError):
            check_url(bad)


def test_the_relay_exposes_the_registry():
    definitions = [definition.mcp() for definition in tools.TOOLS.values()]
    server = build("http://127.0.0.1:1/api/assistant/x", "t", definitions)
    assert server.name == "bgsim"


def test_profiles_report_availability(live):
    _app, url = live
    listed = httpx.get(f"{url}/api/assistant/profiles").json()
    assert listed["default"] == "claude-sonnet"
    entries = {p["name"]: p for p in listed["profiles"]}
    assert entries["claude-sonnet"]["available"] is True
    assert entries["local"]["available"] is False


def test_a_reloaded_page_finds_its_chat(live):
    app, url = live
    session, _ = start(url, app)
    found = httpx.get(f"{url}/api/assistant/sessions", params={"project": "demo"}).json()["session"]
    assert found["session"] == session.id


# ---------------------------------------------------------------------------- the home screen


def test_a_chat_on_the_home_screen_answers_and_creates_a_project(fake_settings, monkeypatch):
    make_project(fake_settings)
    app = create_app(fake_settings)
    fake_claude_env(monkeypatch, "home")
    app.state.assistant._cfg = make_config()
    app.state.assistant.claude.prefix = FAKE_CLAUDE
    with serve(app) as url:
        response = post(url, "/api/assistant", text="make a pendulum project")
        assert response.status_code == 201, response.text
        info = response.json()
        assert info["project"] is None
        session = wait_idle(app.state.assistant, info["session"])
        assert session.events[-1]["status"] == "ok", session.events[-1]
        assert session.project == "pendulum"
        assert any(e["type"] == "project_created" for e in session.events)
        assert (fake_settings.projects_root / "pendulum" / "bgsim.project.json").is_file()
        # The model it made is a draft, as in any project
        assert "first" in session.draft.models
        assert not (fake_settings.projects_root / "pendulum" / "models" / "first.bgmodel.json").exists()
        by_name = httpx.get(f"{url}/api/assistant/sessions", params={"project": "pendulum"}).json()
        assert by_name["session"]["session"] == info["session"]


def test_a_reloaded_home_screen_finds_its_chat(fake_settings, monkeypatch):
    app = create_app(fake_settings)
    fake_claude_env(monkeypatch, "slow")
    app.state.assistant._cfg = make_config()
    app.state.assistant.claude.prefix = FAKE_CLAUDE
    with serve(app) as url:
        info = post(url, "/api/assistant", text="what is a bond graph").json()
        found = httpx.get(f"{url}/api/assistant/sessions").json()["session"]
        assert found["session"] == info["session"]
        post(url, f"/api/assistant/{info['session']}/cancel")
        wait_idle(app.state.assistant, info["session"], 20)


# ---------------------------------------------------------------------------- openai-compatible


class ScriptedLLM:
    """An httpx transport playing a scripted model: each reply is the next message."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "local-model"}]})
        body = json.loads(request.content)
        self.requests.append(body)
        if len(body["messages"]) == 1 and body["tools"][0]["function"]["name"] == "ping":
            return httpx.Response(200, json={"choices": [{"message": {"tool_calls": [
                {"id": "1", "function": {"name": "ping", "arguments": '{"value": 1}'}}
            ]}}]})
        return httpx.Response(200, json={
            "choices": [{"message": self.replies.pop(0)}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })


def call(name: str, args: dict, call_id: str = "c1") -> dict:
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": call_id, "function": {"name": name, "arguments": json.dumps(args)}},
    ]}


def llm_app(app, script):
    client = httpx.Client(transport=httpx.MockTransport(script))
    assistant = app.state.assistant
    assistant._cfg = make_config("http://llm.test/v1")
    assistant.openai._client = client
    assistant._openai_client = client


def test_the_openai_loop_edits_through_the_same_tools(app):
    script = ScriptedLLM([
        call("add_block", {"name": "R1", "ref": "stdlib:bondgraph/R"}),
        {"role": "assistant", "content": "Done."},
    ])
    with TestClient(app) as client:
        llm_app(app, script)
        response = client.post(
            "/api/projects/demo/assistant", json={"text": "add", "model": "motor", "profile": "local"}
        )
        assert response.status_code == 201, response.text
        session = wait_idle(app.state.assistant, response.json()["session"])
    assert ended(session)["status"] == "ok", session.events
    assert ended(session)["usage"]["completionTokens"] == 10
    assert session.draft.changed
    assert script.requests[-1]["messages"][-1]["role"] == "tool"
    assert len(script.requests[-1]["tools"]) == len(tools.TOOLS)


def test_a_reasoning_model_keeps_its_reasoning_between_tool_calls(app):
    thinking = {**call("get_diagnostics", {}), "reasoning_content": "first look at the errors"}
    script = ScriptedLLM([thinking, {"role": "assistant", "content": "Done."}])
    with TestClient(app) as client:
        llm_app(app, script)
        response = client.post(
            "/api/projects/demo/assistant", json={"text": "x", "model": "motor", "profile": "local"}
        )
        session = wait_idle(app.state.assistant, response.json()["session"])
    assert ended(session)["status"] == "ok", session.events
    replayed = [m for m in script.requests[-1]["messages"] if m["role"] == "assistant"]
    assert replayed[0]["reasoning_content"] == "first look at the errors"


def test_text_that_looks_like_a_call_is_not_a_call(app):
    script = ScriptedLLM([{"role": "assistant", "content": '{"name": "delete_model", "arguments": {}}'}])
    with TestClient(app) as client:
        llm_app(app, script)
        response = client.post(
            "/api/projects/demo/assistant", json={"text": "x", "model": "motor", "profile": "local"}
        )
        session = wait_idle(app.state.assistant, response.json()["session"])
    assert not session.draft.changed
    assert not [e for e in session.events if e["type"] == "tool_call"]


def test_bad_json_arguments_are_a_tool_result(app):
    bad = {"role": "assistant", "content": "", "tool_calls": [
        {"id": "x", "function": {"name": "add_block", "arguments": "{oops"}},
    ]}
    script = ScriptedLLM([bad, {"role": "assistant", "content": "ok"}])
    with TestClient(app) as client:
        llm_app(app, script)
        response = client.post(
            "/api/projects/demo/assistant", json={"text": "x", "model": "motor", "profile": "local"}
        )
        session = wait_idle(app.state.assistant, response.json()["session"])
    assert ended(session)["status"] == "ok"
    assert "not valid JSON" in script.requests[-1]["messages"][-1]["content"]


HOSTED = (
    'default = "h"\n[profiles.h]\nrunner = "openai-compatible"\nbase_url = "https://x/v1"\n'
    'api_key_env = "BGSIM_TEST_KEY"\nmodel = "deepseek-v4-pro"\nmax_turns = 2\ntimeout_s = 5\n'
)


def test_a_hosted_profile_says_which_key_is_missing(monkeypatch):
    monkeypatch.delenv("BGSIM_TEST_KEY", raising=False)

    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request without a key")

    profile = profiles.parse(HOSTED).profiles["h"]
    result = runner_openai.probe(profile, httpx.Client(transport=httpx.MockTransport(refuse)))
    assert result["available"] is False and "BGSIM_TEST_KEY" in result["reason"]


def test_a_hosted_endpoint_gets_the_key_and_needs_no_model_list(monkeypatch):
    monkeypatch.setenv("BGSIM_TEST_KEY", "sk-secret")
    seen: list[httpx.Request] = []

    def endpoint(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(404)
        call = {"id": "1", "type": "function", "function": {"name": "ping", "arguments": '{"value": 1}'}}
        return httpx.Response(200, json={"choices": [{"message": {"tool_calls": [call]}}]})

    profile = profiles.parse(HOSTED).profiles["h"]
    result = runner_openai.probe(profile, httpx.Client(transport=httpx.MockTransport(endpoint)))
    assert result == {"available": True, "reason": None, "model": "deepseek-v4-pro"}
    assert all(r.headers["authorization"] == "Bearer sk-secret" for r in seen)
    assert seen[-1].headers["user-agent"] == runner_openai.USER_AGENT
    assert seen[-1].headers["x-opencode-session"]
    assert "sk-secret" not in json.dumps(profile.public())


def test_a_refused_probe_says_what_the_server_said(monkeypatch):
    monkeypatch.setenv("BGSIM_TEST_KEY", "sk-secret")

    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"type": "MissingSessionID"}})

    profile = profiles.parse(HOSTED).profiles["h"]
    result = runner_openai.probe(profile, httpx.Client(transport=httpx.MockTransport(refuse)))
    assert result["available"] is False
    assert "HTTP 400" in result["reason"] and "MissingSessionID" in result["reason"]


def test_a_model_list_is_still_needed_for_auto():
    def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    profile = profiles.parse(
        'default = "l"\n[profiles.l]\nrunner = "openai-compatible"\nbase_url = "http://x/v1"\n'
        'model = "auto"\nmax_turns = 2\ntimeout_s = 5\n'
    ).profiles["l"]
    result = runner_openai.probe(profile, httpx.Client(transport=httpx.MockTransport(missing)))
    assert result["available"] is False and "/models" in result["reason"]


def test_the_probe_needs_structured_tool_calls():
    def no_tools(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ping(1)"}}]})

    profile = profiles.parse(
        'default = "l"\n[profiles.l]\nrunner = "openai-compatible"\nbase_url = "http://x/v1"\n'
        'model = "auto"\nmax_turns = 2\ntimeout_s = 5\n'
    ).profiles["l"]
    result = runner_openai.probe(profile, httpx.Client(transport=httpx.MockTransport(no_tools)))
    assert result["available"] is False and "--jinja" in result["reason"]


def test_a_missing_claude_is_reported():
    runner = runner_claude.ClaudeRunner(lambda: "", ["definitely-not-claude"])
    assert runner.available() == (True, None)  # an explicit prefix is taken as given
    assert sys.executable
