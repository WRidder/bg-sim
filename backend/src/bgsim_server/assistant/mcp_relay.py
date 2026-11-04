"""The MCP relay of the ``claude-cli`` runner: a stdio MCP server (standalone ``fastmcp`` 4.x)
that is a child of ``claude``.

It holds NO logic and no file or worker access. It lists the tools of the backend's registry
(``GET {url}/tools``) and forwards each call to ``POST {url}/tools/{name}`` with the per-session
token from its environment. ``url`` is ``http://127.0.0.1:<port>/api/assistant/<session>``; any
other host is refused.

    BGSIM_ASSISTANT_URL=... BGSIM_ASSISTANT_TOKEN=... python -m bgsim_server.assistant.mcp_relay
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastmcp import FastMCP
from fastmcp.tools import Tool, ToolResult

SERVER_NAME = "bgsim"
URL_ENV = "BGSIM_ASSISTANT_URL"
TOKEN_ENV = "BGSIM_ASSISTANT_TOKEN"
CALL_TIMEOUT_S = 1800.0  # a simulation or a sweep waits for its result


class RelayError(Exception):
    pass


class RelayTool(Tool):
    """One backend tool. ``endpoint`` is the backend URL the call is forwarded to."""

    endpoint: str = ""
    token: str = ""

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=CALL_TIMEOUT_S) as http:
                response = await http.post(
                    self.endpoint, json=arguments, headers={"Authorization": f"Bearer {self.token}"}
                )
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return ToolResult(
                content=json.dumps({"error": f"the backend is unreachable: {exc}"}), is_error=True
            )
        if response.status_code != 200:
            return ToolResult(
                content=json.dumps({"error": f"the backend refused the call ({response.status_code})", "body": body}),
                is_error=True,
            )
        return ToolResult(
            content=json.dumps(body["result"], ensure_ascii=False), is_error=bool(body["isError"])
        )


def check_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise RelayError(f"{URL_ENV} must be an http URL on 127.0.0.1, got {url!r}")
    return url.rstrip("/")


def build(url: str, token: str, tool_defs: list[dict[str, Any]] | None = None) -> FastMCP:
    """The relay server; ``tool_defs`` (the backend's ``GET /tools``) are fetched when not given."""
    url = check_url(url)
    if tool_defs is None:
        response = httpx.get(url + "/tools", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if response.status_code != 200:
            raise RelayError(f"GET {url}/tools -> {response.status_code}")
        tool_defs = response.json()["tools"]
    mcp = FastMCP(SERVER_NAME)
    for definition in tool_defs:
        mcp.add_tool(RelayTool(
            name=definition["name"], description=definition["description"],
            parameters=definition["input_schema"], endpoint=f"{url}/tools/{definition['name']}",
            token=token,
        ))
    return mcp


def main() -> None:
    try:
        url, token = os.environ[URL_ENV], os.environ[TOKEN_ENV]
        build(url, token).run(transport="stdio", show_banner=False)
    except (KeyError, RelayError, httpx.HTTPError) as exc:
        print(f"mcp_relay: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
