"""Project, model and library endpoints (plan sections 3.3, 3.7 and 6).

A project is a directory below ``projects_root`` (``~/bgsim-projects`` by default,
``BGSIM_PROJECTS_ROOT``) that holds ``bgsim.project.json``, the ``models/`` documents,
the project library and the scenes. This module keeps that tree safe:

* every project, model, block and example name is validated (no ``..``, no
  separators, no drive letters, no leading/trailing dot, no Windows device name);
* every path is resolved and checked to stay inside its project directory;
* every write goes to a temporary file in the target directory and is moved into
  place with :func:`os.replace`, with LF newlines (plan section 6);
* model documents are validated with the generated :class:`bgsim_server.contracts.Model`
  model and project documents with :class:`bgsim_server.contracts.Project`.

Endpoint summary (all under ``/api``)::

    GET    /projects                              list project summaries
    POST   /projects                              {name, example?} -> open payload, 201
    GET    /examples                              the examples POST /projects can copy
    GET    /projects/{p}                          the project file plus listings
    PUT    /projects/{p}                          replace the project file
    DELETE /projects/{p}                          remove the project directory
    GET    /projects/{p}/models/{m}               the model document (JSON)
    PUT    /projects/{p}/models/{m}               validate, write and return it
    DELETE /projects/{p}/models/{m}               remove it, its docs folder and its tab entry
    GET    /projects/{p}/library/{block}          the block source (text/plain)
    PUT    /projects/{p}/library/{block}          write the source
    DELETE /projects/{p}/library/{block}          remove it

``{m}`` is the model name (the file is ``models/<m>.bgmodel.json``); a trailing
``.bgmodel.json`` is accepted and stripped. ``{block}`` is the block name (the file
is ``library/<block>.jl``); a trailing ``.jl`` is accepted and stripped. The
project file's ``models`` list is kept in sync by model PUT and DELETE, so a new
model appears as the last tab and a deleted model disappears.

``GET /projects`` returns ``{root, projects: [{name, path, language, models,
modified, valid, error}]}``. ``GET /projects/{p}`` returns ``{name, path, project,
models: [{name, modified, inProject}], library: [{name, modified}]}``; a model that
exists on disk but is not in the project file's tab list has ``inProject: false``.

Errors are ordinary FastAPI errors: 400 for an unsafe name or path, 404 for an
unknown project/model/block/example, 409 for a name that already exists, 422 for a
document that violates the contract (``detail.errors`` holds the schema and pydantic
errors) and 500 for an I/O failure. They are not language diagnostics (plan 3.4), so
they have no ``E``/``W`` code.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, ValidationError
from referencing import Registry, Resource

from .config import BACKEND_VERSION, Settings
from .contracts import Model, Project

router = APIRouter()

PROJECT_FILE = "bgsim.project.json"
MODEL_SUFFIX = ".bgmodel.json"
LIBRARY_SUFFIX = ".jl"
#: The docs folder of a model lives next to its file: ``models/<m>.docs/`` (work package W5.6).
DOCS_SUFFIX = ".docs"

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_BLOCK_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WINDOWS_RESERVED = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.IGNORECASE
)


class ProjectError(HTTPException):
    """An HTTP error raised by the store; subclasses :class:`HTTPException`."""

    def __init__(
        self, status_code: int, message: str, *, errors: list[dict[str, Any]] | None = None
    ):
        detail: str | dict[str, Any] = (
            message if errors is None else {"message": message, "errors": errors}
        )
        super().__init__(status_code=status_code, detail=detail)


# --------------------------------------------------------------------------- names


def _is_safe_name(name: str) -> bool:
    """A single, portable file or directory name (no path syntax at all)."""
    if not isinstance(name, str) or not _NAME_PATTERN.fullmatch(name):
        return False
    if name in {".", ".."} or name.startswith(".") or name.endswith("."):
        return False
    return not _WINDOWS_RESERVED.fullmatch(name)


def _invalid_name(kind: str, name: str, allowed: str) -> ProjectError:
    return ProjectError(
        400,
        f"invalid {kind} name {name!r}: {allowed}; it must be a single file name "
        "without '..', path separators or a drive letter",
    )


def _validate_name(name: str, kind: str) -> str:
    if not _is_safe_name(name):
        raise _invalid_name(kind, name, "use letters, digits, '_', '-' or '.'")
    return name


def _project_name(name: str) -> str:
    return _validate_name(name, "project")


def _model_name(raw: str) -> str:
    """A model name; ``iconic.bgmodel.json`` is accepted as ``iconic``."""
    return _validate_name(raw.removesuffix(MODEL_SUFFIX), "model")


def _block_name(raw: str) -> str:
    """A block name; ``Foo.jl`` is accepted as ``Foo``."""
    name = raw.removesuffix(LIBRARY_SUFFIX)
    if not _BLOCK_PATTERN.fullmatch(name):
        raise _invalid_name(
            "block",
            raw,
            "use a Julia identifier: a letter or '_', then letters, digits or '_'",
        )
    if _WINDOWS_RESERVED.fullmatch(name):
        raise ProjectError(400, f"invalid block name {raw!r}: {name!r} is reserved on Windows")
    return name


def _example_name(name: str) -> str:
    return _validate_name(name, "example")


# --------------------------------------------------------------------------- paths


def _inside(root: Path, *parts: str) -> Path:
    """``root/parts`` with a resolved path that must stay inside ``root``."""
    candidate = root.joinpath(*parts)
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ProjectError(400, f"path {candidate} escapes {root}")
    return candidate


def _relative_dir(project_dir: Path, value: str, field: str) -> Path:
    """A project-file directory field, relative and confined to the project."""
    relative = Path(value)
    if (
        relative.is_absolute()
        or relative.drive
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ProjectError(
            422,
            f"the project file field {field}={value!r} must be a relative directory "
            "inside the project",
        )
    candidate = (project_dir / relative).resolve()
    if not candidate.is_relative_to(project_dir):
        raise ProjectError(
            422, f"the project file field {field}={value!r} escapes the project directory"
        )
    return candidate


# --------------------------------------------------------------------------- files


def _lf(text: str) -> str:
    """Normalise every newline to LF and guarantee one at the end."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text if text.endswith("\n") else text + "\n"


