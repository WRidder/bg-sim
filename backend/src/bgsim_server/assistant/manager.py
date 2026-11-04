"""The assistant core: profiles with availability, one session per project, one run at a time
per session, the run thread and cleanup."""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

from ..projects import ProjectStore
from . import runner_claude, runner_openai, selection, tools
from .profiles import AssistantConfig, Profile, ProfileError, config_path, load
from .session import Context, Session

PROBE_TTL_S = 30.0
VERIFY_TIMEOUT_S = 120.0


class AssistantError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: Any):
        super().__init__(code)
        self.status, self.code, self.message, self.extra = status, code, message, extra


class Assistant:
    def __init__(
        self,
        app: Any,
        cfg: AssistantConfig | None = None,
        claude_prefix: list[str] | None = None,
        openai_client: Any = None,
    ):
        settings = app.state.settings
        schemas = settings.repo_root / "contracts" / "schemas"
        examples = settings.repo_root / "examples"
        self.ctx = Context(
            app,
            ProjectStore(settings.projects_root, examples, schemas),
            ProjectStore(examples, examples, schemas),
        )
        self.backend_url = f"http://127.0.0.1:{settings.port}"
        self.sessions: dict[str, Session] = {}
        self._cfg = cfg
        self._lock = threading.RLock()
        self._probes: dict[str, tuple[float, dict[str, Any]]] = {}
        self.claude = runner_claude.ClaudeRunner(lambda: self.backend_url, claude_prefix)
        self.openai = runner_openai.OpenAIRunner(openai_client)
        self._openai_client = openai_client

    # -- profiles -----------------------------------------------------------------------------
    def config(self) -> AssistantConfig:
        if self._cfg is None:
            try:
                self._cfg = load(config_path(self.ctx.settings.repo_root))
            except ProfileError as exc:
                raise AssistantError(500, "bad_assistant_config", str(exc)) from None
        return self._cfg

    def availability(self, profile: Profile, refresh: bool = False) -> dict[str, Any]:
        held = self._probes.get(profile.name)
        if held and not refresh and time.monotonic() - held[0] < PROBE_TTL_S:
            return held[1]
        if profile.runner == "claude-cli":
            ok, why = self.claude.available()
            result: dict[str, Any] = {"available": ok, "reason": why}
        else:
            result = runner_openai.probe(profile, self._openai_client)
        self._probes[profile.name] = (time.monotonic(), result)
        return result

    def list_profiles(self, refresh: bool = False) -> dict[str, Any]:
        cfg = self.config()
        out = []
        for profile in cfg.profiles.values():
            state = self.availability(profile, refresh)
            out.append({
                "name": profile.name,
                "runner": profile.runner,
                "model": state.get("model") or profile.model,
                "available": state["available"],
                "reason": state["reason"],
                "limits": {
                    "maxTurns": profile.max_turns,
                    "timeoutS": profile.timeout_s,
                    "maxBudgetUsd": profile.max_budget_usd,
                },
            })
        return {"default": cfg.default, "profiles": out}

    # -- sessions -----------------------------------------------------------------------------
    def get(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if session is None:
            raise AssistantError(404, "not_found", "no such assistant session")
        return session

    def for_project(self, project: str | None) -> Session | None:
        return next((s for s in self.sessions.values() if s.project == project), None)

    def start(
        self,
        project: str | None,
        text: str,
        profile_name: str | None,
        model: str | None,
        loop: asyncio.AbstractEventLoop,
        selected: list[dict[str, Any]] | None = None,
        shown_run: str | None = None,
    ) -> Session:
        cfg = self.config()
        profile = cfg.profiles.get(profile_name or cfg.default)
        if profile is None:
            raise AssistantError(404, "not_found", f"no profile {profile_name!r}", profiles=sorted(cfg.profiles))
        state = self.availability(profile)
        if not state["available"]:
            raise AssistantError(409, "profile_unavailable", state["reason"] or "unavailable", profile=profile.name)
        with self._lock:
            old = self.for_project(project)
            if old is not None:
                if old.state == "running":
                    raise AssistantError(409, "busy", f"an assistant run on {project!r} is in progress")
                self.close(old.id)  # "New chat": one session per project
            session = Session(self.ctx, project, model, profile, loop)
            self.sessions[session.id] = session
        self.send(session.id, text, model, selected, shown_run)
        return session

    def send(
        self,
        session_id: str,
        text: str,
        model: str | None,
        selected: list[dict[str, Any]] | None = None,
        shown_run: str | None = None,
    ) -> None:
        session = self.get(session_id)
        with self._lock:
            if session.state == "running":
                raise AssistantError(409, "busy", "a run is in progress; cancel it first")
            if session.state == "closed":
                raise AssistantError(409, "closed", "this chat is closed")
            session.state = "running"
            session.cancel_event.clear()
        if model is not None:
            session.model = model
        session.question = None
        session.draft.refresh()  # the user may have edited since the last message
        session.messages.append({"role": "user", "text": text})
        session.audit.write("user", text=text)
        session.emit("user", text=text, **({"selection": selected} if selected else {}))
        where = f"[The editor has model {session.model!r} open.]\n" if session.model else ""
        if shown_run:
            where += f"[The Plots dock shows run {shown_run}.]\n"
        prompt = where + selection.describe(session.draft, selected or []) + text
        threading.Thread(
            target=self._run, args=(session, prompt), daemon=True,
            name=f"assistant-{session.id[:8]}",
        ).start()

    def _run(self, session: Session, text: str) -> None:
        session.emit("run_start", profile=session.profile.name, runner=session.profile.runner)
        runner = self.claude if session.profile.runner == "claude-cli" else self.openai
        try:
            out = runner.run(session, text)
        except (runner_claude.RunnerError, runner_openai.RunnerError) as exc:
            out = {"status": "error", "message": str(exc)}
            session.emit("error", message=str(exc))
        except Exception as exc:  # noqa: BLE001 - the stream must always end with run_end
            out = {"status": "error", "message": f"{type(exc).__name__}: {exc}"}
            session.emit("error", message=out["message"])
        if out.get("status") not in ("ok", "error", "cancelled") and out.get("message"):
            session.emit("error", message=out["message"])
        session.usage = out.get("usage") or session.usage
        if session.state != "closed" and session.draft.changed:
            try:  # the proposal says what the compiler thinks of the final draft
                asyncio.run_coroutine_threadsafe(session.verify(), session.loop).result(VERIFY_TIMEOUT_S)
            except Exception as exc:  # noqa: BLE001 - see Session.verify
                session.audit.write("verify_failed", error=str(exc))
        proposal = session.proposal()
        session.audit.write(
            "outcome", status=out["status"], message=out.get("message"), usage=out.get("usage"),
            files=[f["name"] for f in proposal["files"]],
        )
        # run_end is in the stream before the session reads idle: whoever sees idle also finds it.
        with self._lock:
            session.emit(
                "run_end", status=out["status"], message=out.get("message"), usage=out.get("usage"),
                proposal=proposal,
            )
            if session.state != "closed":
                session.state = "idle"

    def cancel(self, session_id: str) -> None:
        session = self.get(session_id)
        session.cancel_event.set()
        session.audit.write("cancel")

    def close(self, session_id: str) -> None:
        session = self.sessions.pop(session_id, None)
        if session is None:
            return
        session.cancel_event.set()
        session.state = "closed"
        session.audit.write("closed")
        if not session.loop.is_closed():
            asyncio.run_coroutine_threadsafe(tools.stop_paused_runs(session), session.loop)
        if session.profile.runner == "claude-cli":
            self.claude.close(session)
        session.emit("closed")

    def shutdown(self) -> None:
        for session_id in list(self.sessions):
            self.close(session_id)
