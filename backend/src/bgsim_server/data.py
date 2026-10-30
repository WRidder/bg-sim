"""Project data files: CSV inputs for ``stdlib:sources/CsvSource`` (work package F5.1).

* ``GET /api/projects/{p}/data`` lists the files of the project's ``data/`` folder
  (``[{"file", "bytes"}]``, sorted by name).
* ``GET /api/projects/{p}/data/{file}`` returns the CSV text (``text/csv``).
* ``PUT /api/projects/{p}/data/{file}`` replaces (or creates) a file; the body is the CSV text
  (UTF-8). ``DELETE`` removes it.
* ``POST /api/projects/{p}/data`` takes a ``multipart/form-data`` upload (field ``file``) of a
  ``.csv`` file and stores it as ``data/<name>.csv``; an upload with the name of an existing
  file replaces it.
* ``GET /api/projects/{p}/data/{file}/preview?rows=10`` returns the header (``columns`` with
  the optional ``[unit]`` split off), the number of data rows and the first rows, so the
  inspector can show what a CsvSource will read.

``file`` is one plain name ending in ``.csv`` (no path separators, ``..`` or drive letters,
like the scene and mesh names). Uploads and PUT bodies are limited to
:data:`MAX_DATA_BYTES` (413 above). Every message says what to do next.
"""

from __future__ import annotations

import csv
import re
from typing import Any

from fastapi import APIRouter, Query, Request, Response
from starlette.datastructures import UploadFile

from .meshes import _atomic_write_bytes
from .projects import ProjectError, ProjectStore, Store, _inside, _is_safe_name

router = APIRouter()

#: Largest accepted data file (bytes): about 1.5 million rows of 10 columns.
MAX_DATA_BYTES = 100 * 1024 * 1024
DATA_DIR = "data"
CSV_SUFFIX = ".csv"
_UNIT_HEADER = re.compile(r"^(.*?)\s*\[([^\]]*)\]\s*$")


def _project_dir(store: ProjectStore, project: str):
    return store._require_project(project)


def _data_dir(project_dir):
    directory = _inside(project_dir, DATA_DIR)
    if directory.is_symlink():
        raise ProjectError(400, f"the data directory of {project_dir.name!r} is a link")
    return directory


def _data_name(raw: str) -> str:
    if not _is_safe_name(raw) or not raw.lower().endswith(CSV_SUFFIX) or raw.lower() == CSV_SUFFIX:
        raise ProjectError(
            400,
            f"invalid data file name {raw!r}: use a single file name such as 'trajectory.csv' "
            "(letters, digits, '_', '-' or '.', ending in .csv, no path separators or '..')",
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


def _decode(raw: bytes, label: str) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProjectError(
            400, f"{label} is not UTF-8 text ({exc}); save the CSV as UTF-8 and try again"
        ) from exc


def _check_size(size: int) -> None:
    if size > MAX_DATA_BYTES:
        raise ProjectError(
            413,
            f"the data file is {size} bytes; the limit is {MAX_DATA_BYTES}. "
            "Reduce the number of rows or columns (for example resample to a coarser time step).",
        )


@router.get("/projects/{project}/data")
def list_data(project: str, store: Store) -> list[dict[str, Any]]:
    """The CSV files of ``data/``, sorted by name."""
    directory = _data_dir(_project_dir(store, project))
    if not directory.is_dir():
        return []
    return [
        {"file": path.name, "bytes": path.stat().st_size}
        for path in sorted(directory.iterdir(), key=lambda p: p.name.lower())
        if path.is_file() and path.suffix.lower() == CSV_SUFFIX and _is_safe_name(path.name)
    ]


@router.get("/projects/{project}/data/{file}")
def get_data(project: str, file: str, store: Store) -> Response:
    """One CSV file as text."""
    _, path = _data_path(store, project, file)
    if not path.is_file():
        raise ProjectError(404, f"unknown data file {file!r} in project {project!r}")
    return Response(path.read_bytes(), media_type="text/csv")


@router.get("/projects/{project}/data/{file}/preview")
def preview_data(
    project: str, file: str, store: Store, rows: int = Query(10, ge=0, le=200)
) -> dict[str, Any]:
    """Header, row count and the first rows of one CSV file."""
    _, path = _data_path(store, project, file)
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


@router.put("/projects/{project}/data/{file}")
async def put_data(project: str, file: str, request: Request, store: Store) -> dict[str, Any]:
    """Replace (or create) one CSV file; the body is the CSV text."""
    project_dir, _ = _data_path(store, project, file)
    return _store_csv(project_dir, _data_name(file), await request.body())


@router.delete("/projects/{project}/data/{file}", status_code=204)
def delete_data(project: str, file: str, store: Store) -> Response:
    """Remove one CSV file."""
    _, path = _data_path(store, project, file)
    if not path.is_file():
        raise ProjectError(404, f"unknown data file {file!r} in project {project!r}")
    path.unlink()
    return Response(status_code=204)


def _upload_name(upload_name: str) -> str:
    base = upload_name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    stem, dot, extension = base.rpartition(".")
    if not dot or extension.lower() != "csv":
        raise ProjectError(
            415, f"unsupported data format for {base!r}: upload a .csv file (export spreadsheets to CSV first)"
        )
    safe = "".join(c if c.isalnum() or c in "_-." else "_" for c in stem).strip("_.")
    candidate = f"{safe}{CSV_SUFFIX}"
    if not safe or not _is_safe_name(candidate):
        raise ProjectError(
            400,
            f"cannot derive a data file name from {base!r}: rename the file with letters and "
            "digits (for example 'trajectory.csv') and upload again",
        )
    return candidate


@router.post("/projects/{project}/data", status_code=201)
async def upload_data(project: str, request: Request, store: Store) -> dict[str, Any]:
    """Store an uploaded CSV file under ``data/``."""
    project_dir = _project_dir(store, project)
    content_type = request.headers.get("content-type", "").lower()
    if not content_type.startswith("multipart/form-data"):
        raise ProjectError(
            415, "send the CSV file as multipart/form-data with the file in the field 'file'"
        )
    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise ProjectError(400, "the form has no file; put the CSV in the field named 'file'")
    name = _upload_name(upload.filename or "")
    raw = await upload.read(MAX_DATA_BYTES + 1)
    return _store_csv(project_dir, name, raw)