def _json_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _clean_comments(value: Any) -> Any:
    """Drop ``"$comment": null`` everywhere; the contract wants a string or no key.

    The generated pydantic models allow ``None`` for every ``$comment`` field, but
    the JSON Schemas only allow a string when the key is present. A pydantic dump of
    a document without comments would otherwise add invalid null keys at every level.
    """
    if isinstance(value, dict):
        return {
            key: _clean_comments(item)
            for key, item in value.items()
            if not (key == "$comment" and item is None)
        }
    if isinstance(value, list):
        return [_clean_comments(item) for item in value]
    return value


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` (LF) to a temp file next to ``path`` and replace atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _lf(text).encode("utf-8")
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


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ProjectError(404, f"{path} does not exist") from exc
    except UnicodeDecodeError as exc:
        raise ProjectError(422, f"{path} is not UTF-8 text: {exc}") from exc
    except OSError as exc:
        raise ProjectError(500, f"could not read {path}: {exc}") from exc


def _read_json(path: Path) -> Any:
    raw = _read_text(path)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProjectError(
            422,
            f"{path} is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})",
        ) from exc


def _validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]


def _validate(schema: type[BaseModel], document: Any, what: str) -> Any:
    """Validate a contract document; on failure raise 422 with the pydantic details."""
    try:
        return schema.model_validate(document)
    except ValidationError as exc:
        errors = _validation_errors(exc)
        first = errors[0]
        location = ".".join(str(part) for part in first["loc"]) or "<root>"
        raise ProjectError(
            422,
            f"{what} is invalid: {location}: {first['msg']}",
            errors=errors,
        ) from None


@lru_cache(maxsize=16)
def _schema_validator(schemas_root: str, schema_name: str) -> Draft202012Validator:
    """The validator for one contract schema, with every schema in its registry."""
    directory = Path(schemas_root)
    documents = {
        path.name[: -len(".schema.json")]: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(directory.glob("*.schema.json"))
    }
    registry = Registry().with_resources(
        [(document["$id"], Resource.from_contents(document)) for document in documents.values()]
    )
    return Draft202012Validator(documents[schema_name], registry=registry)


def _schema_errors(validator: Draft202012Validator, document: Any) -> list[dict[str, Any]]:
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    return [
        {"loc": list(error.path), "msg": error.message, "type": "schema"} for error in errors
    ]


def _timestamp(path: Path) -> str | None:
    """The file's mtime as an ISO 8601 UTC string, or ``None`` when unreadable."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
    except OSError:
        return None


def _detail_message(detail: Any) -> str:
    if isinstance(detail, dict):
        return str(detail.get("message", detail))
    return str(detail)


# --------------------------------------------------------------------------- store


class ProjectStore:
    """Safe access to the project tree below ``projects_root``.

    ``examples_root`` defaults to ``None`` (no examples available); the FastAPI
    dependency passes ``<repo>/examples``. Tests pass a temporary directory.
    ``schemas_root`` is the directory with the contract schemas; when it is set,
    documents are also checked against the JSON Schema itself (the generated
    pydantic models are more permissive about explicit nulls, so both passes run).
    """

    def __init__(
        self,
        projects_root: Path,
        examples_root: Path | None = None,
        schemas_root: Path | None = None,
    ):
        self.projects_root = Path(projects_root).expanduser()
        self.examples_root = Path(examples_root).expanduser() if examples_root else None
        self.schemas_root = Path(schemas_root).expanduser() if schemas_root else None

    # ------------------------------------------------------------------ paths

    @property
    def root(self) -> Path:
        return self.projects_root.resolve()

    def _project_path(self, name: str) -> Path:
        """The directory of ``name``, validated but not required to exist."""
        name = _project_name(name)
        root = self.root
        candidate = root / name
        if candidate.is_symlink():
            raise ProjectError(400, f"project {name!r} is a symbolic link")
        if candidate.exists():
            resolved = candidate.resolve()
            if not resolved.is_relative_to(root):
                raise ProjectError(400, f"project {name!r} escapes the projects root")
            if not resolved.is_dir():
                raise ProjectError(404, f"unknown project {name!r}")
            return resolved
        return candidate

    def _require_project(self, name: str) -> Path:
        directory = self._project_path(name)
        if not directory.is_dir() or not (directory / PROJECT_FILE).is_file():
            raise ProjectError(404, f"unknown project {name!r}")
        return directory

    def _project_file(self, project_dir: Path) -> Path:
        return _inside(project_dir, PROJECT_FILE)

    def _models_dir(self, project_dir: Path) -> Path:
        directory = _inside(project_dir, "models")
        if directory.is_symlink():
            raise ProjectError(400, f"the models directory of {project_dir.name!r} is a link")
        return directory

    def _model_path(self, project_dir: Path, model_name: str) -> Path:
        return _inside(self._models_dir(project_dir), f"{model_name}{MODEL_SUFFIX}")

    def _library_dir(self, project_dir: Path, project: Project) -> Path:
        directory = _relative_dir(project_dir, project.libraryDir, "libraryDir")
        if directory.exists() and not directory.is_dir():
            raise ProjectError(
                422,
                f"the project file field libraryDir={project.libraryDir!r} is not a directory",
            )
        return directory

    def _library_path(self, project_dir: Path, project: Project, block: str) -> Path:
        return _inside(self._library_dir(project_dir, project), f"{block}{LIBRARY_SUFFIX}")

    # ------------------------------------------------------------------ documents

    def _check_schema(self, schema_name: str, document: Any, what: str) -> None:
        """Validate against the JSON Schema when ``schemas_root`` is configured."""
        if self.schemas_root is None:
            return
        validator = _schema_validator(str(self.schemas_root.resolve()), schema_name)
        errors = _schema_errors(validator, document)
        if errors:
            first = errors[0]
            location = ".".join(str(part) for part in first["loc"]) or "<root>"
            raise ProjectError(
                422,
                f"{what} does not match {schema_name}.schema.json: "
                f"{location}: {first['msg']}",
                errors=errors,
            )

    def _project_from_document(self, document: Any, what: str) -> Project:
        self._check_schema("project", document, what)
        return _validate(Project, document, what)

    def _load_project(self, project_dir: Path) -> Project:
        path = self._project_file(project_dir)
        if not path.is_file():
            raise ProjectError(404, f"unknown project {project_dir.name!r}")
        document = _read_json(path)
        project = self._project_from_document(
            document, f"the project file of project {project_dir.name!r}"
        )
        if project.name != project_dir.name:
            raise ProjectError(
                422,
                f"the project file names {project.name!r}, but its directory is "
                f"{project_dir.name!r}; rename one of them",
            )
        self._library_dir(project_dir, project)  # reject an escaping libraryDir early
        return project

    def _write_project(self, project_dir: Path, project: Project) -> None:
        payload = _clean_comments(project.model_dump(by_alias=True, mode="json"))
        _atomic_write(self._project_file(project_dir), _json_text(payload))

    def _model_names_on_disk(self, project_dir: Path) -> list[str]:
        models_dir = self._models_dir(project_dir)
        if not models_dir.is_dir():
            return []
        names: list[str] = []
        for path in models_dir.iterdir():
            if path.is_file() and not path.is_symlink() and path.name.endswith(MODEL_SUFFIX):
                stem = path.name[: -len(MODEL_SUFFIX)]
                if _is_safe_name(stem):
                    names.append(stem)
        return sorted(names, key=str.lower)

    def _model_listing(self, project_dir: Path, project: Project) -> list[dict[str, Any]]:
        models_dir = self._models_dir(project_dir)
        listing: list[dict[str, Any]] = []
        if models_dir.is_dir():
            for path in models_dir.iterdir():
                if not path.is_file() or path.is_symlink() or not path.name.endswith(MODEL_SUFFIX):
                    continue
                stem = path.name[: -len(MODEL_SUFFIX)]
                if not _is_safe_name(stem):
                    continue
                listing.append(
                    {
                        "name": stem,
                        "modified": _timestamp(path),
                        "inProject": stem in project.models,
                    }
                )
        order = {name: index for index, name in enumerate(project.models)}
        listing.sort(key=lambda item: (order.get(item["name"], len(order)), item["name"].lower()))
        return listing

    def _library_listing(self, project_dir: Path, project: Project) -> list[dict[str, Any]]:
        library_dir = self._library_dir(project_dir, project)
        if not library_dir.is_dir():
            return []
        listing = []
        for path in library_dir.iterdir():
            if not path.is_file() or path.is_symlink() or not path.name.endswith(LIBRARY_SUFFIX):
                continue
            name = path.name[: -len(LIBRARY_SUFFIX)]
            if _BLOCK_PATTERN.fullmatch(name):
                listing.append({"name": name, "modified": _timestamp(path)})
        listing.sort(key=lambda item: item["name"].lower())
        return listing

    # ------------------------------------------------------------------ projects

    def list_projects(self) -> list[dict[str, Any]]:
        """Every directory with a project file, sorted by name; broken ones included."""
        root = self.root
        if not root.is_dir():
            return []
        summaries: list[dict[str, Any]] = []
        for directory in root.iterdir():
            if (
                not directory.is_dir()
                or directory.is_symlink()
                or not _is_safe_name(directory.name)
            ):
                continue
            project_file = directory / PROJECT_FILE
            if not project_file.is_file():
                continue
            resolved = directory.resolve()
            if not resolved.is_relative_to(root):
                continue
            summary: dict[str, Any] = {
                "name": directory.name,
                "path": str(resolved),
                "language": None,
                "models": [],
                "modified": _timestamp(project_file),
                "valid": False,
                "error": None,
            }
            try:
                project = self._load_project(resolved)
            except HTTPException as exc:
                summary["error"] = _detail_message(exc.detail)
                with suppress(HTTPException):
                    summary["models"] = self._model_names_on_disk(resolved)
            else:
                summary["language"] = project.language
                summary["models"] = list(project.models)
                summary["valid"] = True
            summaries.append(summary)
        summaries.sort(key=lambda item: item["name"].lower())
        return summaries

    def open_project(self, name: str) -> dict[str, Any]:
        """The project file plus its model and library listings (plan 3.7)."""
        project_dir = self._require_project(name)
        project = self._load_project(project_dir)
        return {
            "name": project_dir.name,
            "path": str(project_dir),
            "project": _clean_comments(project.model_dump(by_alias=True, mode="json")),
            "models": self._model_listing(project_dir, project),
            "library": self._library_listing(project_dir, project),
        }

    def create_project(self, name: str, example: str | None = None) -> dict[str, Any]:
        """Create an empty project or copy ``examples/<example>`` (plan 3.7)."""
        name = _project_name(name)
        root = self.root
        destination = root / name
        if destination.exists() or destination.is_symlink():
            raise ProjectError(409, f"a project named {name!r} already exists")
        root.mkdir(parents=True, exist_ok=True)
        staging = root / f".{name}.creating-{uuid.uuid4().hex}"
        try:
            if example:
                source = self._example_source(example)
                try:
                    shutil.copytree(source, staging)
                except OSError as exc:
                    raise ProjectError(
                        500, f"could not copy example {example!r} from {source}: {exc}"
                    ) from exc
                self._prepare_example(staging, name, example)
            else:
                staging.mkdir()
                project = Project(
                    format="bgsim.project",
                    language=BACKEND_VERSION,
                    name=name,
                    models=[],
                    libraryDir="library",
                    scenesDir="scenes",
                )
                for directory in ("models", project.libraryDir, project.scenesDir):
                    (staging / directory).mkdir(parents=True, exist_ok=True)
                self._write_project(staging, project)
            os.replace(staging, destination)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return self.open_project(name)

    def _prepare_example(self, staging: Path, name: str, example: str) -> None:
        """Give a copied example tree the requested name and a valid project file."""
        project_file = staging / PROJECT_FILE
        if project_file.is_file():
            document = _read_json(project_file)
            project = self._project_from_document(
                document, f"the project file of example {example!r}"
            )
            project.name = name
        else:
            project = Project(
                format="bgsim.project",
                language=BACKEND_VERSION,
                name=name,
                models=self._model_names_on_disk(staging),
                libraryDir="library",
                scenesDir="scenes",
            )
        for directory in ("models", project.libraryDir, project.scenesDir):
            relative = _relative_dir(staging, directory, "project directory")
            if relative.exists() and not relative.is_dir():
                raise ProjectError(
                    422, f"the example's project directory entry {directory!r} is not a directory"
                )
            relative.mkdir(parents=True, exist_ok=True)
        self._write_project(staging, project)

    def put_project(self, name: str, document: dict[str, Any]) -> dict[str, Any]:
        """Replace the project file; the directory name stays authoritative."""
        project_dir = self._require_project(name)
        project = self._project_from_document(document, "the project document")
        if project.name != project_dir.name:
            raise ProjectError(
                400,
                f"the project document names {project.name!r}, but the project is "
                f"{project_dir.name!r}",
            )
        self._library_dir(project_dir, project)
        _atomic_write(self._project_file(project_dir), _json_text(document))
        return self.open_project(name)

    def delete_project(self, name: str) -> str:
        """Remove the project directory; returns the canonical name for the cache."""
        project_dir = self._require_project(name)
        try:
            shutil.rmtree(project_dir)
        except OSError as exc:
            raise ProjectError(500, f"could not delete {project_dir}: {exc}") from exc
        return project_dir.name

    def available_examples(self) -> list[str]:
        root = self.examples_root
        if root is None or not root.is_dir():
            return []
        return sorted(
            (
                path.name
                for path in root.iterdir()
                if path.is_dir()
                and not path.is_symlink()
                and _is_safe_name(path.name)
                # tool folders such as __pycache__ or .ipynb_checkpoints are not examples
                and not path.name.startswith(("__", "."))
            ),
            key=str.lower,
        )

    def _example_source(self, example: str) -> Path:
        example = _example_name(example)
        root = self.examples_root
        if root is not None and root.is_dir():
            resolved_root = root.resolve()
            candidate = root / example
            if candidate.is_dir() and not candidate.is_symlink():
                resolved = candidate.resolve()
                if resolved.is_relative_to(resolved_root):
                    return resolved
        available = self.available_examples()
        names = ", ".join(available) if available else "(none)"
        raise ProjectError(
            404, f"unknown example {example!r}; available examples: {names}"
        )

    # ------------------------------------------------------------------ models

    def get_model(self, name: str, model: str) -> bytes:
        project_dir = self._require_project(name)
        path = self._model_path(project_dir, _model_name(model))
        try:
            data = path.read_bytes()
        except FileNotFoundError as exc:
            raise ProjectError(404, f"unknown model {model!r} in project {name!r}") from exc
        except OSError as exc:
            raise ProjectError(500, f"could not read {path}: {exc}") from exc
        try:
            json.loads(data)
        except ValueError as exc:
            raise ProjectError(
                422, f"the model file {path} is not valid JSON: {exc}"
            ) from exc
        return data

    def put_model(self, name: str, model: str, document: dict[str, Any]) -> dict[str, Any]:
        project_dir = self._require_project(name)
        model_name = _model_name(model)
        project = self._load_project(project_dir)
        self._check_schema("model", document, "the model document")
        _validate(Model, document, "the model document")
        _atomic_write(self._model_path(project_dir, model_name), _json_text(document))
        if model_name not in project.models:
            project.models.append(model_name)
            self._write_project(project_dir, project)
        return document

    def delete_model(self, name: str, model: str) -> str:
        project_dir = self._require_project(name)
        model_name = _model_name(model)
        project = self._load_project(project_dir)
        path = self._model_path(project_dir, model_name)
        if not path.is_file():
            raise ProjectError(404, f"unknown model {model!r} in project {name!r}")
        try:
            path.unlink()
        except OSError as exc:
            raise ProjectError(500, f"could not delete {path}: {exc}") from exc
        docs_dir = path.parent / f"{model_name}{DOCS_SUFFIX}"
        if docs_dir.is_symlink() or docs_dir.is_file():
            docs_dir.unlink()
        elif docs_dir.is_dir():
            try:
                shutil.rmtree(docs_dir)
            except OSError as exc:
                raise ProjectError(
                    500, f"the model was deleted, but its docs folder {docs_dir} was not: {exc}"
                ) from exc
        if model_name in project.models:
            project.models = [entry for entry in project.models if entry != model_name]
            self._write_project(project_dir, project)
        return project_dir.name

    # ------------------------------------------------------------------ library

    def get_library(self, name: str, block: str) -> str:
        project_dir = self._require_project(name)
        project = self._load_project(project_dir)
        path = self._library_path(project_dir, project, _block_name(block))
        text = _read_text(path)
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def put_library(self, name: str, block: str, source: str) -> dict[str, str]:
        project_dir = self._require_project(name)
        project = self._load_project(project_dir)
        block_name = _block_name(block)
        _atomic_write(self._library_path(project_dir, project, block_name), source)
        return {
            "project": project_dir.name,
            "name": block_name,
            "file": f"{block_name}{LIBRARY_SUFFIX}",
        }

    def delete_library(self, name: str, block: str) -> str:
        project_dir = self._require_project(name)
        project = self._load_project(project_dir)
        block_name = _block_name(block)
        path = self._library_path(project_dir, project, block_name)
        if not path.is_file():
            raise ProjectError(404, f"unknown block {block!r} in project {name!r}")
        try:
            path.unlink()
        except OSError as exc:
            raise ProjectError(500, f"could not delete {path}: {exc}") from exc
        return project_dir.name


# --------------------------------------------------------------------------- dependency


def get_project_store(request: Request) -> ProjectStore:
    """The store for the configured projects root (plan section 6)."""
    settings: Settings = request.app.state.settings
    return ProjectStore(
        settings.projects_root,
        settings.repo_root / "examples",
        settings.repo_root / "contracts" / "schemas",
    )


Store = Annotated[ProjectStore, Depends(get_project_store)]


# --------------------------------------------------------------------------- bodies


class CreateProjectBody(BaseModel):
    """``POST /api/projects``: a new project, optionally copied from an example."""

    model_config = ConfigDict(extra="forbid")

    name: str
    example: str | None = None


async def _json_body(request: Request, what: str) -> dict[str, Any]:
    try:
        payload = await request.json()
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError are ValueErrors
        raise ProjectError(422, f"the {what} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProjectError(422, f"the {what} must be a JSON object")
    return payload


async def _library_source(request: Request) -> str:
    """The source text of a library PUT.

    The body is the source itself (``text/plain`` or no content type). For clients
    that JSON-encode everything, a JSON string or ``{"source": "..."}`` is unwrapped
    as well; any other JSON body is stored verbatim.
    """
    raw = await request.body()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectError(400, f"the library source is not UTF-8 text: {exc}") from exc
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type == "application/json":
        try:
            payload = json.loads(text)
        except ValueError:
            return text  # not JSON after all: store the text as sent
        if isinstance(payload, str):
            return payload
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("source"), str)
            and set(payload) <= {"source", "name"}
        ):
            return payload["source"]
    return text


def _invalidate(request: Request, project: str) -> None:
    cache = getattr(request.app.state, "catalog_cache", None)
    if cache is not None:
        cache.invalidate(project)


# --------------------------------------------------------------------------- routes


@router.get("/projects")
def list_projects(store: Store) -> dict[str, Any]:
    """Plan 3.7: list the projects below the configured projects root."""
    return {"root": str(store.root), "projects": store.list_projects()}


@router.get("/examples")
def list_examples(store: Store) -> dict[str, Any]:
    """The example names ``POST /api/projects {name, example}`` can copy."""
    return {"examples": store.available_examples()}


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(body: CreateProjectBody, request: Request, store: Store) -> dict[str, Any]:
    """Plan 3.7: create an empty project or copy one from ``examples/<example>``."""
    result = store.create_project(body.name, body.example or None)
    _invalidate(request, result["name"])
    return result


@router.get("/projects/{project}")
def open_project(project: str, store: Store) -> dict[str, Any]:
    """Plan 3.7: the project file plus its model and library listings."""
    return store.open_project(project)


@router.put("/projects/{project}")
async def put_project(project: str, request: Request, store: Store) -> dict[str, Any]:
    """Replace the project file (tab order, libraryDir, scenesDir)."""
    document = await _json_body(request, "project document")
    result = store.put_project(project, document)
    _invalidate(request, result["name"])
    return result


@router.delete("/projects/{project}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project: str, request: Request, store: Store) -> Response:
    """Remove the project directory and everything in it."""
    name = store.delete_project(project)
    _invalidate(request, name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project}/models/{model:path}")
def get_model(project: str, model: str, store: Store) -> Response:
    """Plan 3.7: one model document, byte for byte as stored."""
    return Response(content=store.get_model(project, model), media_type="application/json")


@router.put("/projects/{project}/models/{model:path}")
async def put_model(project: str, model: str, request: Request, store: Store) -> dict[str, Any]:
    """Plan 3.7: validate against ``model.schema.json`` and store the document."""
    document = await _json_body(request, "model document")
    return store.put_model(project, model, document)


@router.delete("/projects/{project}/models/{model:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(project: str, model: str, store: Store) -> Response:
    """Delete the model file and its entry in the project's tab list."""
    store.delete_model(project, model)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project}/library/{block:path}")
def get_library(project: str, block: str, store: Store) -> PlainTextResponse:
    """Plan 3.7: one project-library source, as text."""
    return PlainTextResponse(store.get_library(project, block))


@router.put("/projects/{project}/library/{block:path}")
async def put_library(
    project: str, block: str, request: Request, store: Store
) -> dict[str, str]:
    """Plan 3.7: write one project-library source and drop the catalog cache."""
    source = await _library_source(request)
    result = store.put_library(project, block, source)
    _invalidate(request, result["project"])
    return result


@router.delete(
    "/projects/{project}/library/{block:path}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_library(project: str, block: str, request: Request, store: Store) -> Response:
    """Delete one project-library source and drop the catalog cache."""
    name = store.delete_library(project, block)
    _invalidate(request, name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
