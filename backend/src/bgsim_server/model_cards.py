"""The model picker of a project: one card per model (``GET /api/projects/{p}/models``).

Opening a project shows its models as a grid of cards before the editor opens one. A card needs
more than the model name, and all of it comes from files the project already has, so no Julia
run is needed::

    {name, models: [{name, modified, inProject, description, thumbnail, nodes, preview, error}]}

* ``description``: the model's top-level ``$comment``; without one, the first plain paragraph of
  the first page of the model's docs (``models/<m>.docs``), Markdown stripped. At most
  ``DESCRIPTION_LIMIT`` characters (the web app shortens it further for the card).
* ``thumbnail``: the first image the first docs page shows (an asset file name such as
  ``1078c8343b4c.png``, served by ``GET /api/projects/{p}/docs/{m}/assets/{file}``), or null.
* ``nodes``: the number of blocks on the top-level diagram.
* ``preview``: a miniature of the top-level diagram for models without a docs image:
  ``nodes`` as ``[x, y, kind]`` (``b`` block, ``j`` junction, ``s`` subsystem) and ``links`` as
  ``[from, to, kind]`` node indices (``b`` bond, ``w`` wire, ``s`` signal), both capped.
* ``error``: why the model file could not be read (the card still opens it, and the editor
  shows the real error), else null.

The listing order and ``modified``/``inProject`` are the ones of ``GET /api/projects/{p}``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from .projects import DOCS_SUFFIX, Store

router = APIRouter()

#: Longest description returned (characters).
DESCRIPTION_LIMIT = 600
#: The miniature keeps at most this many nodes and links.
PREVIEW_NODE_LIMIT = 400
PREVIEW_LINK_LIMIT = 800
#: A model file larger than this is not parsed for its card.
MAX_MODEL_BYTES = 16 * 1024 * 1024

_PAGE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_IMAGE = re.compile(r"!\[[^\]]*\]\(\s*assets/([0-9a-f]{12}\.(?:png|jpg|gif|webp|svg))")
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_EMPHASIS = re.compile(r"(\*\*|__|\*|_|`)(?=\S)(.+?)(?<=\S)\1")
_SPACES = re.compile(r"\s+")


def _shorten(text: str, limit: int = DESCRIPTION_LIMIT) -> str | None:
    text = _SPACES.sub(" ", text).strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{cut}…"


def _plain(markdown: str) -> str:
    """Inline Markdown as plain text: links keep their text, emphasis and code marks go."""
    text = _LINK.sub(lambda match: match.group(1), markdown)
    for _ in range(3):
        text = _EMPHASIS.sub(lambda match: match.group(2), text)
    return text


def first_paragraph(markdown: str) -> str | None:
    """The first prose paragraph of a page: no heading, image, list, quote, table or code."""
    in_code = False
    block: list[str] = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("```") or line.startswith("~~~"):
            in_code = not in_code
            if block:
                break
            continue
        if in_code:
            continue
        if not line:
            if block:
                break
            continue
        prose = not (
            line.startswith(("#", "!", "-", "*", "+", ">", "|", "<", "$$"))
            or re.match(r"^\d+[.)]\s", line)
        )
        if not prose:
            if block:
                break
            continue
        block.append(line)
    return _shorten(_plain(" ".join(block))) if block else None


def _first_page(docs_dir: Path) -> str | None:
    """The Markdown of the first page in the docs manifest, or None."""
    manifest_path = docs_dir / "docs.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    pages = manifest.get("pages") if isinstance(manifest, dict) else None
    if not isinstance(pages, list) or not pages or not isinstance(pages[0], dict):
        return None
    page_id = pages[0].get("id")
    if not isinstance(page_id, str) or not _PAGE_ID.fullmatch(page_id):
        return None
    page = docs_dir / "pages" / f"{page_id}.md"
    if not page.is_file() or page.is_symlink():
        return None
    try:
        return page.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _thumbnail(docs_dir: Path, markdown: str) -> str | None:
    """The first image of the page that exists in the docs assets."""
    for match in _IMAGE.finditer(markdown):
        asset = docs_dir / "assets" / match.group(1)
        if asset.is_file() and not asset.is_symlink():
            return match.group(1)
    return None


def _node_kind(node: dict[str, Any]) -> str:
    block = node.get("block")
    if isinstance(block, dict):
        if "junction" in block:
            return "j"
        if "subsystem" in block:
            return "s"
    return "b"


def diagram_preview(document: Any) -> tuple[int, dict[str, list[list[Any]]]]:
    """The node count and the capped miniature of the top-level diagram."""
    diagram = document.get("diagram") if isinstance(document, dict) else None
    if not isinstance(diagram, dict):
        return 0, {"nodes": [], "links": []}
    raw_nodes = [n for n in diagram.get("nodes") or [] if isinstance(n, dict)]
    nodes: list[list[Any]] = []
    index: dict[str, int] = {}
    for node in raw_nodes[:PREVIEW_NODE_LIMIT]:
        position = node.get("position")
        if not isinstance(position, dict):
            continue
        x, y = position.get("x"), position.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        if isinstance(node.get("id"), str):
            index[node["id"]] = len(nodes)
        nodes.append([round(x), round(y), _node_kind(node)])
    links: list[list[Any]] = []
    for connection in diagram.get("connections") or []:
        if len(links) >= PREVIEW_LINK_LIMIT:
            break
        if not isinstance(connection, dict):
            continue
        ends = connection.get("from"), connection.get("to")
        if not all(isinstance(end, dict) for end in ends):
            continue
        a, b = index.get(ends[0].get("node")), index.get(ends[1].get("node"))
        if a is None or b is None or a == b:
            continue
        kind = connection.get("kind")
        links.append([a, b, kind[0] if isinstance(kind, str) and kind else "b"])
    return len(raw_nodes), {"nodes": nodes, "links": links}


def model_card(models_dir: Path, entry: dict[str, Any]) -> dict[str, Any]:
    """The card of one listed model (``entry`` from the project's model listing)."""
    name = entry["name"]
    card: dict[str, Any] = {
        **entry,
        "description": None,
        "thumbnail": None,
        "nodes": 0,
        "preview": {"nodes": [], "links": []},
        "error": None,
    }
    path = models_dir / f"{name}.bgmodel.json"
    document: Any = None
    try:
        if path.stat().st_size > MAX_MODEL_BYTES:
            card["error"] = "the model file is too large to preview"
        else:
            document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        card["error"] = f"the model file could not be read: {exc}"
    if isinstance(document, dict):
        comment = document.get("$comment")
        if isinstance(comment, str):
            card["description"] = _shorten(comment)
        card["nodes"], card["preview"] = diagram_preview(document)

    docs_dir = models_dir / f"{name}{DOCS_SUFFIX}"
    if docs_dir.is_dir() and not docs_dir.is_symlink():
        page = _first_page(docs_dir)
        if page is not None:
            card["thumbnail"] = _thumbnail(docs_dir, page)
            if card["description"] is None:
                card["description"] = first_paragraph(page)
    return card


@router.get("/projects/{project}/models")
def list_model_cards(project: str, store: Store) -> dict[str, Any]:
    """One card per model of the project, for the model picker."""
    project_dir = store._require_project(project)
    loaded = store._load_project(project_dir)
    models_dir = store._models_dir(project_dir)
    listing = store._model_listing(project_dir, loaded)
    return {
        "name": project_dir.name,
        "models": [model_card(models_dir, entry) for entry in listing],
    }
