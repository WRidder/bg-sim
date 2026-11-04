"""Helpers of the assistant tests: a tool bench on the fake worker, a real uvicorn server (the
relay and a fake claude call back over HTTP), and a profile config."""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

import uvicorn

from bgsim_server.assistant import profiles, tools
from bgsim_server.assistant.session import Session

TESTS_DIR = Path(__file__).resolve().parent
REPO = TESTS_DIR.parents[1]
MODEL = REPO / "contracts" / "fixtures" / "model" / "valid" / "model.dcmotor.json"
FAKE_CLAUDE = [sys.executable, str(TESTS_DIR / "fake_claude.py")]
CONFIG = """
default = "claude-sonnet"
[profiles.claude-sonnet]
runner = "claude-cli"
model = "haiku"
effort = "low"
max_turns = 8
max_budget_usd = 0.3
timeout_s = 150
[profiles.local]
runner = "openai-compatible"
base_url = "{base_url}"
model = "auto"
max_turns = 6
timeout_s = 30
one_tool_at_a_time = true
"""


def make_config(base_url: str = "http://127.0.0.1:9/v1") -> profiles.AssistantConfig:
    return profiles.parse(CONFIG.format(base_url=base_url))


def make_project(settings: Any, name: str = "demo", model: str = "motor") -> Path:
    project = settings.projects_root / name
    (project / "models").mkdir(parents=True, exist_ok=True)
    (project / "bgsim.project.json").write_text(
        json.dumps({
            "format": "bgsim.project", "language": "0.1.0", "name": name, "models": [model],
            "libraryDir": "library", "scenesDir": "scenes",
        }),
        encoding="utf-8",
    )
    document = json.loads(MODEL.read_text(encoding="utf-8"))
    document["name"] = model
    (project / "models" / f"{model}.bgmodel.json").write_text(json.dumps(document), encoding="utf-8")
    return project


class Bench:
    """One session on a fake-worker app; `tool` runs a tool on the app's loop."""

    def __init__(self, client: Any, project: str = "demo", model: str | None = "motor"):
        self.client = client
        assistant = client.app.state.assistant

        async def running_loop() -> asyncio.AbstractEventLoop:
            return asyncio.get_running_loop()

        loop = client.portal.call(running_loop)
        self.s = Session(assistant.ctx, project, model, make_config().profiles["claude-sonnet"], loop)

    def call(self, tool_name: str, /, **args: Any) -> tuple[dict[str, Any], bool]:
        return self.client.portal.call(self.s.call_tool, tool_name, args)

    def tool(self, tool_name: str, /, **args: Any) -> dict[str, Any]:
        result, is_error = self.call(tool_name, **args)
        assert not is_error, result
        return result

    def refused(self, tool_name: str, /, **args: Any) -> str:
        result, is_error = self.call(tool_name, **args)
        assert is_error, result
        return result["error"]

    def events(self, kind: str) -> list[dict[str, Any]]:
        return [event for event in self.s.events if event["type"] == kind]


@contextlib.contextmanager
def serve(app: Any):
    """Run ``app`` on a free 127.0.0.1 port in a thread; the assistant learns the URL."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    url = f"http://127.0.0.1:{port}"
    app.state.assistant.backend_url = url
    try:
        yield url
    finally:
        server.should_exit = True
        thread.join(10)


def wait_idle(assistant: Any, session_id: str, timeout: float = 60.0) -> Session:
    session = assistant.get(session_id)
    start = time.monotonic()
    while session.state == "running":
        if time.monotonic() - start > timeout:
            raise TimeoutError("the assistant run did not finish")
        time.sleep(0.05)
    return session


def fake_claude_env(monkeypatch: Any, mode: str = "ok") -> None:
    monkeypatch.setenv("FAKE_CLAUDE_MODE", mode)
    monkeypatch.setenv("FAKE_CLAUDE_TOOLS", ",".join(tools.names()))


def tree(path: Path) -> dict[str, str]:
    """Every file below ``path`` with its contents, the audit logs left out."""
    return {
        str(p.relative_to(path)): p.read_text(encoding="utf-8")
        for p in sorted(path.rglob("*"))
        if p.is_file() and "logs" not in p.relative_to(path).parts
    }


def copy_example(settings: Any, source: Path, name: str) -> None:
    shutil.copytree(source, settings.projects_root / name)
