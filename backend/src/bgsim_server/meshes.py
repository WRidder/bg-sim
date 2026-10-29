"""Scenes and meshes of a project (plan sections 3.7 and 7; work package P5.1).

* ``GET /api/projects/{p}/scenes/{file}`` returns an SDF scene as ``application/xml``
  text; ``PUT`` replaces it atomically with LF line endings (the body is the SDF
  text itself, like the library PUT). The directory is the project's ``scenesDir``
  (``scenes/``). ``file`` is one plain file name ending in ``.sdf``: path
  separators, ``..``, drive letters and Windows reserved names are refused with 400.
* ``GET /api/projects/{p}/meshes/{file}`` serves a stored GLB as ``model/gltf-binary``.
* ``POST /api/projects/{p}/meshes`` takes a ``multipart/form-data`` upload (field
  ``file``) of an STL, OBJ, DAE or GLB, converts it to GLB with trimesh and stores it
  as ``meshes/<stem>.glb``. The answer is ``{"project", "path", "file", "bytes",
  "vertices", "faces"}`` where ``path`` is the project-relative path to reference from
  an SDF scene (for example ``meshes/arm.glb``). An upload with the name of an
  existing mesh replaces it. DAE needs ``pycollada``, which is a dependency, so all
  four formats are supported. Uploads are limited to :data:`MAX_UPLOAD_BYTES`
  (413 above), unknown extensions get 415, unreadable or empty meshes get 422; every
  message says what to do next.

Meshes are written with a temp file + ``os.replace`` so a reader never sees a half
written GLB.
"""

from __future__ import annotations

import asyncio
import io
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

import trimesh
from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from starlette.datastructures import UploadFile

from .projects import (
    ProjectError,
    ProjectStore,
    Store,
    _atomic_write,
    _inside,
    _is_safe_name,
    _lf,
    _read_text,
    _relative_dir,
)

router = APIRouter()

#: Largest accepted upload (bytes); bigger meshes should be decimated first.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
#: Largest accepted SDF scene (bytes).
MAX_SCENE_BYTES = 8 * 1024 * 1024
MESH_DIR = "meshes"
SCENE_SUFFIX = ".sdf"
GLB_SUFFIX = ".glb"
GLB_MEDIA_TYPE = "model/gltf-binary"
#: Source extension (without dot) to trimesh ``file_type``.
MESH_FORMATS = {"stl": "stl", "obj": "obj", "dae": "dae", "glb": "glb"}


# --------------------------------------------------------------------------- paths


def _project_dir(store: ProjectStore, project: str) -> Path:
    return store._require_project(project)


def _scene_name(raw: str) -> str:
    if not _is_safe_name(raw) or not raw.lower().endswith(SCENE_SUFFIX) or raw.lower() == SCENE_SUFFIX:
        raise ProjectError(
            400,
            f"invalid scene file name {raw!r}: use a single file name such as 'robot.sdf' "
            "(letters, digits, '_', '-' or '.', ending in .sdf, no path separators or '..')",
        )
    return raw


def _mesh_name(raw: str) -> str:
    if not _is_safe_name(raw) or not raw.lower().endswith(GLB_SUFFIX) or raw.lower() == GLB_SUFFIX:
        raise ProjectError(
            400,
            f"invalid mesh file name {raw!r}: use a single file name such as 'arm.glb' "
            "(letters, digits, '_', '-' or '.', ending in .glb, no path separators or '..')",
        )
    return raw


def _scenes_dir(store: ProjectStore, project_dir: Path) -> Path:
    project = store._load_project(project_dir)
    directory = _relative_dir(project_dir, project.scenesDir, "scenesDir")
    if directory.exists() and not directory.is_dir():
        raise ProjectError(
            422, f"the project file field scenesDir={project.scenesDir!r} is not a directory"
        )
    return directory


def _meshes_dir(project_dir: Path) -> Path:
    directory = _inside(project_dir, MESH_DIR)
    if directory.is_symlink():
        raise ProjectError(400, f"the meshes directory of {project_dir.name!r} is a link")
    return directory


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except OSError as exc:
        with suppress(OSError):
            os.unlink(temp_name)
        raise ProjectError(500, f"could not write {path}: {exc}") from exc
    except BaseException:
        with suppress(OSError):
            os.unlink(temp_name)
        raise


# --------------------------------------------------------------------------- scenes


@router.get("/projects/{project}/scenes/{file}")
def get_scene(project: str, file: str, store: Store) -> Response:
    """The SDF text of one scene (LF line endings)."""
    project_dir = _project_dir(store, project)
    path = _inside(_scenes_dir(store, project_dir), _scene_name(file))
    if not path.is_file():
        raise ProjectError(404, f"unknown scene {file!r} in project {project!r}")
    text = _read_text(path).replace("\r\n", "\n").replace("\r", "\n")
    return PlainTextResponse(text, media_type="application/xml")


