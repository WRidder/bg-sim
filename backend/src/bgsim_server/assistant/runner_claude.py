"""Runner ``claude-cli``: ``claude -p`` as a subprocess on the user's SUBSCRIPTION login, the
planner-playground's integration (its design/briefs/WP8_assistant.md).

Safety rests on the flags AND on a self-check of the ``system/init`` event: the tools must be
exactly ours. Billing: the child environment has every API key or provider variable removed,
``--bare`` is never used (it ignores the OAuth login), and the run is aborted unless the CLI
reports ``apiKeySource == "none"``.

One ``claude`` process lives per session (stdin kept open, ``--input-format stream-json``), so a
follow-up message needs no transcript on disk. A cancelled or timed-out process is killed; the
next message starts a new one and is given the earlier requests as context.
"""

from __future__ import annotations

import json
import os
import queue
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from . import tools
from .profiles import Profile
from .prompts import system_prompt

SERVER_NAME = "bgsim"
MCP_PREFIX = f"mcp__{SERVER_NAME}__"
COMMAND_ENV = "BGSIM_ASSISTANT_CLAUDE"
STRIPPED_ENV = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
)
FIXED_ENV = {
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
    "CLAUDE_CODE_DISABLE_FILE_MENTIONS": "1",
    "ENABLE_CLAUDEAI_MCP_SERVERS": "false",
    "MCP_TOOL_TIMEOUT": "1800000",  # a simulation or a sweep can take long
}
INTERRUPT_GRACE_S = 5.0
INIT_TIMEOUT_S = 60.0


class RunnerError(Exception):
    pass


def expected_tools() -> list[str]:
    return sorted(MCP_PREFIX + name for name in tools.names())


def child_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """The parent's environment without any API-billing or provider variable, plus the fixed
    switches. Names are removed case-insensitively (Windows)."""
    source = os.environ if base is None else base
    env = {k: v for k, v in source.items() if k.upper() not in STRIPPED_ENV}
    env.update(FIXED_ENV)
    return env


def find_claude() -> list[str] | None:
    override = os.environ.get(COMMAND_ENV)
    if override:
        return shlex.split(override, posix=False)
    exe = shutil.which("claude")
    return [exe] if exe else None


def build_command(prefix: list[str], profile: Profile, mcp_json: Path, prompt_file: Path) -> list[str]:
    """The prompt comes on stdin, never on the command line, so the variadic --allowedTools
    cannot swallow it."""
    return [
        *prefix, "-p",
        "--tools", "",
        "--strict-mcp-config", "--mcp-config", str(mcp_json),
        "--setting-sources", "", "--settings", '{"disableAllHooks":true}',
        "--disable-slash-commands",
        "--permission-mode", "dontAsk", "--permission-prompts", "none",
        "--allowedTools", MCP_PREFIX + "*",
        "--model", profile.model, "--effort", str(profile.effort),
        "--max-turns", str(profile.max_turns), "--max-budget-usd", str(profile.max_budget_usd),
        "--system-prompt-file", str(prompt_file),
        "--no-session-persistence",
        "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
    ]


def check_init(init: dict[str, Any]) -> list[str]:
    """Problems with a ``system/init`` event; empty when the surface is exactly the expected one."""
    bad = []
    got = sorted(init.get("tools", []))
    want = expected_tools()
    if got != want:
        extra, missing = sorted(set(got) - set(want)), sorted(set(want) - set(got))
        bad.append(f"the tools differ: extra {extra}, missing {missing}")
    if init.get("skills"):
        bad.append(f"skills present: {init['skills']}")
    if init.get("slash_commands"):
        bad.append(f"slash commands present: {init['slash_commands']}")
    servers = init.get("mcp_servers", [])
    if [s.get("name") for s in servers] != [SERVER_NAME]:
        bad.append(f"MCP servers are {[s.get('name') for s in servers]}, expected [{SERVER_NAME!r}]")
    elif servers[0].get("status") != "connected":
        bad.append(f"MCP server {SERVER_NAME} is {servers[0].get('status')!r}, not connected")
    if init.get("permissionMode") != "dontAsk":
        bad.append(f"permissionMode is {init.get('permissionMode')!r}, expected 'dontAsk'")
    if init.get("apiKeySource") != "none":
        bad.append(f"apiKeySource is {init.get('apiKeySource')!r}, not 'none' (subscription login required)")
    return bad


def kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], check=False, capture_output=True)
    else:
        proc.kill()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()


class _Proc:
    """One running ``claude`` with a reader thread that queues its stdout lines (None at EOF)."""

    def __init__(self, argv: list[str], cwd: Path, env: dict[str, str]):
        self.popen = subprocess.Popen(
            argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0,
        )
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.stderr = bytearray()
        self.init_checked = False
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def _read(self) -> None:
        assert self.popen.stdout is not None
        for raw in iter(self.popen.stdout.readline, b""):
            self.lines.put(raw.decode("utf-8", "replace"))
        self.lines.put(None)

    def _read_err(self) -> None:
        assert self.popen.stderr is not None
        for raw in iter(self.popen.stderr.readline, b""):
            if len(self.stderr) < 4000:
                self.stderr += raw

    def send(self, obj: dict[str, Any]) -> None:
        assert self.popen.stdin is not None
        self.popen.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        self.popen.stdin.flush()

    def alive(self) -> bool:
        return self.popen.poll() is None


def user_line(text: str) -> dict[str, Any]:
    return {"type": "user", "message": {"role": "user", "content": text}}


def _usage(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "costUsd": event.get("total_cost_usd"),
        "turns": event.get("num_turns"),
        "durationMs": event.get("duration_ms"),
    }


