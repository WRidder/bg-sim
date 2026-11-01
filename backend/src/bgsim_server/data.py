"""Project data files (work package F5.1): CSV inputs for ``stdlib:sources/CsvSource`` and
reduced-model files (``*.modal.json``, format ``bgsim.modal-body``) for
``stdlib:spatial/ModalBody3D``.

* ``GET /api/projects/{p}/data?kind=csv`` lists the files of the project's ``data/`` folder
  (``[{"file", "bytes", "kind"}]``, sorted by name). ``kind`` is ``csv`` (the default, so a
  plain request lists the CSV files as it always did), ``modal`` or ``all``; each entry's
  ``kind`` is ``"csv"`` or ``"modal"``.
* ``GET /api/projects/{p}/data/{file}`` returns the file text (``text/csv`` or
  ``application/json``).
* ``PUT /api/projects/{p}/data/{file}`` replaces (or creates) a file; the body is the text
  (UTF-8). A reduced-model file must be a JSON object with ``"format": "bgsim.modal-body"`` and
  ``"version": 1``. ``DELETE`` removes a file.
* ``POST /api/projects/{p}/data`` takes a ``multipart/form-data`` upload (field ``file``) of a
  ``.csv`` or ``.modal.json`` file and stores it as ``data/<name>.csv`` or
  ``data/<name>.modal.json``; an upload with the name of an existing file replaces it.
* ``GET /api/projects/{p}/data/{file}/preview?rows=10`` returns the header (``columns`` with
  the optional ``[unit]`` split off), the number of data rows and the first rows, so the
  inspector can show what a CsvSource will read (CSV files only).

``file`` is one plain name ending in ``.csv`` or ``.modal.json`` (no path separators, ``..`` or
drive letters, like the scene and mesh names). Uploads and PUT bodies are limited to
:data:`MAX_DATA_BYTES` (413 above). Every message says what to do next.
"""

from __future__ import annotations

import csv
import json
import re
from typing import Any, Literal

from fastapi import APIRouter, Query, Request, Response
from starlette.datastructures import UploadFile

from .meshes import _atomic_write_bytes
from .projects import ProjectError, ProjectStore, Store, _inside, _is_safe_name

router = APIRouter()

#: Largest accepted data file (bytes): about 1.5 million rows of 10 columns.
MAX_DATA_BYTES = 100 * 1024 * 1024
DATA_DIR = "data"
CSV_SUFFIX = ".csv"
MODAL_SUFFIX = ".modal.json"
MODAL_FORMAT = "bgsim.modal-body"
MODAL_VERSION = 1
#: File kind to file-name suffix (lower case).
DATA_SUFFIXES = {"csv": CSV_SUFFIX, "modal": MODAL_SUFFIX}
MEDIA_TYPES = {"csv": "text/csv", "modal": "application/json"}
_UNIT_HEADER = re.compile(r"^(.*?)\s*\[([^\]]*)\]\s*$")
_MODAL_HINT = "write it with julia/BGSimFEM (bin/bgsim-fem.jl <part>.fem.json)"


def _project_dir(store: ProjectStore, project: str):
    return store._require_project(project)


def _data_dir(project_dir):
    directory = _inside(project_dir, DATA_DIR)
    if directory.is_symlink():
        raise ProjectError(400, f"the data directory of {project_dir.name!r} is a link")
    return directory


def data_kind(name: str) -> str | None:
    """``"csv"``, ``"modal"`` or None (not a data file) by the suffix of ``name``."""
    lower = name.lower()
    for kind, suffix in DATA_SUFFIXES.items():
        if lower.endswith(suffix) and len(lower) > len(suffix):
            return kind
    return None


def _data_name(raw: str) -> str:
    if not _is_safe_name(raw) or data_kind(raw) is None:
        raise ProjectError(
            400,
            f"invalid data file name {raw!r}: use a single file name such as 'trajectory.csv' or "
            "'bracket.modal.json' (letters, digits, '_', '-' or '.', ending in .csv or "
            ".modal.json, no path separators or '..')",
        )
    return raw


def _data_path(store: ProjectStore, project: str, file: str):
    project_dir = _project_dir(store, project)
    return project_dir, _inside(_data_dir(project_dir), _data_name(file))


def split_header(cell: str) -> dict[str, str]:
    """``"q1 [rad]"`` to ``{"name": "q1", "unit": "rad"}``."""
    text = cell.strip().strip('"').strip()
    match = _UNIT_HEADER.match(text)
    if match:
        return {"name": match.group(1).strip(), "unit": match.group(2).strip()}
    return {"name": text, "unit": ""}