@router.put("/projects/{project}/scenes/{file}")
async def put_scene(project: str, file: str, request: Request, store: Store) -> dict[str, Any]:
    """Replace (or create) one scene; the body is the SDF text."""
    project_dir = _project_dir(store, project)
    name = _scene_name(file)
    path = _inside(_scenes_dir(store, project_dir), name)
    raw = await request.body()
    if len(raw) > MAX_SCENE_BYTES:
        raise ProjectError(
            413, f"the scene is {len(raw)} bytes; the limit is {MAX_SCENE_BYTES}. Split the scene."
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectError(400, f"the scene is not UTF-8 text: {exc}") from exc
    if not text.strip():
        raise ProjectError(400, "the scene is empty; send the SDF document as the request body")
    _atomic_write(path, text)
    stored = _lf(text)
    return {
        "project": project_dir.name,
        "file": name,
        "path": f"{path.parent.name}/{name}",
        "bytes": len(stored.encode("utf-8")),
    }


# --------------------------------------------------------------------------- meshes


@router.get("/projects/{project}/meshes/{file}")
def get_mesh(project: str, file: str, store: Store) -> FileResponse:
    """One stored GLB as ``model/gltf-binary``."""
    project_dir = _project_dir(store, project)
    path = _inside(_meshes_dir(project_dir), _mesh_name(file))
    if not path.is_file():
        raise ProjectError(404, f"unknown mesh {file!r} in project {project!r}")
    return FileResponse(path, media_type=GLB_MEDIA_TYPE)


def _stored_stem(upload_name: str) -> tuple[str, str]:
    """``(stem, extension)`` of an uploaded file name, or a 400/415 error."""
    base = upload_name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    stem, dot, extension = base.rpartition(".")
    extension = extension.lower()
    if not dot or extension not in MESH_FORMATS:
        raise ProjectError(
            415,
            f"unsupported mesh format for {base!r}: upload an .stl, .obj, .dae or .glb file "
            "(export other formats to one of these first)",
        )
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in stem).strip("_")
    candidate = f"{safe}{GLB_SUFFIX}"
    if not safe or not _is_safe_name(candidate):
        raise ProjectError(
            400,
            f"cannot derive a mesh name from {base!r}: rename the file with letters and digits "
            "(for example 'arm.stl') and upload again",
        )
    return safe, extension


def convert_to_glb(data: bytes, extension: str, label: str) -> tuple[bytes, int, int]:
    """Convert mesh bytes to ``(glb, vertex_count, face_count)`` with trimesh."""
    file_type = MESH_FORMATS[extension]
    try:
        loaded = trimesh.load(io.BytesIO(data), file_type=file_type, force="scene")
    except Exception as exc:
        raise ProjectError(
            422,
            f"could not read {label!r} as {extension.upper()}: {exc}. Check that the file is a "
            "valid mesh (binary STL and GLB are the most robust) and upload again",
        ) from exc
    geometries = [
        geometry
        for geometry in loaded.geometry.values()
        if isinstance(geometry, trimesh.Trimesh) and len(geometry.faces) > 0
    ]
    if not geometries:
        raise ProjectError(
            422,
            f"{label!r} contains no triangle mesh; export the solid body (not only lines, "
            "points or a point cloud) and upload again",
        )
    try:
        glb = loaded.export(file_type="glb")
    except Exception as exc:
        raise ProjectError(422, f"could not convert {label!r} to GLB: {exc}") from exc
    vertices = sum(len(geometry.vertices) for geometry in geometries)
    faces = sum(len(geometry.faces) for geometry in geometries)
    return bytes(glb), vertices, faces


async def _read_limited(upload: UploadFile) -> bytes:
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ProjectError(
            413,
            f"the mesh is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB; decimate it or "
            "split it into smaller parts and upload again",
        )
    return data


@router.post("/projects/{project}/meshes", status_code=201)
async def upload_mesh(project: str, request: Request, store: Store) -> dict[str, Any]:
    """Convert an uploaded STL/OBJ/DAE/GLB to GLB and store it under ``meshes/``."""
    project_dir = _project_dir(store, project)
    content_type = request.headers.get("content-type", "").lower()
    if not content_type.startswith("multipart/form-data"):
        raise ProjectError(
            415, "send the mesh as multipart/form-data with the file in the field 'file'"
        )
    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise ProjectError(400, "the form has no file; put the mesh in the field named 'file'")
    stem, extension = _stored_stem(upload.filename or "")
    data = await _read_limited(upload)
    if not data:
        raise ProjectError(400, f"the uploaded file {upload.filename!r} is empty")
    glb, vertices, faces = await asyncio.to_thread(
        convert_to_glb, data, extension, upload.filename or stem
    )
    name = f"{stem}{GLB_SUFFIX}"
    path = _inside(_meshes_dir(project_dir), name)
    _atomic_write_bytes(path, glb)
    return {
        "project": project_dir.name,
        "file": name,
        "path": f"{MESH_DIR}/{name}",
        "bytes": len(glb),
        "vertices": vertices,
        "faces": faces,
    }
