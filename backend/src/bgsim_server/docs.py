"""The documentation wiki of a model (work package W5.6).

Docs live next to the model file and travel with it::

    <project>/models/<model>.docs/
      docs.json            the page tree (contracts/schemas/docs.schema.json)
      pages/<id>.md        one Markdown file per page
      assets/<hash>.<ext>  images, named by the first 12 hex digits of their SHA-256

Endpoints (all under ``/api/projects/{p}/docs/{model}``)::

    GET    ""                      the manifest (an empty one when no docs exist yet)
    PUT    ""                      replace the manifest (schema and tree checked)
    GET    /pages/{id}             the page text (text/markdown; "" before the first save)
    PUT    /pages/{id}             write the page; the body is the Markdown text
    DELETE /pages/{id}?children=   remove a page; ``delete`` removes its subtree, ``promote``
                                   moves its children up one level (required when it has any)
    GET    /assets                 {assets: [{file, bytes, used}], unused}
    POST   /assets                 multipart upload (field ``file``) -> {file, path, bytes, existed}
    POST   /assets/copy            {fromProject, fromModel, files} -> {copied, existing, missing}
    DELETE /assets/unused          remove every asset that no page references
    GET    /assets/{file}          one image with a safe content type and a sandboxing CSP

Names are validated like the rest of the store: the model name by the project store, page ids and
asset names by the strict patterns below, so no request can leave the docs folder. Images are
recognised by their bytes (png, jpeg, gif, webp, svg), never by the client's file name or content
type; an SVG that carries script, event handlers or foreign content is refused. Deleting a page
rewrites the manifest first (atomically) and then removes the page files.
"""

from __future__ import annotations

import hashlib
import re
from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.datastructures import UploadFile

from .meshes import _atomic_write_bytes
from .projects import (
    DOCS_SUFFIX,
    ProjectError,
    ProjectStore,
    Store,
    _atomic_write,
    _inside,
    _json_body,
    _json_text,
    _model_name,
    _read_json,
)

router = APIRouter()

MANIFEST_FILE = "docs.json"
PAGES_DIR = "pages"
ASSETS_DIR = "assets"
#: Largest accepted image (bytes).
MAX_IMAGE_BYTES = 10 * 1024 * 1024
#: Largest accepted page text (bytes).
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_PAGES = 1000
MAX_DEPTH = 24

_PAGE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_ASSET_NAME = re.compile(r"^[0-9a-f]{12}\.(?:png|jpg|gif|webp|svg)$")
_ASSET_REF = re.compile(r"assets/([0-9a-f]{12}\.(?:png|jpg|gif|webp|svg))")

MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "svg": "image/svg+xml",
}
#: Served with every asset so an SVG opened on its own can run no script and load nothing.
ASSET_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "private, max-age=3600",
}
_SVG_FORBIDDEN = re.compile(
    r"<\s*script|<\s*foreignobject|<\s*iframe|<\s*embed|<\s*object|<!entity|"
    r"\son[a-z]+\s*=|javascript\s*:|data\s*:\s*text/html",
    re.IGNORECASE,
)


def empty_manifest() -> dict[str, Any]:
    return {"format": "bgsim.docs", "version": 1, "pages": []}


# --------------------------------------------------------------------------- names and paths


def _page_id(raw: str) -> str:
    if not _PAGE_ID.fullmatch(raw):
        raise ProjectError(
            400,
            f"invalid page id {raw!r}: use lower-case letters, digits and '-' (at most 64 "
            "characters, starting with a letter or digit)",
        )
    return raw


def _asset_name(raw: str) -> str:
    if not _ASSET_NAME.fullmatch(raw):
        raise ProjectError(
            400,
            f"invalid asset name {raw!r}: assets are named <12 hex digits>.<png|jpg|gif|webp|svg>; "
            "upload the image again to get its name",
        )
    return raw


