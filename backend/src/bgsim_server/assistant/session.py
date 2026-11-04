"""One assistant session: the draft of one project, the event log (SSE), the pending question,
the verdicts of the model checks and the audit log.

The event log is the whole chat: a reloaded page replays it from the start.
"""

from __future__ import annotations

import asyncio
import copy
import json
import secrets
import threading
import time
import uuid
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ..projects import ProjectStore
from . import tools
from .draft import Draft, _normal
from .profiles import Profile

MAX_EDITS = 2000  # a runaway guard on edits per session


class Context:
    """What the tools need from the application; `shim` stands in for a Request (`.app`)."""

    def __init__(self, app: Any, store: ProjectStore, examples: ProjectStore):
        self.app = app
        self.settings = app.state.settings
        self.store = store
        self.examples = examples
        self.shim = SimpleNamespace(app=app)
        self._gallery: dict[str, Any] | None = None

    def gallery(self) -> dict[str, Any]:
        if self._gallery is None:
            path = self.settings.repo_root / "web" / "src" / "examples" / "gallery.json"
            self._gallery = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        return self._gallery


class Audit:
    """``<project>/logs/assistant/<utc time>-<session>.jsonl``: the profile, every user text,
    event, tool call and outcome. Never the tool token."""

    def __init__(self, project_dir: Path, session_id: str):
        folder = project_dir / "logs" / "assistant"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        self.path = folder / f"{stamp}-{session_id[:8]}.jsonl"
        self._lock = threading.Lock()

    def write(self, kind: str, **data: Any) -> None:
        record = {"t": round(time.time(), 3), "kind": kind, **data}
        # A project deleted under the chat takes its log with it.
        with self._lock, suppress(FileNotFoundError), self.path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