class ClaudeRunner:
    """``prefix`` is the command that starts claude (default: ``claude`` on PATH, or
    ``BGSIM_ASSISTANT_CLAUDE``); tests put a fake there."""

    def __init__(self, backend_url: Any, prefix: list[str] | None = None):
        self._backend_url = backend_url  # callable -> "http://127.0.0.1:port"
        self.prefix = prefix

    def _command(self) -> list[str] | None:
        return self.prefix or find_claude()

    def available(self) -> tuple[bool, str | None]:
        if not self._command():
            return False, "the `claude` command is not on PATH"
        return True, None

    def run(self, s: Any, text: str) -> dict[str, Any]:
        deadline = time.monotonic() + s.profile.timeout_s
        state = s.runner_state
        proc: _Proc | None = state.get("proc")
        first = proc is None or not proc.alive()
        if first:
            proc = state["proc"] = self._start(s)
        payload = text
        if first and state.get("earlier"):
            earlier = "\n".join(f"- {t}" for t in state["earlier"])
            payload = (
                "Earlier requests in this chat (the draft already reflects them):\n"
                f"{earlier}\n\nNew request:\n{text}"
            )
        state.setdefault("earlier", []).append(text)
        assert proc is not None
        try:
            proc.send(user_line(payload))
        except OSError as exc:
            self._kill(s)
            raise RunnerError(f"claude is not running: {exc}") from None
        return self._consume(s, proc, deadline)

    def _start(self, s: Any) -> _Proc:
        prefix = self._command()
        if not prefix:
            raise RunnerError("the `claude` command is not on PATH")
        # A fresh EMPTY working directory outside the repository: nothing to pick up there.
        folder = Path(s.runner_state.get("folder") or tempfile.mkdtemp(prefix="bgsim-assistant-"))
        s.runner_state["folder"] = str(folder)
        cwd = folder / "cwd"
        cwd.mkdir(exist_ok=True)
        mcp_json = folder / "mcp.json"
        mcp_json.write_text(json.dumps({"mcpServers": {SERVER_NAME: {
            "command": sys.executable,
            "args": ["-m", "bgsim_server.assistant.mcp_relay"],
            "env": {
                "BGSIM_ASSISTANT_URL": f"{self._backend_url()}/api/assistant/{s.id}",
                "BGSIM_ASSISTANT_TOKEN": s.token,
                "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            },
        }}}), encoding="utf-8")
        prompt_file = folder / "system.md"
        prompt_file.write_text(system_prompt(s.profile, s.project), encoding="utf-8", newline="\n")
        argv = build_command(prefix, s.profile, mcp_json.resolve(), prompt_file.resolve())
        s.audit.write("spawn", argv=argv)  # the token is only in mcp.json, never in argv or the log
        return _Proc(argv, cwd, child_env())

    def _kill(self, s: Any) -> None:
        proc = s.runner_state.pop("proc", None)
        if proc is not None:
            kill_tree(proc.popen)

    def _consume(self, s: Any, proc: _Proc, deadline: float) -> dict[str, Any]:
        usage: dict[str, Any] = {}
        init_deadline = time.monotonic() + INIT_TIMEOUT_S
        interrupted_at: float | None = None
        while True:
            now = time.monotonic()
            if s.cancel_event.is_set() or now > deadline:
                if interrupted_at is None:
                    interrupted_at = now
                    try:
                        proc.send({
                            "type": "control_request", "request_id": uuid.uuid4().hex,
                            "request": {"subtype": "interrupt"},
                        })
                    except OSError:
                        pass
                elif now - interrupted_at > INTERRUPT_GRACE_S:
                    self._kill(s)
                    return {"status": "cancelled" if s.cancel_event.is_set() else "timeout", "usage": usage}
            if not proc.init_checked and now > init_deadline:
                self._kill(s)
                raise RunnerError("claude did not report its init event in time")
            try:
                line = proc.lines.get(timeout=0.25)
            except queue.Empty:
                continue
            if line is None:
                error = bytes(proc.stderr).decode("utf-8", "replace").strip()
                self._kill(s)
                if s.cancel_event.is_set():
                    return {"status": "cancelled", "usage": usage}
                raise RunnerError("claude exited" + (f": {error[:500]}" if error else ""))
            try:
                event = json.loads(line)
            except ValueError:
                continue
            kind = event.get("type")
            if kind == "system" and event.get("subtype") == "init":
                problems = check_init(event)
                proc.init_checked = True
                keep = ("tools", "mcp_servers", "skills", "slash_commands", "apiKeySource", "model",
                        "permissionMode", "claude_code_version")
                s.audit.write("init", init={k: event.get(k) for k in keep}, problems=problems)
                if problems:
                    self._kill(s)
                    raise RunnerError(
                        "init self-check failed, aborted before the first turn: " + "; ".join(problems)
                    )
                s.emit("status", message="claude started", model=event.get("model"))
            elif kind == "assistant":
                for block in event.get("message", {}).get("content", []):
                    if block.get("type") == "text" and block.get("text", "").strip():
                        s.emit("text", text=block["text"])
                        s.messages.append({"role": "assistant", "text": block["text"]})
            elif kind == "result":
                usage = _usage(event)
                if interrupted_at is not None:  # the interrupt ended the turn; the process lives on
                    return {"status": "cancelled" if s.cancel_event.is_set() else "timeout", "usage": usage}
                if event.get("is_error") or event.get("subtype") not in (None, "success"):
                    limit = str(event.get("subtype", "")).startswith("error_max")
                    return {
                        "status": "limit" if limit else "error",
                        "message": str(event.get("result") or event.get("subtype")),
                        "usage": usage,
                    }
                return {"status": "ok", "usage": usage}

    def close(self, s: Any) -> None:
        proc = s.runner_state.pop("proc", None)
        if proc is not None:
            try:
                assert proc.popen.stdin is not None
                proc.popen.stdin.close()
            except OSError:
                pass
            try:
                proc.popen.wait(3)
            except subprocess.TimeoutExpired:
                kill_tree(proc.popen)
        folder = s.runner_state.pop("folder", None)
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