def _docs_dir(store: ProjectStore, project: str, model: str) -> Path:
    """``models/<model>.docs`` of an existing model (the folder itself may not exist yet)."""
    project_dir = store._require_project(project)
    name = _model_name(model)
    if not store._model_path(project_dir, name).is_file():
        raise ProjectError(404, f"unknown model {model!r} in project {project!r}")
    directory = _inside(store._models_dir(project_dir), f"{name}{DOCS_SUFFIX}")
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ProjectError(400, f"the docs folder of model {model!r} is a link or a file")
    return directory


def _sub(directory: Path, *parts: str) -> Path:
    path = _inside(directory, *parts)
    if path.parent.is_symlink():
        raise ProjectError(400, f"{path.parent} is a link")
    return path


# --------------------------------------------------------------------------- manifest


def _walk(pages: list[dict[str, Any]], depth: int = 1):
    for page in pages:
        yield page, depth
        yield from _walk(page["children"], depth + 1)


def _check_manifest(store: ProjectStore, document: Any) -> dict[str, Any]:
    store._check_schema("docs", document, "the docs manifest")
    if not isinstance(document, dict):
        raise ProjectError(422, "the docs manifest must be a JSON object")
    seen: set[str] = set()
    for page, depth in _walk(document["pages"]):
        if depth > MAX_DEPTH:
            raise ProjectError(
                422, f"page {page['id']!r} is nested deeper than {MAX_DEPTH} levels; flatten the tree"
            )
        if page["id"] in seen:
            raise ProjectError(
                422, f"page id {page['id']!r} is used twice; every page needs its own id"
            )
        seen.add(page["id"])
        expected = f"{PAGES_DIR}/{page['id']}.md"
        if page["file"] != expected:
            raise ProjectError(
                422,
                f"page {page['id']!r} names the file {page['file']!r}; a page file is always "
                f"{expected!r}",
            )
    if len(seen) > MAX_PAGES:
        raise ProjectError(422, f"the docs have {len(seen)} pages; the limit is {MAX_PAGES}")
    return document


def _read_manifest(store: ProjectStore, directory: Path) -> dict[str, Any]:
    path = _sub(directory, MANIFEST_FILE)
    if not path.is_file():
        return empty_manifest()
    return _check_manifest(store, _read_json(path))


def _write_manifest(directory: Path, manifest: dict[str, Any]) -> None:
    _atomic_write(_sub(directory, MANIFEST_FILE), _json_text(manifest))


def _find(pages: list[dict[str, Any]], page_id: str) -> tuple[list[dict[str, Any]], int] | None:
    """The sibling list holding ``page_id`` and its index."""
    for index, page in enumerate(pages):
        if page["id"] == page_id:
            return pages, index
        found = _find(page["children"], page_id)
        if found is not None:
            return found
    return None


def _ids_of(page: dict[str, Any]) -> list[str]:
    return [page["id"], *(i for child in page["children"] for i in _ids_of(child))]


@router.get("/projects/{project}/docs/{model}")
def get_docs(project: str, model: str, store: Store) -> dict[str, Any]:
    """The page tree of a model; a model without docs has an empty one."""
    return _read_manifest(store, _docs_dir(store, project, model))


@router.put("/projects/{project}/docs/{model}")
async def put_docs(project: str, model: str, request: Request, store: Store) -> dict[str, Any]:
    """Replace the page tree (the page files are written through the page routes)."""
    directory = _docs_dir(store, project, model)
    document = _check_manifest(store, await _json_body(request, "docs manifest"))
    _write_manifest(directory, document)
    return document


# --------------------------------------------------------------------------- pages


def _require_page(store: ProjectStore, directory: Path, page_id: str) -> dict[str, Any]:
    manifest = _read_manifest(store, directory)
    found = _find(manifest["pages"], page_id)
    if found is None:
        raise ProjectError(
            404,
            f"unknown page {page_id!r}; add it to the page tree first (PUT the manifest) and "
            "then write its text",
        )
    siblings, index = found
    return siblings[index]


