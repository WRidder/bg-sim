"""Runner ``openai-compatible``: the backend owns the loop over chat completions with tools
(llama.cpp ``llama-server``, Ollama, LM Studio, ... on a local ``base_url``, or a hosted endpoint
such as OpenCode Go with ``api_key_env``).

The model can act only through ``Session.call_tool``: no subprocess, no filesystem. Tool calls
are read ONLY from the structured ``tool_calls`` of the response, never parsed out of text.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

import httpx

from . import tools
from .profiles import Profile
from .prompts import system_prompt

PROBE_TOOL = {"type": "function", "function": {
    "name": "ping",
    "description": "Report a number back.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"value": {"type": "integer"}},
        "required": ["value"],
    },
}}


USER_AGENT = "bg-sim-assistant/0.1"


class RunnerError(Exception):
    pass


def _headers(profile: Profile, session: str | None = None) -> dict[str, str]:
    """A hosted endpoint wants to know the client and, for its limits, the conversation."""
    headers = {"User-Agent": USER_AGENT}
    key = os.environ.get(profile.api_key_env) if profile.api_key_env else None
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if session:
        headers["x-opencode-session"] = session
    return headers


def _models(profile: Profile, client: httpx.Client, timeout: float = 5.0) -> list[str]:
    assert profile.base_url is not None
    response = client.get(
        profile.base_url.rstrip("/") + "/models", headers=_headers(profile), timeout=timeout
    )
    response.raise_for_status()
    return [entry["id"] for entry in response.json().get("data", [])]


def probe(profile: Profile, client: httpx.Client | None = None, timeout: float = 60.0) -> dict[str, Any]:
    """The endpoint answers and one tiny tool call comes back as structured ``tool_calls``."""
    if profile.api_key_env and not os.environ.get(profile.api_key_env):
        return {
            "available": False, "model": None,
            "reason": f"set the environment variable {profile.api_key_env} and restart the backend",
        }
    own = client is None
    http = client or httpx.Client()
    url = (profile.base_url or "").rstrip("/")
    try:
        try:
            ids = _models(profile, http)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            # Only `auto` needs the list: some hosted endpoints do not serve one.
            if profile.model == "auto":
                return {"available": False, "reason": f"cannot reach {url}/models: {exc}", "model": None}
            ids = []
        if profile.model == "auto" and not ids:
            return {"available": False, "reason": f"{url}/models lists no model", "model": None}
        model = ids[0] if profile.model == "auto" else profile.model
        if profile.model != "auto" and ids and profile.model not in ids:
            return {"available": False, "reason": f"the server serves {ids}, not {profile.model!r}", "model": None}
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "Call the tool ping with value 1."}],
            "tools": [PROBE_TOOL], "tool_choice": "auto", "max_tokens": 512, "temperature": 0,
        }
        try:
            response = http.post(
                url + "/chat/completions", json=body, timeout=timeout,
                headers=_headers(profile, f"probe-{uuid.uuid4()}"),
            )
            if response.is_error:
                reason = f"HTTP {response.status_code}: {response.text[:300]}"
                return {"available": False, "reason": f"the tool-call probe failed: {reason}", "model": model}
            message = response.json()["choices"][0]["message"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            return {"available": False, "reason": f"the tool-call probe failed: {exc}", "model": model}
        calls = message.get("tool_calls") or []
        ok = False
        if calls:
            try:
                arguments = json.loads(calls[0]["function"]["arguments"])
                ok = calls[0]["function"]["name"] == "ping" and isinstance(arguments, dict)
            except (KeyError, TypeError, ValueError):
                ok = False
        if not ok:
            return {
                "available": False, "model": model,
                "reason": "no tool calling (start llama-server with --jinja): "
                "the probe returned no structured tool_calls",
            }
        return {"available": True, "reason": None, "model": model}
    finally:
        if own:
            http.close()


class OpenAIRunner:
    def __init__(self, client: httpx.Client | None = None):
        self._client = client

    def run(self, s: Any, text: str) -> dict[str, Any]:
        profile: Profile = s.profile
        deadline = time.monotonic() + profile.timeout_s
        own = self._client is None
        client = self._client or httpx.Client()
        usage = {"promptTokens": 0, "completionTokens": 0, "turns": 0}
        try:
            model = s.runner_state.get("model")
            if model is None:
                model = profile.model
                if model == "auto":
                    ids = _models(profile, client)
                    if not ids:
                        raise RunnerError(f"{profile.base_url}/models lists no model")
                    model = ids[0]
                s.runner_state["model"] = model
            history: list[dict[str, Any]] = s.runner_state.setdefault(
                "history", [{"role": "system", "content": system_prompt(profile, s.project)}]
            )
            history.append({"role": "user", "content": text})
            offered = [definition.openai() for definition in tools.TOOLS.values()]
            for _turn in range(profile.max_turns):
                if s.cancel_event.is_set():
                    return {"status": "cancelled", "usage": usage}
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {"status": "timeout", "usage": usage}
                body: dict[str, Any] = {
                    "model": model, "messages": history, "tools": offered, "tool_choice": "auto",
                    "temperature": 0.2 if profile.temperature is None else profile.temperature,
                }
                if profile.one_tool_at_a_time:
                    body["parallel_tool_calls"] = False
                if profile.top_k is not None:
                    body["top_k"] = profile.top_k
                if profile.repeat_penalty is not None:
                    body["repeat_penalty"] = profile.repeat_penalty
                assert profile.base_url is not None
                try:
                    response = client.post(
                        profile.base_url.rstrip("/") + "/chat/completions", json=body,
                        headers=_headers(profile, s.id), timeout=remaining,
                    )
                    response.raise_for_status()
                    answer = response.json()
                    message = answer["choices"][0]["message"]
                except httpx.TimeoutException:
                    return {"status": "timeout", "usage": usage}
                except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
                    raise RunnerError(f"chat completion failed: {exc}") from None
                usage["turns"] += 1
                counted = answer.get("usage") or {}
                usage["promptTokens"] += counted.get("prompt_tokens", 0)
                usage["completionTokens"] += counted.get("completion_tokens", 0)
                content = message.get("content") or ""
                calls = message.get("tool_calls") or []
                # A reasoning model refuses a history that lost its reasoning between tool calls.
                reasoning = message.get("reasoning_content")
                history.append({
                    "role": "assistant", "content": content, **({"tool_calls": calls} if calls else {}),
                    **({"reasoning_content": reasoning} if reasoning else {}),
                })
                if content.strip():
                    s.emit("text", text=content)
                if not calls:
                    s.messages.append({"role": "assistant", "text": content})
                    return {"status": "ok", "usage": usage}
                for call in calls:
                    history.append({
                        "role": "tool", "tool_call_id": call.get("id", ""),
                        "content": json.dumps(self._call(s, call)),
                    })
                if s.question is not None:
                    return {"status": "ok", "usage": usage}  # the answers come as the next message
            return {"status": "limit", "message": f"stopped after {profile.max_turns} turns", "usage": usage}
        finally:
            if own:
                client.close()

    @staticmethod
    def _call(s: Any, call: dict[str, Any]) -> dict[str, Any]:
        """Execute one structured tool call; every failure becomes the tool result."""
        function = call.get("function") or {}
        name = function.get("name", "")
        raw = function.get("arguments", "")
        try:
            args = json.loads(raw) if isinstance(raw, str) and raw.strip() else ({} if raw in ("", None) else raw)
        except ValueError as exc:
            result = {"error": f"the arguments are not valid JSON ({exc}); call the tool again"}
            s.emit("tool_call", name=name, args=raw, isError=True, summary="refused: arguments are not JSON")
            return result
        result, _ = s.call_tool_blocking(name, args)
        return result