def _dialect(header_line: str) -> str:
    best, count = ",", header_line.count(",")
    for candidate in (";", "\t"):
        if header_line.count(candidate) > count:
            best, count = candidate, header_line.count(candidate)
    return best


def preview_csv(text: str, rows: int = 10) -> dict[str, Any]:
    """Header, row count and the first ``rows`` data rows of CSV text (422 if unusable)."""
    text = text.removeprefix("﻿")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ProjectError(
            422, "the CSV file is empty; it needs a header row with the column names, then numeric rows"
        )
    delimiter = _dialect(lines[0])
    header = next(csv.reader([lines[0]], delimiter=delimiter))
    columns = [split_header(cell) for cell in header]
    head: list[list[float | str]] = []
    for number, line in enumerate(lines[1:], start=1):
        cells = next(csv.reader([line], delimiter=delimiter))
        if len(cells) != len(columns):
            raise ProjectError(
                422,
                f"data row {number} has {len(cells)} cells but the header has {len(columns)} "
                "columns; check the delimiter and that no cell is missing",
            )
        if number <= rows:
            parsed: list[float | str] = []
            for cell in cells:
                try:
                    parsed.append(float(cell))
                except ValueError:
                    parsed.append(cell.strip())
            head.append(parsed)
    return {"columns": columns, "rows": max(len(lines) - 1, 0), "head": head, "delimiter": delimiter}


def check_modal(text: str, name: str) -> dict[str, Any]:
    """The parsed reduced-model document, or 422 when it is not a ``bgsim.modal-body`` file.

    Only the header is checked here; the compiler validates the matrices when it reads the file.
    """
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProjectError(
            422, f"{name!r} is not valid JSON ({exc}); {_MODAL_HINT} again"
        ) from exc
    if not isinstance(document, dict) or document.get("format") != MODAL_FORMAT:
        raise ProjectError(
            422,
            f"{name!r} is not a reduced-model file (it needs \"format\": \"{MODAL_FORMAT}\"); "
            f"{_MODAL_HINT}",
        )
    version = document.get("version")
    if isinstance(version, bool) or version != MODAL_VERSION:
        raise ProjectError(
            422,
            f"{name!r} has version {version!r} of the reduced-model format; this server reads "
            f"version {MODAL_VERSION}. Write the file again with the BGSimFEM of this checkout",
        )
    return document


def _decode(raw: bytes, label: str, what: str = "the CSV") -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProjectError(
            400, f"{label} is not UTF-8 text ({exc}); save {what} as UTF-8 and try again"
        ) from exc


def _check_size(size: int) -> None:
    if size > MAX_DATA_BYTES:
        raise ProjectError(
            413,
            f"the data file is {size} bytes; the limit is {MAX_DATA_BYTES}. "
            "Reduce the number of rows or columns (for example resample to a coarser time step).",
        )


@router.get("/projects/{project}/data")
def list_data(
    project: str, store: Store, kind: Literal["csv", "modal", "all"] = Query("csv")
) -> list[dict[str, Any]]:
    """The data files of ``data/`` of one kind (CSV by default, or all), sorted by name."""
    directory = _data_dir(_project_dir(store, project))
    if not directory.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        found = data_kind(path.name)
        if found is None or not path.is_file() or not _is_safe_name(path.name):
            continue
        if kind in ("all", found):
            out.append({"file": path.name, "bytes": path.stat().st_size, "kind": found})
    return out


@router.get("/projects/{project}/data/{file}")
def get_data(project: str, file: str, store: Store) -> Response:
    """One data file as text (CSV, or the JSON of a reduced model)."""
    _, path = _data_path(store, project, file)
    if not path.is_file():
        raise ProjectError(404, f"unknown data file {file!r} in project {project!r}")
    return Response(path.read_bytes(), media_type=MEDIA_TYPES[data_kind(file) or "csv"])


@router.get("/projects/{project}/data/{file}/preview")
def preview_data(
    project: str, file: str, store: Store, rows: int = Query(10, ge=0, le=200)
) -> dict[str, Any]:
    """Header, row count and the first rows of one CSV file."""
    _, path = _data_path(store, project, file)
    if data_kind(file) != "csv":
        raise ProjectError(
            400,
            f"{file!r} is not a CSV file and the preview reads CSV files only; fetch a "
            "reduced-model file with GET /api/projects/{project}/data/{file} instead",
        )
    if not path.is_file():
        raise ProjectError(404, f"unknown data file {file!r} in project {project!r}")
    result = preview_csv(_decode(path.read_bytes(), file), rows)
    result.update({"project": project, "file": file, "path": f"{DATA_DIR}/{file}",
                   "bytes": path.stat().st_size})
    return result