class Session:
    def __init__(
        self,
        ctx: Context,
        project: str | None,
        model: str | None,
        profile: Profile,
        loop: asyncio.AbstractEventLoop,
    ):
        self.id = str(uuid.uuid4())
        self.token = secrets.token_urlsafe(32)
        self.ctx = ctx
        self.project = project
        self.model = model
        self.profile = profile
        self.loop = loop
        self.draft = Draft(ctx.store, project or "")
        self.state = "idle"                 # idle | running | closed
        self.messages: list[dict[str, str]] = []
        self.usage: dict[str, Any] = {}
        self.runner_state: dict[str, Any] = {}
        self.events: list[dict[str, Any]] = []
        self.question: dict[str, Any] | None = None
        self.catalogs: dict[Any, Any] = {}
        self.checks: dict[str, tuple[Any, list[dict[str, Any]]]] = {}
        self.runs: set[str] = set()
        self.edits = 0
        self.cancel_event = threading.Event()
        self._cond = threading.Condition()
        self._edit_lock = asyncio.Lock()
        self._figures = 0
        # A chat on the home screen has no project folder for its log.
        log_root = ctx.store._require_project(project) if project else ctx.settings.worker_log_path.parent
        self.audit = Audit(log_root, self.id)
        self.audit.write("session", id=self.id, project=project, profile=profile.public())

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def next_figure(self) -> int:
        self._figures += 1
        return self._figures

    # -- events -------------------------------------------------------------------------------
    def emit(self, type_: str, **data: Any) -> dict[str, Any]:
        with self._cond:
            event = {"seq": len(self.events), "type": type_, "t": round(time.time(), 3), **data}
            self.events.append(event)
            self._cond.notify_all()
        self.audit.write("event", **{k: v for k, v in event.items() if k not in ("t", "proposal")})
        return event

    def wait_events(self, after: int, timeout: float) -> list[dict[str, Any]]:
        """Events with seq >= after; blocks up to ``timeout`` s when there are none yet."""
        with self._cond:
            if len(self.events) <= after:
                self._cond.wait(timeout)
            return self.events[after:]

    # -- tools --------------------------------------------------------------------------------
    async def call_tool(self, name: str, args: Any) -> tuple[dict[str, Any], bool]:
        if self.state == "closed":
            return {"error": "the session is closed"}, True
        definition = tools.TOOLS.get(name)
        edits = definition is not None and definition.edits
        if edits and self.edits >= MAX_EDITS:
            return {"error": f"at most {MAX_EDITS} edits per session"}, True
        if edits:
            async with self._edit_lock:  # edits read, await the worker, then write the draft
                result, is_error = await tools.call(self, name, args)
        else:
            result, is_error = await tools.call(self, name, args)
        self.audit.write("tool", name=name, args=args, is_error=is_error, result=result)
        self.emit("tool_call", name=name, args=args, isError=is_error, summary=_summary(result, is_error))
        if edits and not is_error:
            self.edits += 1
            self.emit("proposal", proposal=self.proposal())
        return result, is_error

    def call_tool_blocking(self, name: str, args: Any) -> tuple[dict[str, Any], bool]:
        """From a runner thread: the tools run on the application's event loop."""
        return asyncio.run_coroutine_threadsafe(self.call_tool(name, args), self.loop).result()

    def bind_project(self, project: str) -> None:
        """A chat on the home screen made a project and works in it from now on."""
        self.project = project
        self.draft = Draft(self.ctx.store, project)
        self.audit.write("project_created", project=project)
        self.emit("project_created", project=project)

    def pose_question(self, question_set: dict[str, Any]) -> None:
        self.question = question_set
        self.emit("question", question=question_set)

    # -- proposal -----------------------------------------------------------------------------
    def record_check(self, name: str, document: dict[str, Any], diagnostics: list[dict[str, Any]]) -> None:
        self.checks[name] = (_normal(document), diagnostics)

    def _fresh_check(self, name: str, document: dict[str, Any]) -> list[dict[str, Any]] | None:
        held = self.checks.get(name)
        return held[1] if held is not None and held[0] == _normal(document) else None

    def proposal(self) -> dict[str, Any]:
        issues = [
            {"file": file, "severity": "error", "code": None, "path": None, "message": message}
            for file, message in self.draft.problems()
        ]
        valid = not issues
        checked = True
        for name, document in self.draft.models.items():
            if document is None:
                continue
            diagnostics = self._fresh_check(name, document)
            if diagnostics is None:
                checked = False
                continue
            for item in diagnostics:
                if item.get("severity") in ("error", "warning"):
                    issues.append({
                        "file": f"model:{name}", "severity": item["severity"],
                        "code": item.get("code"), "path": item.get("path"),
                        "message": item["message"],
                    })
                if item.get("severity") == "error":
                    checked = False
        return {
            "changed": self.draft.changed,
            "valid": valid,
            "checked": checked,
            "issues": issues[:60],
            "files": self.draft.files(),
        }

    async def verify(self) -> None:
        """Check every changed model that has no verdict for its current state."""
        for name, document in list(self.draft.models.items()):
            if document is not None and self._fresh_check(name, document) is None:
                try:
                    await tools.check_document(self, name)
                except Exception as exc:  # noqa: BLE001 - the run must still end with its proposal
                    self.audit.write("verify_failed", model=name, error=str(exc))

    def discard(self) -> None:
        """Back to the saved project; the conversation stays."""
        self.draft.discard()
        self.audit.write("discard")
        self.emit("proposal", proposal=self.proposal())

    def info(self) -> dict[str, Any]:
        return {
            "session": self.id,
            "project": self.project,
            "model": self.model,
            "profile": self.profile.name,
            "state": self.state,
            "messages": copy.deepcopy(self.messages),
            "usage": dict(self.usage),
            "events": len(self.events),
            "proposal": self.proposal(),
            "question": self.question,
        }


def _summary(result: dict[str, Any], is_error: bool) -> str:
    if is_error:
        return "refused: " + str(result.get("error"))[:240]
    for key in ("added", "connected", "updated", "removed", "created", "shown", "written", "runId"):
        if key in result:
            status = f" ({result['status']})" if key == "runId" and "status" in result else ""
            return f"{key} {result[key]}{status}"
    if "errors" in result:
        return f"{result['errors']} errors, {result['warnings']} warnings"
    return "ok"