@router.get("/projects/{project}/docs/{model}/pages/{page_id}")
def get_page(project: str, model: str, page_id: str, store: Store) -> PlainTextResponse:
    directory = _docs_dir(store, project, model)
    _require_page(store, directory, _page_id(page_id))
    path = _sub(directory, PAGES_DIR, f"{page_id}.md")
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return PlainTextResponse(text, media_type="text/markdown")


@router.put("/projects/{project}/docs/{model}/pages/{page_id}")
async def put_page(
    project: str, model: str, page_id: str, request: Request, store: Store
) -> dict[str, Any]:
    directory = _docs_dir(store, project, model)
    _require_page(store, directory, _page_id(page_id))
    raw = await request.body()
    if len(raw) > MAX_PAGE_BYTES:
        raise ProjectError(
            413, f"the page is {len(raw)} bytes; the limit is {MAX_PAGE_BYTES}. Split the page."
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectError(400, f"the page is not UTF-8 text: {exc}") from exc
    stored = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    _atomic_write_bytes(_sub(directory, PAGES_DIR, f"{page_id}.md"), stored)
    return {"id": page_id, "bytes": len(stored)}


@router.delete("/projects/{project}/docs/{model}/pages/{page_id}")
def delete_page(
    project: str, model: str, page_id: str, store: Store, children: str | None = None
) -> dict[str, Any]:
    """Remove a page: manifest first (atomically), then the files of the removed pages."""
    directory = _docs_dir(store, project, model)
    manifest = _read_manifest(store, directory)
    found = _find(manifest["pages"], _page_id(page_id))
    if found is None:
        raise ProjectError(404, f"unknown page {page_id!r}")
    siblings, index = found
    page = siblings[index]
    if page["children"] and children not in {"delete", "promote"}:
        raise ProjectError(
            409,
            f"page {page_id!r} has {len(page['children'])} child page(s); pass children=delete "
            "to remove the whole subtree or children=promote to move them up one level",
        )
    if children == "promote":
        siblings[index : index + 1] = page["children"]
        removed = [page_id]
    else:
        del siblings[index]
        removed = _ids_of(page)
    _write_manifest(directory, manifest)
    for removed_id in removed:
        with suppress(OSError):
            _sub(directory, PAGES_DIR, f"{removed_id}.md").unlink(missing_ok=True)
    return {"removed": removed, "pages": manifest["pages"]}


# --------------------------------------------------------------------------- assets


def sniff_image(data: bytes) -> str | None:
    """The extension of a supported image, judged by its bytes; ``None`` when unsupported."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    head = data[:2048].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head.startswith((b"<?xml", b"<svg", b"<!--", b"<!DOCTYPE svg")) and b"<svg" in data[:8192]:
        return "svg"
    return None


def _check_svg(data: bytes) -> None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectError(415, f"the SVG is not UTF-8 text: {exc}") from exc
    match = _SVG_FORBIDDEN.search(text)
    if match is not None:
        raise ProjectError(
            422,
            f"the SVG contains {match.group(0).strip()!r}, which could run script; remove "
            "scripts, event handlers and embedded objects, or export the drawing as PNG",
        )


def asset_name_for(data: bytes, extension: str) -> str:
    return f"{hashlib.sha256(data).hexdigest()[:12]}.{extension}"


def _asset_files(directory: Path) -> list[Path]:
    assets = _sub(directory, ASSETS_DIR)
    if not assets.is_dir():
        return []
    return sorted(
        (p for p in assets.iterdir() if p.is_file() and _ASSET_NAME.fullmatch(p.name)),
        key=lambda p: p.name,
    )


def _referenced_assets(directory: Path) -> set[str]:
    pages = _sub(directory, PAGES_DIR)
    names: set[str] = set()
    if pages.is_dir():
        for path in pages.glob("*.md"):
            names.update(_ASSET_REF.findall(path.read_text(encoding="utf-8", errors="replace")))
    return names


@router.get("/projects/{project}/docs/{model}/assets")
def list_assets(project: str, model: str, store: Store) -> dict[str, Any]:
    directory = _docs_dir(store, project, model)
    used = _referenced_assets(directory)
    assets = [
        {"file": p.name, "bytes": p.stat().st_size, "used": p.name in used}
        for p in _asset_files(directory)
    ]
    return {"assets": assets, "unused": sum(1 for a in assets if not a["used"])}


@router.post("/projects/{project}/docs/{model}/assets")
async def upload_asset(project: str, model: str, request: Request, store: Store) -> Response:
    directory = _docs_dir(store, project, model)
    content_type = request.headers.get("content-type", "").lower()
    if not content_type.startswith("multipart/form-data"):
        raise ProjectError(
            415, "send the image as multipart/form-data with the file in the field 'file'"
        )
    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise ProjectError(400, "the form has no file; put the image in the field named 'file'")
    data = await upload.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ProjectError(
            413,
            f"the image is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MiB; scale it down or "
            "export it as JPEG or WebP and add it again",
        )
    if not data:
        raise ProjectError(400, "the image is empty")
    extension = sniff_image(data)
    if extension is None:
        raise ProjectError(
            415,
            "unsupported image format: use PNG, JPEG, GIF, WebP or SVG (convert other formats first)",
        )
    if extension == "svg":
        _check_svg(data)
    name = asset_name_for(data, extension)
    path = _sub(directory, ASSETS_DIR, name)
    existed = path.is_file()
    if not existed:
        _atomic_write_bytes(path, data)
    body = {"file": name, "path": f"{ASSETS_DIR}/{name}", "bytes": len(data), "existed": existed}
    return JSONResponse(body, status_code=200 if existed else 201)


@router.post("/projects/{project}/docs/{model}/assets/copy")
async def copy_assets(project: str, model: str, request: Request, store: Store) -> dict[str, Any]:
    """Copy assets from another model so pasted Markdown keeps its images."""
    target = _docs_dir(store, project, model)
    body = await _json_body(request, "copy request")
    source_project, source_model, files = (
        body.get("fromProject"),
        body.get("fromModel"),
        body.get("files"),
    )
    if (
        not isinstance(source_project, str)
        or not isinstance(source_model, str)
        or not isinstance(files, list)
        or not all(isinstance(f, str) for f in files)
    ):
        raise ProjectError(
            422, "send {fromProject, fromModel, files: [asset names]} to copy assets"
        )
    source = _docs_dir(store, source_project, source_model)
    copied: list[str] = []
    existing: list[str] = []
    missing: list[str] = []
    for file in dict.fromkeys(files):
        name = _asset_name(file)
        destination = _sub(target, ASSETS_DIR, name)
        origin = _sub(source, ASSETS_DIR, name)
        if destination.is_file():
            existing.append(name)
        elif not origin.is_file():
            missing.append(name)
        else:
            _atomic_write_bytes(destination, origin.read_bytes())
            copied.append(name)
    return {"copied": copied, "existing": existing, "missing": missing}


@router.delete("/projects/{project}/docs/{model}/assets/unused")
def delete_unused_assets(project: str, model: str, store: Store) -> dict[str, Any]:
    """Remove the assets that no saved page references."""
    directory = _docs_dir(store, project, model)
    used = _referenced_assets(directory)
    deleted: list[str] = []
    for path in _asset_files(directory):
        if path.name not in used:
            path.unlink()
            deleted.append(path.name)
    return {"deleted": deleted, "kept": len(_asset_files(directory))}


@router.get("/projects/{project}/docs/{model}/assets/{file}")
def get_asset(project: str, model: str, file: str, store: Store) -> FileResponse:
    directory = _docs_dir(store, project, model)
    name = _asset_name(file)
    path = _sub(directory, ASSETS_DIR, name)
    if not path.is_file():
        raise ProjectError(404, f"unknown image {file!r} in the docs of model {model!r}")
    return FileResponse(
        path, media_type=MEDIA_TYPES[name.rsplit(".", 1)[1]], headers=ASSET_HEADERS
    )

