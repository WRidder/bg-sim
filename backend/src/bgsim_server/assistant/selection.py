"""What the user had selected, as the text that goes in front of their message.

The chat shows the selection as chips; the model reads this text. Selected nodes are looked up
in the draft, so the model sees their block and parameters without a tool call.
"""

from __future__ import annotations

from typing import Any

from . import modelops
from .draft import Draft
from .modelops import ToolError


def _node(document: dict[str, Any] | None, path: list[str], name: str) -> str:
    if document is None:
        return name
    try:
        _, node, _ = modelops.locate(document, "/".join([*path, name]))
    except ToolError:
        return f"{name} (not in the draft)"
    details = modelops.block_label(node)
    params = node.get("params") or {}
    if params:
        details += ", " + ", ".join(f"{k}={v}" for k, v in params.items())
    return f"{name} ({details})"


def _diagram(draft: Draft, item: dict[str, Any]) -> str:
    level = "/".join(item["path"]) or "top level"
    lines = [f"- In model {item['model']}, {level}:"]
    document = draft.model(item["model"])
    if item["nodes"]:
        lines.append("  nodes: " + "; ".join(_node(document, item["path"], n) for n in item["nodes"]))
    if item["connections"]:
        lines.append("  connections: " + "; ".join(item["connections"]))
    return "\n".join(lines)


def _code(item: dict[str, Any]) -> str:
    return (
        f"- Code of {item['source']}, lines {item['fromLine']}-{item['toLine']}:\n"
        f"```julia\n{item['text']}\n```"
    )


def _doc(item: dict[str, Any]) -> str:
    owner = f"model {item['model']}" if item["model"] else "the project docs"
    return f"- Docs page {item['page']} of {owner}:\n<<<\n{item['text']}\n>>>"


def describe(draft: Draft, items: list[dict[str, Any]]) -> str:
    """The block to put before the message; empty without a selection."""
    if not items:
        return ""
    parts = []
    for item in items:
        if item["kind"] == "diagram":
            parts.append(_diagram(draft, item))
        elif item["kind"] == "code":
            parts.append(_code(item))
        else:
            parts.append(_doc(item))
    return "[Selected by the user:\n" + "\n".join(parts) + "\n]\n\n"