def _store_csv(project_dir, name: str, raw: bytes) -> dict[str, Any]:
    _check_size(len(raw))
    if not raw.strip():
        raise ProjectError(400, f"the data file {name!r} is empty; send the CSV text as the body")
    text = _decode(raw, name)
    result = preview_csv(text, 0)  # validates header and cell counts before anything is stored
    path = _inside(_data_dir(project_dir), name)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    _atomic_write_bytes(path, normalized)
    return {
        "project": project_dir.name,
        "file": name,
        "path": f"{DATA_DIR}/{name}",
        "bytes": len(normalized),
        "rows": result["rows"],
        "columns": result["columns"],
    }


def _store_modal(project_dir, name: str, raw: bytes) -> dict[str, Any]:
    _check_size(len(raw))
    if not raw.strip():
        raise ProjectError(
            400, f"the data file {name!r} is empty; send the reduced-model JSON as the body"
        )
    text = _decode(raw, name, "the reduced-model file")
    document = check_modal(text, name)  # validates the header before anything is stored
    path = _inside(_data_dir(project_dir), name)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    _atomic_write_bytes(path, normalized)
    title, nm = document.get("name"), document.get("nm")
    return {
        "project": project_dir.name,
        "file": name,
        "path": f"{DATA_DIR}/{name}",
        "bytes": len(normalized),
        "kind": "modal",
        "name": title if isinstance(title, str) else None,
        "nm": nm if isinstance(nm, int) and not isinstance(nm, bool) else None,
    }


def _store(project_dir, name: str, raw: bytes) -> dict[str, Any]:
    if data_kind(name) == "modal":
        return _store_modal(project_dir, name, raw)
    return _store_csv(project_dir, name, raw)


@router.put("/projects/{project}/data/{file}")
async def put_data(project: str, file: str, request: Request, store: Store) -> dict[str, Any]:
    """Replace (or create) one data file; the body is the CSV or reduced-model JSON text."""
    project_dir, _ = _data_path(store, project, file)
    return _store(project_dir, _data_name(file), await request.body())


@router.delete("/projects/{project}/data/{file}", status_code=204)
def delete_data(project: str, file: str, store: Store) -> Response:
    """Remove one data file."""
    _, path = _data_path(store, project, file)
    if not path.is_file():
        raise ProjectError(404, f"unknown data file {file!r} in project {project!r}")
    path.unlink()
    return Response(status_code=204)


def _upload_name(upload_name: str) -> str:
    base = upload_name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if base.lower().endswith(MODAL_SUFFIX):
        stem, suffix = base[: -len(MODAL_SUFFIX)], MODAL_SUFFIX
    else:
        stem, dot, extension = base.rpartition(".")
        if not dot or extension.lower() != "csv":
            raise ProjectError(
                415,
                f"unsupported data format for {base!r}: upload a .csv file (export spreadsheets "
                "to CSV first) or a reduced-model .modal.json file (written by julia/BGSimFEM)",
            )
        suffix = CSV_SUFFIX
    safe = "".join(c if c.isalnum() or c in "_-." else "_" for c in stem).strip("_.")
    candidate = f"{safe}{suffix}"
    if not safe or not _is_safe_name(candidate):
        raise ProjectError(
            400,
            f"cannot derive a data file name from {base!r}: rename the file with letters and "
            "digits (for example 'trajectory.csv' or 'bracket.modal.json') and upload again",
        )
    return candidate


@router.post("/projects/{project}/data", status_code=201)
async def upload_data(project: str, request: Request, store: Store) -> dict[str, Any]:
    """Store an uploaded CSV or reduced-model file under ``data/``."""
    project_dir = _project_dir(store, project)
    content_type = request.headers.get("content-type", "").lower()
    if not content_type.startswith("multipart/form-data"):
        raise ProjectError(
            415, "send the data file as multipart/form-data with the file in the field 'file'"
        )
    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise ProjectError(400, "the form has no file; put the data file in the field named 'file'")
    name = _upload_name(upload.filename or "")
    raw = await upload.read(MAX_DATA_BYTES + 1)
    return _store(project_dir, name, raw)
