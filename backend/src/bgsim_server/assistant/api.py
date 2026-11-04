"""REST + SSE of the assistant (plan/ASSISTANT_PLAN.md).

The UI endpoints answer only on the loopback interface: the backend binds 0.0.0.0, and the
``claude-cli`` runner works on the user's own subscription login, which is for the user alone.
Bodies are JSON models, so a foreign web page cannot post one without a CORS preflight, which
this app never grants. The relay endpoints (``/tools``) need the per-session token.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..contracts import AssistantAnswers, AssistantApplyRequest, AssistantMessageRequest
from ..projects import Store, _project_name
from . import tools
from .manager import Assistant, AssistantError
from .session import Session

KEEPALIVE_S = 15.0
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


def _local_only(request: Request) -> None:
    host = request.client.host if request.client is not None else None
    if host not in _LOOPBACK:
        raise HTTPException(status_code=403, detail="the assistant is available on this machine only")


router = APIRouter()
local = APIRouter(dependencies=[Depends(_local_only)])


def _assistant(request: Request) -> Assistant:
    return request.app.state.assistant


def _error(exc: AssistantError) -> JSONResponse:
    return JSONResponse(
        {"code": exc.code, "message": exc.message, "detail": exc.message, **exc.extra},
        status_code=exc.status,
    )


def _selection(body: AssistantMessageRequest) -> list[dict[str, Any]]:
    return [item.model_dump(by_alias=True, mode="json", exclude_unset=True) for item in body.selection or []]


def _sse(event: dict[str, Any]) -> bytes:
    text = json.dumps(event, ensure_ascii=False)
    return f"id: {event['seq']}\nevent: {event['type']}\ndata: {text}\n\n".encode()


def format_answers(session: Session, body: AssistantAnswers) -> str:
    """The answers as the next user message, in the words the question used."""
    question_set = session.question
    if question_set is None or question_set["id"] != body.questionSet:
        raise AssistantError(409, "no_question", "that question is no longer waiting for an answer")
    given = {answer.questionId: answer for answer in body.answers}
    lines = ["My answers:"]
    for question in question_set["questions"]:
        answer = given.get(question["id"])
        values = list(answer.values) if answer is not None else []
        other = (answer.other or "").strip() if answer is not None else ""
        labels = {o["value"]: o["label"] for o in question.get("options") or []}
        wrong = [v for v in values if v not in labels]
        if wrong:
            raise AssistantError(422, "bad_answer", f"{question['id']}: not an option: {wrong}")
        if question["kind"] == "single" and len(values) > 1:
            raise AssistantError(422, "bad_answer", f"{question['id']}: choose one")
        if other and question["kind"] != "text" and not question.get("allowOther"):
            raise AssistantError(422, "bad_answer", f"{question['id']}: takes no free text")
        if not values and not other and not question.get("optional"):
            raise AssistantError(422, "bad_answer", f"{question['id']} needs an answer")
        chosen = [f"{labels[v]} (`{v}`)" for v in values] + ([other] if other else [])
        lines.append(f"- {question['prompt']} {', '.join(chosen) or '(no answer)'}")
    return "\n".join(lines)


@local.get("/assistant/profiles")
async def profiles(request: Request, refresh: bool = Query(False)) -> Any:
    try:
        return await asyncio.to_thread(_assistant(request).list_profiles, refresh)
    except AssistantError as exc:
        return _error(exc)


@local.get("/assistant/sessions")
async def session_of(request: Request, project: str | None = None) -> dict[str, Any]:
    """The project's chat, or the home screen's without `project`: a reloaded page picks it up."""
    session = _assistant(request).for_project(project)
    return {"session": session.info() if session is not None else None}


@local.post("/assistant", status_code=201)
async def start_home(body: AssistantMessageRequest, request: Request) -> Any:
    """A chat on the home screen: no project yet."""
    try:
        session = await asyncio.to_thread(
            _assistant(request).start, None, body.text, body.profile, None,
            asyncio.get_running_loop(), _selection(body), body.run,
        )
    except AssistantError as exc:
        return _error(exc)
    return session.info()


@local.post("/projects/{project}/assistant", status_code=201)
async def start(
    project: str, body: AssistantMessageRequest, request: Request, store: Store
) -> Any:
    store._require_project(_project_name(project))
    try:
        session = await asyncio.to_thread(
            _assistant(request).start, project, body.text, body.profile, body.model,
            asyncio.get_running_loop(), _selection(body), body.run,
        )
    except AssistantError as exc:
        return _error(exc)
    return session.info()


@local.get("/assistant/{session_id}")
async def inspect(session_id: str, request: Request) -> Any:
    try:
        return _assistant(request).get(session_id).info()
    except AssistantError as exc:
        return _error(exc)


@local.delete("/assistant/{session_id}")
async def close(session_id: str, request: Request) -> Any:
    try:
        assistant = _assistant(request)
        assistant.get(session_id)
        await asyncio.to_thread(assistant.close, session_id)
        return {"closed": session_id}
    except AssistantError as exc:
        return _error(exc)


@local.post("/assistant/{session_id}/messages", status_code=202)
async def message(session_id: str, body: AssistantMessageRequest, request: Request) -> Any:
    try:
        assistant = _assistant(request)
        assistant.send(session_id, body.text, body.model, _selection(body), body.run)
        return assistant.get(session_id).info()
    except AssistantError as exc:
        return _error(exc)


@local.post("/assistant/{session_id}/answers", status_code=202)
async def answers(session_id: str, body: AssistantAnswers, request: Request) -> Any:
    try:
        assistant = _assistant(request)
        session = assistant.get(session_id)
        assistant.send(session_id, format_answers(session, body), None)
        return session.info()
    except AssistantError as exc:
        return _error(exc)


@local.post("/assistant/{session_id}/cancel", status_code=202)
async def cancel(session_id: str, request: Request) -> Any:
    try:
        _assistant(request).cancel(session_id)
        return {"cancelling": True}
    except AssistantError as exc:
        return _error(exc)


@local.post("/assistant/{session_id}/discard")
async def discard(session_id: str, request: Request) -> Any:
    try:
        session = _assistant(request).get(session_id)
        if session.state == "running":
            raise AssistantError(409, "busy", "cancel the run first")
        session.discard()
        return session.info()
    except AssistantError as exc:
        return _error(exc)


@local.post("/assistant/{session_id}/apply")
async def apply(session_id: str, body: AssistantApplyRequest, request: Request) -> Any:
    """Write the draft. A file changed on disk since the draft read it refuses the whole apply."""
    try:
        session = _assistant(request).get(session_id)
        if session.state == "running":
            raise AssistantError(409, "busy", "cancel the run first")
        problems = session.draft.problems()
        if problems:
            raise AssistantError(422, "invalid", problems[0][1], issues=[p[1] for p in problems[:10]])
        conflicts = session.draft.conflicts()
        if conflicts:
            raise AssistantError(
                409, "changed_on_disk",
                "these files changed since the chat read them: " + ", ".join(conflicts),
                files=conflicts,
            )
    except AssistantError as exc:
        return _error(exc)
    result = session.draft.apply(body.openModel, session.id)
    session.checks.clear()
    session.audit.write("apply", **{k: v for k, v in result.items() if k != "openModel"})
    session.emit("proposal", proposal=session.proposal())
    return result


@local.get("/assistant/{session_id}/events")
async def events(session_id: str, request: Request, after: int = Query(0, ge=0)) -> Any:
    try:
        session = _assistant(request).get(session_id)
    except AssistantError as exc:
        return _error(exc)

    async def stream() -> AsyncIterator[bytes]:
        loop = asyncio.get_running_loop()
        cursor = after
        while True:
            found = await loop.run_in_executor(None, session.wait_events, cursor, KEEPALIVE_S)
            if not found:
                if session.state != "running":
                    return  # idle and nothing new: the stream of this run is complete
                yield b": keepalive\n\n"
                continue
            for event in found:
                cursor = event["seq"] + 1
                yield _sse(event)
            if found[-1]["type"] in ("run_end", "closed") and session.state != "running":
                return

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


# ---------------------------------------------------------------------------- the relay


def _authed(request: Request, session_id: str) -> Session:
    """The session, when the bearer token is its own. Unknown session and wrong token look alike."""
    session = _assistant(request).sessions.get(session_id)
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth[:7].lower() == "bearer " else ""
    if session is None or not secrets.compare_digest(token.encode(), session.token.encode()):
        raise HTTPException(status_code=401, detail="unauthorized")
    return session


@router.get("/assistant/{session_id}/tools")
async def tool_list(session_id: str, request: Request) -> dict[str, Any]:
    _authed(request, session_id)
    return {"tools": [definition.mcp() for definition in tools.TOOLS.values()]}


@router.post("/assistant/{session_id}/tools/{name}")
async def tool_call(session_id: str, name: str, request: Request) -> Any:
    session = _authed(request, session_id)
    if session.state != "running":
        raise HTTPException(status_code=409, detail="tools can be called during a run only")
    if name not in tools.TOOLS:
        raise HTTPException(status_code=404, detail="unknown tool")
    try:
        args = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="the body is not JSON") from None
    result, is_error = await session.call_tool(name, args)
    return {"result": result, "isError": is_error}

