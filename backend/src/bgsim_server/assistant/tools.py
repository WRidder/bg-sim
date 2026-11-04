"""The assistant's tool registry: ONE definition per tool. Every runner (the MCP relay of
``claude-cli``, the loop of ``openai-compatible``) exposes exactly ``TOOLS``.

The safety rule is capability by construction (plan/ASSISTANT_PLAN.md):

* an edit tool changes the session's draft and nothing else; only Apply writes the project;
* the edit tools have no ``project`` argument, so every other project and every example is
  read-only: the read tools take ``project``, and ``create_model`` copies into the draft;
* there is no file, shell or network tool. Models are parsed, never evaluated (spec section 1),
  and so are code cells: ``run_code`` goes through the language's interpreter in the worker.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
from fastapi import HTTPException
from pydantic import ValidationError

from .. import data as data_files
from .. import debug, docs, proxy, runs
from ..contracts import Breakpoint, DebugStartOptions, Model, ParameterOverride, ParameterStep
from ..projects import ProjectStore, _block_name, _detail_message, _model_name
from ..proxy import WorkerRpcFailure
from ..worker import WorkerError
from . import analysis, modelops, reference
from .modelops import ToolError

MAX_TEXT = 200_000
MAX_SWEEP = 16
MAX_SAMPLES = 400
TERMINAL = ("done", "failed", "cancelled")
EXAMPLE_PREFIX = "example:"

Handler = Callable[[Any, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    schema: dict[str, Any]
    handler: Handler
    edits: bool = False
    #: Still allowed after ask_user, before the user has answered.
    while_asking: bool = False
    #: Works in a chat without a project (the home screen). Edit tools need one.
    needs_project: bool = False

    def mcp(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.schema}

    def openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name, "description": self.description, "parameters": self.schema,
            },
        }


TOOLS: dict[str, ToolDef] = {}


def tool(
    description: str,
    properties: dict[str, Any] | None = None,
    required: tuple[str, ...] = (),
    *,
    edits: bool = False,
    while_asking: bool = False,
    needs_project: bool | None = None,
) -> Callable[[Handler], Handler]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties or {},
        "required": list(required),
    }

    def register(fn: Handler) -> Handler:
        needs = edits if needs_project is None else needs_project
        TOOLS[fn.__name__] = ToolDef(fn.__name__, description, schema, fn, edits, while_asking, needs)
        return fn

    return register


# ---------------------------------------------------------------------------- schema pieces

STR = {"type": "string"}
NUM = {"type": "number"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}
STRS = {"type": "array", "items": STR}
VALUE = {"type": ["string", "number", "boolean"]}
VALUES = {"type": "object", "additionalProperties": VALUE}
PROJECT = {
    "type": "string",
    "description": "Read from another project (read-only), or `example:<name>` for a shipped "
    "example. Omit for the project you are working on, which includes your draft.",
}
MODEL = {"type": "string", "description": "Model name; omit for the model open in the editor."}
NODE = {"type": "string", "description": "Node name; inside a subsystem `Drive/Motor`."}
PARENT = {"type": "string", "description": "The subsystem to work in, like `Drive`; omit for the top level."}
POINT = {
    "type": "object",
    "additionalProperties": False,
    "required": ["x", "y"],
    "properties": {"x": NUM, "y": NUM},
}
OVERRIDES = {
    "type": "array",
    "description": "Values for this run only; the model is not changed.",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["target", "value"],
        "properties": {
            "target": {"type": "string", "description": "`Motor/R`, or `global:Kp` for a global."},
            "value": NUM,
        },
    },
}
SCHEDULE = {
    "type": "array",
    "description": "Block parameter changes during the run (not for globals).",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["t", "target", "value"],
        "properties": {"t": NUM, "target": STR, "value": NUM},
    },
}
SIGNALS = {"type": "array", "minItems": 1, "items": STR, "description": "Signal ids, like `Load/w`."}


# ---------------------------------------------------------------------------- helpers


def _error_text(exc: HTTPException) -> str:
    return _detail_message(exc.detail)


def _model_name_of(s: Any, args: dict[str, Any]) -> str:
    name = args.get("model") or s.model
    if not name:
        raise ToolError("name a model: none is open in the editor", models=_model_names(s, args))
    return _model_name(name)


def _model_names(s: Any, args: dict[str, Any]) -> list[str]:
    return [] if s.project is None and not args.get("project") else s.draft.listing()["models"]


def _source(s: Any, project: str | None) -> tuple[ProjectStore, str, bool]:
    """``(store, project, is the working project)`` for a read tool's ``project`` argument."""
    if project is None and s.project is None:
        raise ToolError("no project is open: name one with `project`, see list_projects")
    if project is None or project == s.project:
        return s.ctx.store, s.project, True
    if project.startswith(EXAMPLE_PREFIX):
        return s.ctx.examples, project[len(EXAMPLE_PREFIX):], False
    return s.ctx.store, project, False


def _read_model(s: Any, name: str, project: str | None) -> dict[str, Any]:
    store, source, current = _source(s, project)
    if current:
        document = s.draft.model(name)
        if document is None:
            raise ToolError(f"no model {name!r}", models=s.draft.listing()["models"])
        return document
    return json.loads(store.get_model(source, name))


def _working(s: Any, name: str) -> dict[str, Any]:
    """A copy to edit: a refused edit leaves the draft as it was."""
    return copy.deepcopy(_read_model(s, name, None))


def _project_dir(s: Any) -> str:
    return str(s.ctx.store._require_project(s.project).resolve())


def _for_worker(s: Any, document: dict[str, Any]) -> Model:
    """The draft as the worker takes it: draft library blocks travel inline."""
    try:
        return Model.model_validate(modelops.inline_blocks(document, s.draft.library))
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first.get("loc", ()))
        raise ToolError(f"the model document is invalid at {where}: {first.get('msg')}") from None


async def _catalog(s: Any, project: str | None = None) -> dict[str, dict[str, Any]]:
    """ref -> catalog entry, indexed once per cached catalog."""
    store, source, current = _source(s, project)
    name = s.project if current else (source if store is s.ctx.store else None)
    catalog = await proxy.catalog(s.ctx.shim, project=name)
    held = s.catalogs.get(name)
    if held is None or held[0] is not catalog:
        held = (catalog, {block["ref"]: block for block in catalog["blocks"]})
        s.catalogs[name] = held
    return held[1]


def _brief(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref": block["ref"],
        "group": block["group"],
        "description": block["description"].split("\n")[0][:200],
        "ports": [f"{p['name']}:{p['domain']}" for p in block["ports"]],
        "inputs": [p["name"] for p in block["inputs"]],
        "outputs": [p["name"] for p in block["outputs"]],
    }


async def _check_source(s: Any, source: str, ref: str | None = None) -> dict[str, Any]:
    return await proxy.check_block(proxy.BlockCheckBody(source=source, ref=ref), s.ctx.shim)


async def _interface(s: Any, node: dict[str, Any]) -> dict[str, Any] | None:
    """The declarations of a node's block: the draft, the catalog, or the inline source."""
    block = node["block"]
    if "inline" in block:
        return (await _check_source(s, block["inline"]["source"])).get("interface")
    ref = block.get("ref")
    if ref is None:
        return None
    if ref.startswith("project:"):
        name = ref[len("project:"):]
        if name in s.draft.library:
            source = s.draft.library[name]
            return None if source is None else (await _check_source(s, source, ref)).get("interface")
    return (await _catalog(s)).get(ref)


async def _interfaces(s: Any, document: dict[str, Any], *endpoints: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for endpoint in endpoints:
        _, node, _ = modelops.locate(document, modelops.split_endpoint(endpoint)[0])
        found = await _interface(s, node)
        if found is not None:
            out[node["id"]] = found
    return out


def _check_names(
    what: str, given: dict[str, Any] | None, known: list[dict[str, Any]] | None, node: str
) -> None:
    if not given or known is None:
        return
    names = {entry["name"] for entry in known}
    wrong = sorted(set(given) - names)
    if wrong:
        raise ToolError(f"{node} has no {what} {wrong}; it has {sorted(names)}")


def _strings(values: dict[str, Any] | None) -> dict[str, str]:
    return {key: str(value).lower() if isinstance(value, bool) else str(value)
            for key, value in (values or {}).items()}


def _trim_diagnostics(items: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    keep = ("code", "severity", "message", "hint", "path", "block", "scope", "source")
    ranked = sorted(items, key=lambda d: {"error": 0, "warning": 1}.get(d.get("severity"), 2))
    return [{k: d[k] for k in keep if d.get(k) is not None} for d in ranked[:limit]]


async def check_document(s: Any, name: str) -> dict[str, Any]:
    """``model.check`` of one model; the session remembers the verdict for the proposal."""
    document = s.draft.model(name)
    if document is None:
        raise ToolError(f"no model {name!r}")
    model = _for_worker(s, document)
    result = await proxy._call_worker(
        s.ctx.shim, "model.check",
        {"model": runs._model_document(model), "projectDir": _project_dir(s)},
    )
    diagnostics = result.get("diagnostics") or []
    s.record_check(name, document, diagnostics)
    return {
        "errors": sum(1 for d in diagnostics if d.get("severity") == "error"),
        "warnings": sum(1 for d in diagnostics if d.get("severity") == "warning"),
        "diagnostics": _trim_diagnostics(diagnostics),
        "stats": result.get("stats"),
    }


# ---------------------------------------------------------------------------- reading: projects


@tool("List every project on this machine and the shipped examples. All of them can be read "
      "with the `project` argument of the read tools (examples as `example:<name>`), and copied "
      "into your draft with create_model; only the current project can be edited.")
async def list_projects(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    projects = [
        {"name": p["name"], "models": p["models"]}
        for p in s.ctx.store.list_projects()
    ]
    return {
        "current": s.project,
        "projects": projects,
        "examples": [
            {"project": f"{EXAMPLE_PREFIX}{name}", "title": g.get("title"), "about": g.get("description")}
            for name, g in s.ctx.gallery().items()
        ],
    }


@tool("Create a new empty project, or a copy of an example, and work in it from here on. Only on "
      "the home screen, where no project is open. It is written at once (it overwrites nothing); "
      "everything after it is a draft to Apply as usual.",
      {"name": STR, "example": {"type": "string", "description": "Example name, without `example:`."}},
      ("name",), needs_project=False)
async def create_project(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    if s.project is not None:
        raise ToolError(f"you are working in project {s.project!r}; a new one starts on the home screen")
    made = s.ctx.store.create_project(a["name"], a.get("example"))
    s.bind_project(made["name"])
    return {"created": made["name"], "models": s.draft.listing()["models"]}


@tool("List the models and library blocks of a project (with your draft's changes for the "
      "current one), and which model is open.", {"project": PROJECT})
async def list_models(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    store, source, current = _source(s, a.get("project"))
    if current:
        return {**s.draft.listing(), "open": s.model, "project": s.project,
                "changedInDraft": [f["name"] for f in s.draft.files()]}
    opened = store.open_project(source)
    return {
        "project": source, "readOnly": True,
        "models": [m["name"] for m in opened["models"]],
        "library": [b["name"] for b in opened["library"]],
    }


@tool("Read a model: its nodes, parameters and connections by name, one diagram level at a time, "
      "with settings, globals and plots at the top level. `raw` returns the whole JSON document.",
      {"model": MODEL, "subsystem": PARENT, "raw": BOOL, "project": PROJECT})
async def get_model(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    document = _read_model(s, _model_name_of(s, a), a.get("project"))
    if a.get("raw"):
        text = json.dumps(document)
        if len(text) > MAX_TEXT:
            raise ToolError(f"the document is {len(text)} characters: read it level by level")
        return {"document": document}
    return modelops.describe_model(document, modelops.split_path(a.get("subsystem")))


@tool("Find library blocks by what they do. Search before you assume a block exists. Blocks of "
      "the current project are included.",
      {"query": STR, "group": STR, "project": PROJECT, "limit": INT}, ("query",))
async def search_blocks(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    catalog = await _catalog(s, a.get("project"))
    words = a["query"].lower().split()
    scored = []
    for block in catalog.values():
        if a.get("group") and a["group"].lower() not in block["group"].lower():
            continue
        name = block["ref"].lower()
        text = f"{block['description']} {block['group']}".lower()
        score = sum((5 if w in name else 0) + (1 if w in text else 0) for w in words)
        if score:
            scored.append((score, block))
    scored.sort(key=lambda entry: (-entry[0], entry[1]["ref"]))
    return {
        "blocks": [_brief(b) for _, b in scored[: a.get("limit", 20)]],
        "groups": sorted({b["group"] for b in catalog.values()}),
    }


@tool("The exact interface of a block: ports, inputs, outputs, parameters with units and limits, "
      "constants, variables. Never guess a port or parameter name.",
      {"ref": {"type": "string", "description": "Like `stdlib:bondgraph/R` or `project:Tyre`."},
       "project": PROJECT}, ("ref",))
async def describe_block(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    ref = a["ref"]
    _, _, current = _source(s, a.get("project"))
    if current and ref.startswith("project:") and ref[len("project:"):] in s.draft.library:
        source = s.draft.block(ref[len("project:"):])
        if source is None:
            raise ToolError(f"{ref} is deleted in the draft")
        checked = await _check_source(s, source, ref)
        return {"ref": ref, "draft": True, **checked}
    block = (await _catalog(s, a.get("project"))).get(ref)
    if block is None:
        raise ToolError(f"no block {ref!r}; use search_blocks")
    return {key: value for key, value in block.items() if key not in ("source", "icon", "path")}


@tool("The source of a block, to learn from it or to copy and adapt it into a project block.",
      {"ref": STR, "project": PROJECT}, ("ref",))
async def get_block_source(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    ref = a["ref"]
    store, source_project, current = _source(s, a.get("project"))
    if ref.startswith("project:"):
        name = ref[len("project:"):]
        if current:
            source = s.draft.block(name)
            if source is None:
                raise ToolError(f"no block {ref!r}", library=s.draft.listing()["library"])
            return {"ref": ref, "source": source}
        return {"ref": ref, "source": store.get_library(source_project, name)}
    block = (await _catalog(s)).get(ref)
    if block is None:
        raise ToolError(f"no block {ref!r}; use search_blocks")
    return {"ref": ref, "source": block["source"]}


@tool("The docs of a project: the page tree of a model's docs and of the project docs, for any "
      "project (read-only) or example, and for the current one with your draft pages.",
      {"model": STR, "project": PROJECT})
async def list_docs(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    store, source, current = _source(s, a.get("project"))

    def tree(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"id": p["id"], "title": p["title"],
                 **({"children": tree(p["children"])} if p["children"] else {})} for p in pages]

    model = a.get("model")
    if model is None:
        index = docs.get_docs_index(source, store)
        result: dict[str, Any] = {
            "project": source,
            "projectDocs": tree(index["project"]["pages"]),
            "models": {entry["name"]: tree(entry["docs"]["pages"]) for entry in index["models"]},
        }
    else:
        result = {"project": source, "model": model,
                  "pages": tree(docs._get_docs(store, source, _model_name(model))["pages"])}
    if current and s.draft.pages:
        result["draftPages"] = [f"{o or '@project'}/{p}" for o, p in s.draft.pages]
    return result


@tool("Read one docs page. With `model` a page of that model's docs, without it a page of the "
      "project docs. Works for any project (read-only) or example.",
      {"page": STR, "model": STR, "project": PROJECT}, ("page",))
async def read_doc(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    store, source, current = _source(s, a.get("project"))
    model = a.get("model")
    if current:
        text = s.draft.page(model, a["page"])
        if text is not None:
            return {"page": a["page"], "draft": True, "text": text}
    text = docs.read_page_text(store, source, _model_name(model) if model else None, a["page"])
    return {"page": a["page"], "text": text[:MAX_TEXT]}


@tool("List the data files (CSV tables, reduced flexible bodies) of a project.", {"project": PROJECT})
async def list_data(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    store, source, _ = _source(s, a.get("project"))
    return {"files": data_files.list_data(source, store, "all")}


@tool("The header and first rows of a CSV data file.",
      {"file": STR, "rows": INT, "project": PROJECT}, ("file",))
async def preview_data(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    store, source, _ = _source(s, a.get("project"))
    return data_files.preview_data(source, a["file"], store, min(a.get("rows", 10), 50))


@tool("Search the language spec, the design notes and the user manual. Returns section ids for "
      "read_reference. Use it for syntax, scopes, units, events, bond-graph semantics, diagnostics.",
      {"query": STR}, ("query",))
async def search_reference(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    return {"sections": reference.search(s.ctx.settings.repo_root, a["query"])}


@tool("Read one section of the reference by id, from search_reference.", {"section": STR}, ("section",))
async def read_reference(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    found = reference.read(s.ctx.settings.repo_root, a["section"])
    if found is None:
        raise ToolError(f"no section {a['section']!r}; use search_reference")
    return found


# ---------------------------------------------------------------------------- editing: models


def _copy_block_refs(s: Any, document: dict[str, Any], store: ProjectStore, source: str) -> list[str]:
    copied = []
    for _, diagram in modelops.walk_diagrams(document):
        for node in diagram["nodes"]:
            ref = modelops.block_ref(node) or ""
            if ref.startswith("project:"):
                name = ref[len("project:"):]
                if s.draft.block(name) is None:
                    s.draft.put_block(name, store.get_library(source, name))
                    copied.append(name)
    return copied


@tool("Create a model in the draft: empty, or a copy of a model of this project, another project "
      "or an example (with the project blocks it uses).",
      {"name": STR, "from_model": STR, "from_project": PROJECT}, ("name",), edits=True)
async def create_model(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name(a["name"])
    if s.draft.model(name) is not None:
        raise ToolError(f"model {name!r} already exists")
    copied: list[str] = []
    if a.get("from_model"):
        store, source, current = _source(s, a.get("from_project"))
        document = copy.deepcopy(_read_model(s, _model_name(a["from_model"]), a.get("from_project")))
        document["name"] = name
        if not current:
            copied = _copy_block_refs(s, document, store, source)
    else:
        document = modelops.empty_model(name)
    s.draft.put_model(name, document)
    return {"created": name, "copiedBlocks": copied}


@tool("Delete a model in the draft. The model open in the editor cannot be deleted.",
      {"model": STR}, ("model",), edits=True)
async def delete_model(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name(a["model"])
    if name == s.model:
        raise ToolError("that model is open in the editor; ask the user to leave it first")
    _read_model(s, name, None)
    s.draft.put_model(name, None)
    return {"deleted": name}


@tool("Add a block, junction or empty subsystem to a diagram. Give exactly one of `ref`, "
      "`junction`, `source` (an inline block) or `subsystem: true`. Parameter values are constant "
      "expressions and may name globals. In an existing diagram give `near` (a node) and `side`, "
      "or run auto_layout after connecting: it places what you added and nothing else.",
      {"model": MODEL, "parent": PARENT, "name": STR, "ref": STR,
       "junction": {"enum": ["0", "1"]}, "source": STR, "subsystem": BOOL,
       "params": VALUES, "constants": {"type": "object"}, "starts": VALUES, "position": POINT,
       "near": STR, "side": {"enum": ["right", "left", "above", "below"]}},
      ("name",), edits=True)
async def add_block(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    document = _working(s, name)
    diagram = modelops.diagram_at(document, modelops.split_path(a.get("parent")))
    kinds = [k for k in ("ref", "junction", "source", "subsystem") if a.get(k)]
    if len(kinds) != 1:
        raise ToolError("give exactly one of ref, junction, source or subsystem")
    params = _strings(a.get("params"))
    interface = None
    if a.get("junction"):
        block: dict[str, Any] = {"junction": a["junction"]}
    elif a.get("subsystem"):
        block = modelops.empty_subsystem()
    elif a.get("source"):
        checked = await _check_source(s, a["source"])
        interface = checked.get("interface")
        errors = [d for d in checked["diagnostics"] if d.get("severity") == "error"]
        if errors:
            raise ToolError("the block source has errors", diagnostics=_trim_diagnostics(errors))
        block = {"inline": {"source": a["source"]}}
    else:
        block = {"ref": a["ref"]}
        interface = await _interface(s, {"block": block})
        if interface is None:
            raise ToolError(f"no block {a['ref']!r}; use search_blocks")
    if interface is not None:
        _check_names("parameter", params, interface["parameters"], a["name"])
        _check_names("constant", a.get("constants"), interface["constants"], a["name"])
        names = [*interface["variables"], *interface["outputs"]]
        _check_names("start value", a.get("starts"), names, a["name"])
        params = {**{p["name"]: p["default"] for p in interface["parameters"]}, **params}
    position = a.get("position")
    if a.get("near"):
        anchor = next((n for n in diagram["nodes"] if n["name"] == a["near"]), None)
        if anchor is None:
            raise ToolError(f"no node {a['near']!r} at this level", nodes=[n["name"] for n in diagram["nodes"]])
        position = modelops.place_near(diagram, anchor, a.get("side", "right"))
    node = modelops.add_node(
        document, diagram, a["name"], block, params=params, constants=a.get("constants"),
        starts=_strings(a.get("starts")), position=position,
    )
    s.draft.put_model(name, document)
    return {"added": a["name"], "ports": modelops.ports_of(node, interface)}


@tool("Change a block: rename it, set parameters, constants or start values (null removes an "
      "override), move or rotate it, or swap its `ref` or inline `source`.",
      {"model": MODEL, "node": NODE, "rename": STR, "params": {"type": "object"},
       "constants": {"type": "object"}, "starts": {"type": "object"}, "ref": STR, "source": STR,
       "position": POINT, "rotation": NUM, "flipX": BOOL},
      ("node",), edits=True)
async def update_block(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    document = _working(s, name)
    diagram, node, _ = modelops.locate(document, a["node"])
    if a.get("ref"):
        node["block"] = {"ref": a["ref"]}
    elif a.get("source"):
        node["block"] = {"inline": {"source": a["source"]}}
    interface = await _interface(s, node)
    if a.get("ref") and interface is None:
        raise ToolError(f"no block {a['ref']!r}; use search_blocks")
    if interface is not None:
        _check_names("parameter", a.get("params"), interface["parameters"], node["name"])
        _check_names("constant", a.get("constants"), interface["constants"], node["name"])
    for key in ("params", "constants", "starts"):
        for field, value in (a.get(key) or {}).items():
            if value is None:
                node.setdefault(key, {}).pop(field, None)
            else:
                node.setdefault(key, {})[field] = value if key == "constants" else _strings({field: value})[field]
    if a.get("rename"):
        if not modelops.NODE_NAME.fullmatch(a["rename"]):
            raise ToolError(f"{a['rename']!r} is not a node name")
        if any(n["name"] == a["rename"] for n in diagram["nodes"]):
            raise ToolError(f"this diagram already has a node {a['rename']!r}")
        node["name"] = a["rename"]
    for key in ("position", "rotation", "flipX"):
        if key in a:
            node[key] = a[key]
    s.draft.put_model(name, document)
    return {"updated": node["name"], "params": node.get("params")}


@tool("Remove a block with its connections.", {"model": MODEL, "node": NODE}, ("node",), edits=True)
async def remove_block(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    document = _working(s, name)
    diagram, node, _ = modelops.locate(document, a["node"])
    gone = modelops.remove_node(diagram, node)
    s.draft.put_model(name, document)
    return {"removed": a["node"], "connectionsRemoved": len(gone)}


@tool("Connect two ports of one diagram. Endpoints are `Node.port`, a bare junction name, or "
      "`Drive/Motor.p` inside a subsystem. Kind (bond, wire, signal) follows from the ports, and a "
      "signal is put output to input. For a bond, `from` -> `to` is the power direction (half arrow "
      "at `to`).",
      {"model": MODEL, "from": STR, "to": STR}, ("from", "to"), edits=True)
async def connect(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    document = _working(s, name)
    interfaces = await _interfaces(s, document, a["from"], a["to"])
    connection = modelops.connect(document, a["from"], a["to"], interfaces)
    s.draft.put_model(name, document)
    return {"connected": f"{a['from']} -> {a['to']}", "kind": connection["kind"]}


@tool("Remove a connection.", {"model": MODEL, "from": STR, "to": STR}, ("from", "to"), edits=True)
async def disconnect(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    document = _working(s, name)
    modelops.disconnect(document, a["from"], a["to"])
    s.draft.put_model(name, document)
    return {"disconnected": f"{a['from']} -> {a['to']}"}


@tool("Expose a port of a node inside a subsystem on the subsystem's outside face, under `name`. "
      "Outside it then connects as `Subsystem.name`. For a junction give the `domain`.",
      {"model": MODEL, "inner": {"type": "string", "description": "Like `Drive/Motor.p`, or `Drive/J1`."},
       "name": STR, "domain": STR}, ("inner", "name"), edits=True)
async def expose_port(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    document = _working(s, name)
    interfaces = await _interfaces(s, document, a["inner"])
    port = modelops.expose_port(document, a["inner"], a["name"], interfaces, a.get("domain"))
    s.draft.put_model(name, document)
    return {"exposed": a["name"], "port": port}


@tool("Lay out a diagram. In a diagram that has a saved layout it places ONLY the blocks you "
      "added, next to what they connect to, in the diagram's own direction and spacing; everything "
      "else stays where the user put it. In a new diagram it makes a full layout: signal flow left "
      "to right, feedback back through, bond graph elements above and below their junctions. "
      "`whole: true` redoes an existing layout and needs the user to have asked for it.",
      {"model": MODEL, "parent": PARENT, "whole": BOOL, "nodes": STRS}, edits=True)
async def auto_layout(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    document = _working(s, name)
    path = modelops.split_path(a.get("parent"))
    diagram = modelops.diagram_at(document, path)
    saved = _saved_names(s, name, path)
    if a.get("nodes"):
        placed = modelops.place_new(diagram, set(a["nodes"]))
    elif saved and not a.get("whole"):
        placed = modelops.place_new(diagram, {n["name"] for n in diagram["nodes"]} - saved)
    else:
        modelops.auto_layout(diagram)
        placed = [n["name"] for n in diagram["nodes"]]
    s.draft.put_model(name, document)
    return {"placed": placed, "kept": len(diagram["nodes"]) - len(placed),
            "overlapping": modelops.overlaps(diagram)}


def _saved_names(s: Any, name: str, path: list[str]) -> set[str]:
    """The nodes of this level in the saved model: their places are the user's."""
    base = s.draft.base_model(name)
    if base is None:
        return set()
    try:
        return {n["name"] for n in modelops.diagram_at(base, path)["nodes"]}
    except ToolError:
        return set()


@tool("Add or change global parameters (named constant expressions a user tunes) and remove "
      "others. Use globals for masses, gains and set points; node parameters may name them.",
      {"model": MODEL,
       "set": {"type": "array", "items": {
           "type": "object", "additionalProperties": False, "required": ["name", "value"],
           "properties": {"name": STR, "value": VALUE, "unit": STR, "description": STR}}},
       "remove": STRS}, edits=True)
async def set_globals(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    document = _working(s, name)
    table = document.get("parameters") or []
    table = [p for p in table if p["name"] not in set(a.get("remove") or [])]
    for entry in a.get("set") or []:
        update = {**entry, "value": str(entry["value"])}
        found = next((p for p in table if p["name"] == entry["name"]), None)
        if found is None:
            table.append(update)
        else:
            found.update(update)
    document["parameters"] = table
    s.draft.put_model(name, document)
    return {"globals": table}


@tool("Change the simulation settings of a model: t_start, t_end, solver, reltol, abstol, "
      "max_step, event_limit, and `output` ({mode: points, points: N} or {mode: interval, ...}).",
      {"model": MODEL, "t_start": NUM, "t_end": NUM, "solver": STR, "reltol": NUM, "abstol": NUM,
       "max_step": {"type": ["number", "null"]}, "event_limit": INT, "output": {"type": "object"}},
      edits=True)
async def set_settings(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    document = _working(s, name)
    document["settings"].update({k: v for k, v in a.items() if k != "model"})
    s.draft.put_model(name, document)
    return {"settings": document["settings"]}


@tool("Set one part of a model that has no tool of its own, as JSON following "
      "contracts/schemas/model.schema.json: `plots` (saved plots), `dashboard` (cards), `scene`, "
      "`bindings`. The result is validated.",
      {"model": MODEL, "field": {"enum": ["plots", "dashboard", "scene", "bindings"]}, "value": {}},
      ("field", "value"), edits=True)
async def set_model_field(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    document = _working(s, name)
    document[a["field"]] = a["value"]
    _validated(s, document)
    s.draft.put_model(name, document)
    return {"set": a["field"]}


def _validated(s: Any, document: dict[str, Any]) -> None:
    try:
        s.ctx.store._check_schema("model", document, "the model document")
    except HTTPException as exc:
        raise ToolError(_error_text(exc)) from None


@tool("Replace a whole model with a JSON document (contracts/schemas/model.schema.json); for "
      "bulk generation. The other tools are safer: they check names, ports and ids for you.",
      {"model": MODEL, "document": {"type": "object"}}, ("document",), edits=True)
async def replace_model(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    document = {**a["document"], "name": name}
    _validated(s, document)
    problems = modelops.lint(document)
    if problems:
        raise ToolError("the document is inconsistent", problems=problems[:20])
    s.draft.put_model(name, document)
    return {"replaced": name}


@tool("Add a sticky note (Markdown, no images or tables) to a diagram.",
      {"model": MODEL, "parent": PARENT, "text": STR, "x": NUM, "y": NUM,
       "color": {"enum": ["yellow", "blue", "green", "pink", "grey"]}},
      ("text",), edits=True)
async def add_note(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    document = _working(s, name)
    diagram = modelops.diagram_at(document, modelops.split_path(a.get("parent")))
    note = {
        "id": modelops._next_id(document, "note", "annotations"),
        "kind": "text", "text": a["text"],
        "x": a.get("x", 80), "y": a.get("y", 20), "w": 240, "h": 120,
    }
    if a.get("color") not in (None, "yellow"):
        note["color"] = a["color"]
    diagram.setdefault("annotations", []).append(note)
    s.draft.put_model(name, document)
    return {"added": note["id"]}


# ---------------------------------------------------------------------------- editing: blocks, docs


@tool("Write a block of the project library in the draft (`project:<name>`). Only for what no "
      "combination of standard elements can express. Returns its diagnostics and interface.",
      {"name": STR, "source": STR}, ("name", "source"), edits=True)
async def write_library_block(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _block_name(a["name"])
    checked = await _check_source(s, a["source"], f"project:{name}")
    s.draft.put_block(name, a["source"])
    return {"ref": f"project:{name}", **checked}


@tool("Delete a project library block in the draft.", {"name": STR}, ("name",), edits=True)
async def delete_library_block(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _block_name(a["name"])
    if s.draft.block(name) is None:
        raise ToolError(f"no block {name!r}", library=s.draft.listing()["library"])
    s.draft.put_block(name, None)
    return {"deleted": name}


@tool("Write a docs page in the draft: of `model`, or of the project docs when `model` is absent. "
      "A new id adds the page to the tree, under `parent` if given. Markdown, with $math$ and "
      "`block:` / `signal:` links.",
      {"page": STR, "title": STR, "text": STR, "model": STR, "parent": STR},
      ("page", "title", "text"), edits=True)
async def write_doc(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    model = a.get("model")
    if model is not None:
        _read_model(s, _model_name(model), None)
    s.draft.put_page(model, docs._page_id(a["page"]), a["title"], a["text"], a.get("parent"))
    return {"written": a["page"]}


# ---------------------------------------------------------------------------- checking


@tool("Check one block's source without adding it: diagnostics and the interface.",
      {"source": STR}, ("source",))
async def check_block(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    return await _check_source(s, a["source"])


@tool("Check a model through the real compiler: units, domains, causality, structure. Returns "
      "the diagnostics with hints. Run it after every batch of edits, before simulating.",
      {"model": MODEL}, needs_project=True)
async def check_model(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    return await check_document(s, _model_name_of(s, a))


@tool("Why a signal has its value: the equation that computes it and what it depends on. Needs "
      "no run.", {"model": MODEL, "signal": STR}, ("signal",), needs_project=True)
async def explain_signal(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    document = _read_model(s, _model_name_of(s, a), None)
    return await proxy._call_worker(
        s.ctx.shim, "model.explain",
        {
            "model": runs._model_document(_for_worker(s, document)),
            "projectDir": _project_dir(s),
            "signal": a["signal"],
        },
    )


@tool("Everything that is wrong right now, as the user's Problems panel would show it: the "
      "compiler's diagnostics of a model, syntax and check errors of every project library block "
      "and inline block, and the diagnostics of the model's latest run. Each has its code, block "
      "path, source line and column, and a hint.", {"model": MODEL}, needs_project=True)
async def get_diagnostics(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    result: dict[str, Any] = {"model": await check_document(s, name)}
    blocks: dict[str, Any] = {}
    for block in s.draft.listing()["library"]:
        source = s.draft.block(block)
        if source is None:
            continue
        found = (await _check_source(s, source, f"project:{block}"))["diagnostics"]
        if found:
            blocks[f"project:{block}"] = _trim_diagnostics(found)
    document = _read_model(s, name, None)
    for level, diagram in modelops.walk_diagrams(document):
        for node in diagram["nodes"]:
            if "inline" in node["block"]:
                found = (await _check_source(s, node["block"]["inline"]["source"]))["diagnostics"]
                if found:
                    blocks["/".join([*level, node["name"]])] = _trim_diagnostics(found)
    result["blocks"] = blocks
    latest = _latest_run_id(s, name)
    if latest is not None:
        summary = _run_summary(_manifest(s, latest))
        result["latestRun"] = {k: summary[k] for k in ("runId", "status", "diagnostics")}
    return result


@tool("The last lines of the worker's log, for a crash or an error that has no diagnostic.",
      {"lines": INT})
async def worker_log(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    path = s.ctx.settings.worker_log
    if path is None or not path.is_file():
        return {"lines": []}
    return {"lines": path.read_text(encoding="utf-8", errors="replace").splitlines()[-min(a.get("lines", 80), 400):]}


# ---------------------------------------------------------------------------- simulating


def _manifest(s: Any, run_id: str) -> dict[str, Any]:
    run_dir, state = runs._locate(s.ctx.shim, run_id)
    return state.manifest_document() if state is not None else runs._load_manifest(run_dir)


def _finite(values: Any) -> list[float | None]:
    return [float(v) if np.isfinite(v) else None for v in np.asarray(values, dtype=float)]


def _runs_of(store: ProjectStore, project: str, model: str | None) -> list[dict[str, Any]]:
    """The manifests of a project's runs, newest first; another model's runs are left out."""
    folder = store._require_project(project) / "runs"
    if not folder.is_dir():
        return []
    out = []
    for path in sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        manifest = path / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            document = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if model is None or document.get("model") == model:
            out.append(document)
    return out


def _latest_run_id(s: Any, model: str) -> str | None:
    """The newest finished run of a model: the user's or the assistant's."""
    return next(
        (d.get("id") for d in _runs_of(s.ctx.store, s.project, model) if d.get("status") == "done"),
        None,
    )


def _run_summary(document: dict[str, Any]) -> dict[str, Any]:
    signals = document.get("signals") or []
    return {
        "runId": document["id"],
        "model": document.get("model"),
        "status": document["status"],
        "stats": document.get("stats"),
        "diagnostics": _trim_diagnostics(document.get("diagnostics") or [], 15),
        "signalCount": len(signals),
        "timeRange": document.get("time"),
        "states": [x["id"] for x in signals if x.get("kind") == "state"][:30],
    }


async def _await_run(s: Any, run_id: str, wait_s: float) -> dict[str, Any]:
    loop = s.loop
    deadline = loop.time() + wait_s
    while True:
        document = _manifest(s, run_id)
        if document["status"] in TERMINAL:
            return _run_summary(document)
        if s.cancel_event.is_set():
            await runs.cancel_run(run_id, s.ctx.shim)
            return {"runId": run_id, "status": "cancelled"}
        if loop.time() >= deadline:
            return {
                **_run_summary(document),
                "note": "still running: poll with run_status, or stop it with stop_run",
            }
        await s.sleep(0.2)


async def _start_run(
    s: Any,
    name: str,
    a: dict[str, Any],
    overrides: list[dict[str, Any]] | None,
    debugging: DebugStartOptions | None = None,
) -> str:
    document = copy.deepcopy(_read_model(s, name, None))
    for key in ("t_start", "t_end", "solver", "max_step"):
        if key in a:
            document["settings"][key] = a[key]
    body = runs.RunCreateBody(
        model=_for_worker(s, document),
        parameterOverrides=[ParameterOverride.model_validate(o) for o in overrides] if overrides else None,
        parameterSchedule=[ParameterStep.model_validate(o) for o in a["schedule"]] if a.get("schedule") else None,
        debug=debugging,
    )
    run_id = await runs.launch_run(s.ctx.shim, s.project, body)
    s.runs.add(run_id)
    return run_id


def _announce_run(s: Any, run_id: str, name: str, debugging: bool = False) -> None:
    draft = name in s.draft.models or bool(s.draft.library)
    s.emit("simulation", runId=run_id, model=name, draft=draft, **({"debug": True} if debugging else {}))


@tool("Simulate a model as it stands in your draft (the saved model is not touched) and wait for "
      "the result. The user sees the run live in the Plots dock. `t_end` and the other settings "
      "here, `overrides` and `schedule`, apply to this run only.",
      {"model": MODEL, "t_start": NUM, "t_end": NUM, "solver": STR,
       "max_step": {"type": ["number", "null"]}, "overrides": OVERRIDES, "schedule": SCHEDULE,
       "wait_s": {"type": "number", "description": "How long to wait, default 300, at most 900."}}, needs_project=True)
async def run_simulation(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    run_id = await _start_run(s, name, a, a.get("overrides"))
    _announce_run(s, run_id, name)
    return await _await_run(s, run_id, min(a.get("wait_s", 300), 900))


@tool("A run's result: status, stats, diagnostics, the settings it ran with and its overrides. "
      "Without `run_id`, the latest finished run of the model.",
      {"run_id": STR, "model": MODEL})
async def run_status(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    run_id = a.get("run_id") or _latest_run_id(s, _model_name_of(s, a))
    if run_id is None:
        raise ToolError("this model has no finished run")
    document = _manifest(s, run_id)
    return {
        **_run_summary(document),
        **{k: document.get(k) for k in ("settings", "parameterOverrides", "parameterSchedule", "parentRun")},
    }


@tool("Stop a running simulation.", {"run_id": STR}, ("run_id",))
async def stop_run(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    return await runs.cancel_run(a["run_id"], s.ctx.shim)


@tool("The recent runs of a project, the user's and yours, newest first; `project` reads another "
      "project's runs. Their signals are read with the tools below, by run id.",
      {"model": STR, "project": PROJECT, "limit": INT})
async def list_runs(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    store, source, _ = _source(s, a.get("project"))
    found = _runs_of(store, source, a.get("model"))[: a.get("limit", 10)]
    return {"runs": [
        {
            "runId": d.get("id"), "model": d.get("model"), "status": d.get("status"),
            "created": d.get("created"), "overrides": d.get("parameterOverrides"),
        }
        for d in found
    ]}


@tool("The signals a run recorded, filtered by a piece of their id and by kind (state, port, "
      "power, input, output, observed, ...).",
      {"run_id": STR, "filter": STR, "kind": STR, "limit": INT}, ("run_id",))
async def list_signals(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    signals = _manifest(s, a["run_id"]).get("signals") or []
    needle = (a.get("filter") or "").lower()
    found = [
        {"id": x["id"], "unit": x.get("unit"), "kind": x.get("kind")}
        for x in signals
        if needle in x["id"].lower() and (not a.get("kind") or x.get("kind") == a["kind"])
    ]
    limit = a.get("limit", 200)
    return {"total": len(found), "signals": found[:limit], "truncated": len(found) > limit}


def _series(
    s: Any, run_id: str, ids: list[str], t0: float | None, t1: float | None
) -> tuple[np.ndarray, np.ndarray, dict[str, dict[str, Any]]]:
    run_dir, state = runs._locate(s.ctx.shim, run_id)
    document, signals = runs._manifest_and_signals(run_dir, state)
    lookup = {str(x["id"]): i for i, x in enumerate(signals)}
    missing = [i for i in ids if i not in lookup]
    if missing:
        raise ToolError(f"run {run_id} did not record {missing[:5]}; use list_signals")
    time, values = runs._read_series(run_dir, document, signals, [lookup[i] for i in ids], t0, t1)
    return time, values, {str(x["id"]): x for x in signals}


@tool("Exact numbers for signals of a run over a time window: initial, final, min, max and when, "
      "time-weighted mean and RMS, integral, and how many samples are NaN or Inf. Use these rather "
      "than reading values off a curve.",
      {"run_id": STR, "signals": SIGNALS, "t0": NUM, "t1": NUM}, ("run_id", "signals"))
async def signal_stats(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    time, values, info = _series(s, a["run_id"], a["signals"], a.get("t0"), a.get("t1"))
    return {
        "signals": {
            sid: {"unit": info[sid].get("unit"), **analysis.signal_stats(time, values[i])}
            for i, sid in enumerate(a["signals"])
        }
    }


@tool("Signal values at uniform times, to see the shape of a curve in numbers, or at the exact "
      "`times` you name.",
      {"run_id": STR, "signals": SIGNALS, "points": INT, "t0": NUM, "t1": NUM,
       "times": {"type": "array", "maxItems": MAX_SAMPLES, "items": NUM}},
      ("run_id", "signals"))
async def sample_signals(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    points = max(2, min(a.get("points", 40), MAX_SAMPLES))
    time, values, _ = _series(s, a["run_id"], a["signals"], a.get("t0"), a.get("t1"))
    if a.get("times"):
        grid = np.asarray(a["times"], dtype=float)
        rows = np.vstack([np.interp(grid, time, values[i]) for i in range(len(a["signals"]))])
    else:
        grid, rows = analysis.resample(time, values, points)
    return {
        "time": [float(f"{v:.6g}") for v in grid],
        "values": {
            sid: [None if not np.isfinite(v) else float(f"{v:.6g}") for v in rows[i]]
            for i, sid in enumerate(a["signals"])
        },
    }


@tool("Step-response figures of a signal: rise time, overshoot, settling time, steady-state "
      "error, measured from t0 towards `target` (default: its final value).",
      {"run_id": STR, "signal": STR, "target": NUM, "band": NUM, "t0": NUM, "t1": NUM},
      ("run_id", "signal"))
async def step_metrics(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    time, values, _ = _series(s, a["run_id"], [a["signal"]], a.get("t0"), a.get("t1"))
    return analysis.step_metrics(time, values[0], a.get("target"), a.get("band", 0.02))


@tool("Compare signals of two runs (also across models): RMS and largest difference, and when.",
      {"run_a": STR, "run_b": STR, "signals": SIGNALS, "signals_b": STRS},
      ("run_a", "run_b", "signals"))
async def compare_runs(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    other = a.get("signals_b") or a["signals"]
    if len(other) != len(a["signals"]):
        raise ToolError("signals_b must pair one to one with signals")
    time_a, values_a, _ = _series(s, a["run_a"], a["signals"], None, None)
    time_b, values_b, _ = _series(s, a["run_b"], other, None, None)
    return {
        "signals": {
            sid: analysis.compare(time_a, values_a[i], time_b, values_b[i])
            for i, sid in enumerate(a["signals"])
        }
    }


@tool("Simulate a model once per value of one parameter and tabulate the signals' figures. For "
      f"tuning and sensitivity; at most {MAX_SWEEP} values.",
      {"model": MODEL, "target": {"type": "string", "description": "`Motor/R` or `global:Kp`."},
       "values": {"type": "array", "minItems": 1, "items": NUM}, "signals": SIGNALS, "t_end": NUM,
       "overrides": OVERRIDES},
      ("target", "values", "signals"), needs_project=True)
async def parameter_sweep(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    if len(a["values"]) > MAX_SWEEP:
        raise ToolError(f"at most {MAX_SWEEP} values in one sweep")
    name = _model_name_of(s, a)
    table = []
    for value in a["values"]:
        if s.cancel_event.is_set():
            break
        overrides = [*(a.get("overrides") or []), {"target": a["target"], "value": value}]
        run_id = await _start_run(s, name, a, overrides)
        done = await _await_run(s, run_id, 300)
        row: dict[str, Any] = {"value": value, "runId": run_id, "status": done["status"]}
        if done["status"] == "done":
            time, values, _ = _series(s, run_id, a["signals"], None, None)
            row["signals"] = {
                sid: {
                    k: v for k, v in analysis.signal_stats(time, values[i]).items()
                    if k in ("final", "min", "max", "rms", "tMax")
                }
                for i, sid in enumerate(a["signals"])
            }
        else:
            row["diagnostics"] = done.get("diagnostics")
        table.append(row)
    return {"target": a["target"], "rows": table}


# ---------------------------------------------------------------------------- showing and asking


@tool("Show a plot of signals of a run in the chat. `x` makes it an XY plot.",
      {"title": STR, "run_id": STR, "signals": SIGNALS, "x": STR, "t0": NUM, "t1": NUM},
      ("title", "run_id", "signals"))
async def plot_signals(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    wanted = [*a["signals"], *([a["x"]] if a.get("x") else [])]
    _series(s, a["run_id"], wanted, 0.0, 0.0)
    figure = {
        "id": f"plot-{s.next_figure()}", "kind": "plot", "title": a["title"],
        "runId": a["run_id"], "signals": a["signals"],
        **{k: a[k] for k in ("x", "t0", "t1") if k in a},
    }
    s.emit("figure", figure=figure)
    return {"shown": figure["id"]}


@tool("Show one level of a model as a drawing in the chat: your draft, or a model of another "
      "project. Use it after building, so the user sees the structure.",
      {"model": MODEL, "subsystem": PARENT, "project": PROJECT, "title": STR})
async def show_diagram(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    document = _read_model(s, name, a.get("project"))
    path = modelops.split_path(a.get("subsystem"))
    title = a.get("title") or "/".join([name, *path])
    s.emit("figure", figure=modelops.diagram_figure(document, path, f"diagram-{s.next_figure()}", title))
    return {"shown": title}


QUESTION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "prompt", "kind"],
    "properties": {
        "id": STR,
        "prompt": {"type": "string", "description": "The question; Markdown with $math$."},
        "kind": {"enum": ["single", "multiple", "text"],
                 "description": "single: radio buttons. multiple: checkboxes. text: free text."},
        "options": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["value", "label"],
            "properties": {"value": STR, "label": STR, "description": STR}}},
        "allowOther": {"type": "boolean", "description": "Also offer a free-text answer."},
        "optional": BOOL,
    },
}


@tool("Ask the user: radio buttons (`single`), checkboxes (`multiple`) or a text field (`text`). "
      "Use it when a decision is the user's: what to model, assumptions that change the result, "
      "which of several designs. After this call END YOUR TURN at once, with no other tool and at "
      "most one short sentence; the answers arrive as the next user message.",
      {"title": STR, "questions": {"type": "array", "minItems": 1, "maxItems": 8, "items": QUESTION}},
      ("questions",), while_asking=True)
async def ask_user(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    seen = set()
    for question in a["questions"]:
        if question["id"] in seen:
            raise ToolError(f"question id {question['id']!r} is used twice")
        seen.add(question["id"])
        options = question.get("options") or []
        if question["kind"] != "text" and len(options) < 2:
            raise ToolError(f"question {question['id']!r} needs at least two options")
        if len({o["value"] for o in options}) != len(options):
            raise ToolError(f"question {question['id']!r} repeats an option value")
    question_set = {
        "id": f"q{s.next_figure()}",
        **({"title": a["title"]} if a.get("title") else {}),
        "questions": a["questions"],
    }
    s.pose_question(question_set)
    return {"status": "shown", "instruction": "End your turn now. The answers come as the next user message."}


CELL_SIGNAL = re.compile(r's"([^"]+)"')


@tool("Compute anything from simulation results: run a Julia code cell over a run and its model, "
      "and show tables and plots in the chat. Julia syntax on the block language's interpreter "
      "(never evaluated): assignments, `for`, `while`, `if`, your own functions (`f(x) = ...` or "
      "`function ... end`), tuples (`b, a = butter(2, 0.1)`), vectors, matrices, complex numbers, "
      "ranges, masks like `w[t .> 1]`, `x[end]`, `A[:, 1]`. `t` is the run's time, `s\"Load/w\"` a "
      "signal as a vector, `s\"Motor/R\"` a parameter, `Kp` a global. `*`, `/` on two vectors are "
      "elementwise, with a matrix they are matrix operations. "
      "Library: the language's math; length sum prod mean var std median percentile rms maximum "
      "minimum argmax argmin first last diff cumsum reverse sort any all count findfirst findall "
      "zeros ones linspace; trapz(y,x) cumtrapz(y,x) gradient(y,x) interp(q,xs,ys) peaks(y) "
      "crossings(y,level); fft ifft fftfreq(n,fs) samplerate(t) amplitude(y) ampfreq(t) hann hamming "
      "blackman convolve xcorr; movmean(y,n) detrend butter(order,wn) butterhigh(order,wn) "
      "filter(b,a,y) filtfilt(b,a,y); polyfit(x,y,n) polyval(p,x) (coefficients ascending); inv det "
      "rank trace eigvals svdvals pinv diag eye size hcat vcat transpose `A \\ b`; real imag conj "
      "angle abs2 isnan isfinite. "
      "Output, shown in the chat (capitalised too, and the title is optional): `plot(\"Title\", x, "
      "y1, y2)`, `scatter`, `bar`, `table(\"Title\", a, b)`, `image(\"Title\", M)` for a matrix as "
      "a heat map, `text(\"peak\", p, \"at\", t0)`; a bare top-level expression prints its value. "
      "No I/O or packages: what the library lacks, write as a function in the cell.",
      {"code": STR, "title": STR,
       "run_id": {"type": "string", "description": "Default: the model's latest finished run."},
       "model": MODEL, "t0": NUM, "t1": NUM}, ("code",), needs_project=True)
async def run_code(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    document = _read_model(s, name, None)
    run_id = a.get("run_id") or _latest_run_id(s, name)
    time: Any = None
    signals: dict[str, list[float | None]] = {}
    if run_id is not None:
        recorded = {str(x["id"]) for x in _manifest(s, run_id).get("signals") or []}
        wanted = sorted(set(CELL_SIGNAL.findall(a["code"])) & recorded)
        grid, values, _ = _series(s, run_id, wanted or [min(recorded)], a.get("t0"), a.get("t1"))
        time = _finite(grid)
        signals = {sid: _finite(values[i]) for i, sid in enumerate(wanted)}
    result = await proxy._call_worker(
        s.ctx.shim, "code.run",
        {
            "code": a["code"], "time": time, "signals": signals,
            "model": runs._model_document(_for_worker(s, document)),
            "projectDir": _project_dir(s),
        },
    )
    cell = f"cell-{s.next_figure()}"
    first_error = next((d["message"] for d in result["diagnostics"]), None)
    s.emit("code", id=cell, title=a.get("title") or "Julia", code=a["code"], runId=run_id,
           ok=result["ok"], output=result["output"], error=first_error)
    for figure in result["figures"]:
        s.emit("figure", figure={**figure, "id": f"{cell}-{s.next_figure()}"})
    return {
        "ok": result["ok"], "runId": run_id, "output": result["output"], "values": result["values"],
        "shown": [f"{f['kind']}: {f['title']}" for f in result["figures"]],
        "diagnostics": _trim_diagnostics(result["diagnostics"]),
    }


# ---------------------------------------------------------------------------- the debugger


BREAKPOINTS = {
    "type": "array",
    "items": {"type": "object"},
    "description": "Each is one of: {kind: 'line', line: {ref: 'project:Block', line: 12, path?: "
    "'Instance'}, condition?: 'k == 5', hitCount?: 3}, where `line` is a statement's line in the "
    "block's file, counted from 1 at the first line of get_block_source; {kind: 'watch', watch: {expr: "
    "'s\"Motor1/i\" > 5', context?: 'Instance'}, hitCount?: 3}; {kind: 'time', time: {t: 0.5}}; "
    "{kind: 'event', event: {path?: 'Instance'}}; {kind: 'exception', exception: {on: ['E901']}}. "
    "A watch sees continuous signals only: on a signal of @discrete code it never fires, so use a "
    "line breakpoint in that code with a `condition` over its locals.",
}
PAUSE_WAIT = {"type": "number", "description": "How long to wait for the pause, default 60, at most 600."}
_BREAKPOINT_DEFAULTS: dict[str, dict[str, Any]] = {
    "line": {"path": None}, "watch": {"context": None}, "event": {"path": None},
}


def _breakpoints(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The contract's breakpoints, with what a tool call may leave out filled in."""
    found = []
    for index, item in enumerate(items, 1):
        kind = str(item.get("kind"))
        entry = {"id": f"bp{index}", "enabled": True, **item}
        if kind in _BREAKPOINT_DEFAULTS:
            entry[kind] = {**_BREAKPOINT_DEFAULTS[kind], **(item.get(kind) or {})}
        found.append(debug._dump(Breakpoint.model_validate(entry)))
    return found


async def _debug_call(s: Any, method: str, params: dict[str, Any]) -> Any:
    try:
        return await debug._debug_call(s.ctx.shim, method, params)
    except debug.DebugConflict as exc:
        raise ToolError(exc.message, diagnostics=_trim_diagnostics(exc.diagnostics)) from None


def _refused(result: dict[str, Any], message: str) -> dict[str, Any]:
    """A worker's refusal comes with a placeholder value that must not pass for an answer."""
    errors = [d for d in result.get("diagnostics") or [] if d.get("severity") == "error"]
    if errors:
        raise ToolError(message, diagnostics=_trim_diagnostics(errors))
    return result


def _paused_state(s: Any) -> Any:
    """The paused run of this project, the user's or yours; the newest when there are more."""
    here = Path(_project_dir(s)).resolve()
    paused = [
        state for state in runs._store_for(s.ctx.app).runs.values()
        if state.last_paused is not None and state.project_dir.resolve() == here
    ]
    if not paused:
        raise ToolError("no run is paused: start one with debug_start")
    return paused[-1]


def _live_run(s: Any, a: dict[str, Any]) -> Any:
    """The run to control. Other projects stay read-only, so only a run of this one."""
    if a.get("run_id") is None:
        return _paused_state(s)
    run_id = a["run_id"]
    _, state = runs._locate(s.ctx.shim, run_id)
    if state is None or state.done is not None:
        raise ToolError(f"run {run_id} is not active: start a new one with debug_start")
    if state.project_dir.resolve() != Path(_project_dir(s)).resolve():
        raise ToolError(f"run {run_id} belongs to another project")
    return state


def _pause_view(s: Any, state: Any) -> dict[str, Any]:
    params = state.last_paused["params"]
    return {
        "runId": state.run_id, "status": "paused",
        **{k: params.get(k) for k in ("t", "tick", "reason", "breakpointId", "location", "frame")},
        "diagnostics": _trim_diagnostics(params.get("diagnostics") or []),
    }


async def _await_pause(s: Any, state: Any, before: Any, wait_s: float) -> dict[str, Any]:
    """The next pause after ``before``, or how the run ended, or that it is still going."""
    deadline = s.loop.time() + min(wait_s, 600)
    while True:
        if state.last_paused is not None and state.last_paused is not before:
            return _pause_view(s, state)
        if state.done is not None:
            return await _await_run(s, state.run_id, 5)
        if s.cancel_event.is_set():
            await runs.cancel_run(state.run_id, s.ctx.shim)
            return {"runId": state.run_id, "status": "cancelled"}
        if s.loop.time() >= deadline:
            return {
                "runId": state.run_id, "status": state.status,
                "note": "no pause yet: wait with debug_status, or pause it with debug_pause",
            }
        await s.sleep(0.05)


async def _command(
    s: Any, state: Any, command: str, params: dict[str, Any], wait_s: float
) -> dict[str, Any]:
    before = state.last_paused
    method, schema, _ = debug.COMMANDS[command]
    await _debug_call(s, method, debug._validate_params(schema, {**params, "runId": state.run_id}))
    return await _await_pause(s, state, before, wait_s)


@tool("Start a debug run of a model as it stands in your draft and wait for its first pause. The "
      "user sees it in the Plots dock and the Debug tab, and can take over. Without breakpoints it "
      "pauses at its start (`pause_on_entry`). Find a line for a line breakpoint in the block's "
      "source (`get_block_source`). Returns where it paused: time, reason, source location and, "
      "at a statement, the frame (locals, held outputs, previous values), and `breakpoints`, the "
      "status of each. If one did not bind, the run stays paused at its start so you can correct "
      "it with debug_set_breakpoints. When you are done, end the run with stop_run unless the "
      "user wants to carry on from there.",
      {"model": MODEL, "breakpoints": BREAKPOINTS, "pause_on_entry": BOOL, "t_end": NUM,
       "overrides": OVERRIDES, "wait_s": PAUSE_WAIT}, needs_project=True)
async def debug_start(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    name = _model_name_of(s, a)
    breakpoints = _breakpoints(a.get("breakpoints") or [])
    wait_s = a.get("wait_s", 60)
    # Only the worker's answer to debug.setBreakpoints says whether a breakpoint bound, and it
    # needs the built run: the start of the run is the first moment to ask.
    options = DebugStartOptions.model_validate({"breakpoints": [], "pauseOnEntry": True})
    run_id = await _start_run(s, name, a, a.get("overrides"), options)
    _announce_run(s, run_id, name, debugging=True)
    state = runs._store_for(s.ctx.app).get(run_id)
    entry = await _await_pause(s, state, None, wait_s)
    if entry["status"] != "paused":
        return entry
    if not breakpoints:
        return entry if a.get("pause_on_entry", True) else await _command(s, state, "continue", {}, wait_s)
    params = {"runId": run_id, "breakpoints": breakpoints}
    statuses = (await _debug_call(s, "debug.setBreakpoints", params))["breakpoints"]
    if a.get("pause_on_entry", False) or not all(status["verified"] for status in statuses):
        return {**entry, "breakpoints": statuses}
    result = await _command(s, state, "continue", {}, wait_s)
    if result["status"] != "paused":
        result["note"] = "no breakpoint fired before the run ended"
    return {**result, "breakpoints": statuses}


@tool("Where a debug run stands: paused (time, reason, location, frame), still running, or how it "
      "ended. Without `run_id`, the paused run of this project: the user's own as well as yours, "
      "so you can help with a run the user paused.",
      {"run_id": STR}, needs_project=True)
async def debug_status(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    if a.get("run_id") is None:
        return _pause_view(s, _paused_state(s))
    _, state = runs._locate(s.ctx.shim, a["run_id"])
    if state is not None and state.last_paused is not None:
        return _pause_view(s, state)
    if state is not None and state.done is None:
        return {"runId": state.run_id, "status": state.status}
    return _run_summary(_manifest(s, a["run_id"]))


@tool("Replace ALL breakpoints of a running debug run, including any the user set on it, and say "
      "for each whether it is verified and if not why. Works while it runs or is paused.",
      {"run_id": STR, "breakpoints": BREAKPOINTS}, ("breakpoints",), needs_project=True)
async def debug_set_breakpoints(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    state = _live_run(s, a)
    params = {"runId": state.run_id, "breakpoints": _breakpoints(a["breakpoints"])}
    return await _debug_call(s, "debug.setBreakpoints", params)


@tool("Continue a paused debug run to its next breakpoint or its end, and wait for that.",
      {"run_id": STR, "wait_s": PAUSE_WAIT}, needs_project=True)
async def debug_continue(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    return await _command(s, _live_run(s, a), "continue", {}, a.get("wait_s", 60))


@tool("Step a paused debug run and wait for the pause. `granularity`: statement (one statement "
      "of discrete code), tick (the next clock tick), solverStep or event.",
      {"run_id": STR, "wait_s": PAUSE_WAIT,
       "granularity": {"type": "string", "enum": ["statement", "tick", "solverStep", "event"]}},
      ("granularity",), needs_project=True)
async def debug_step(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    params = {"granularity": a["granularity"]}
    return await _command(s, _live_run(s, a), "step", params, a.get("wait_s", 60))


@tool("Run a paused debug run on to time `t` and pause there.",
      {"run_id": STR, "t": NUM, "wait_s": PAUSE_WAIT}, ("t",), needs_project=True)
async def debug_run_to(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    return await _command(s, _live_run(s, a), "runTo", {"t": a["t"]}, a.get("wait_s", 60))


@tool("Pause a debug run that is running.", {"run_id": STR}, ("run_id",), needs_project=True)
async def debug_pause(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    return await _command(s, _live_run(s, a), "pause", {}, 30)


@tool("Evaluate an expression at the pause, read-only: a signal such as `s\"Motor1/i\"`, `t`, or "
      "an expression over them and the frame's locals. `context` is the instance path that "
      "relative names resolve in.",
      {"run_id": STR, "expr": STR, "context": STR}, ("expr",), needs_project=True)
async def debug_evaluate(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    state = _live_run(s, a)
    params = {"runId": state.run_id, "expr": a["expr"], "context": a.get("context")}
    return _refused(await _debug_call(s, "debug.evaluate", params), "the expression failed")


@tool("The values of signals at the pause, by id.",
      {"run_id": STR, "ids": {"type": "array", "items": STR, "minItems": 1}}, ("ids",),
      needs_project=True)
async def debug_values(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    state = _live_run(s, a)
    return await _debug_call(s, "debug.values", {"runId": state.run_id, "ids": a["ids"]})


async def _edit(s: Any, a: dict[str, Any], command: str, params: dict[str, Any]) -> dict[str, Any]:
    state = _live_run(s, a)
    method, schema, _ = debug.COMMANDS[command]
    result = await _debug_call(s, method, debug._validate_params(schema, {**params, "runId": state.run_id}))
    return _refused(result, "the live edit was refused")


@tool("Change a parameter of a paused debug run from this moment on, to try a fix without "
      "restarting. `name` includes the instance: `Ctrl/aw`, not `aw`. It is a live edit: neither "
      "the model nor your draft changes. A fix that works goes into the model with update_block "
      "or set_globals.",
      {"run_id": STR, "name": STR, "value": NUM}, ("name", "value"), needs_project=True)
async def debug_set_parameter(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    return await _edit(s, a, "setParameter", {"name": a["name"], "value": a["value"]})


@tool("Change a state of a paused debug run from this moment on (`id` as listed by "
      "list_signals). A live edit, like debug_set_parameter.",
      {"run_id": STR, "id": STR, "value": NUM}, ("id", "value"), needs_project=True)
async def debug_set_state(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    return await _edit(s, a, "setState", {"id": a["id"], "value": a["value"]})


def _model_of_run(s: Any, run_id: str) -> str:
    return str(_manifest(s, run_id)["model"])


@tool("Rewind: replay a run up to time `t` and pause there, as a new debug run, so you can try "
      "another change from that moment. The run you rewind is stopped if it is still going.",
      {"run_id": STR, "t": NUM, "wait_s": PAUSE_WAIT}, ("run_id", "t"), needs_project=True)
async def debug_rewind(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    parent = a["run_id"]
    branch = (await debug._derive_run(s.ctx.shim, parent, "run.branch", a["t"]))["runId"]
    s.runs.add(branch)
    active = runs._store_for(s.ctx.app).get(parent)
    if active is not None and active.done is None:
        await runs.cancel_run(parent, s.ctx.shim)
    _announce_run(s, branch, _model_of_run(s, parent), debugging=True)
    state = runs._store_for(s.ctx.app).get(branch)
    return await _await_pause(s, state, None, a.get("wait_s", 60))


@tool("Run a finished or stopped debug run again as a normal run, with its live edits applied at "
      "the same moments, and wait for the result.",
      {"run_id": STR, "wait_s": {"type": "number"}}, ("run_id",), needs_project=True)
async def debug_replay(s: Any, a: dict[str, Any]) -> dict[str, Any]:
    replay = (await debug._derive_run(s.ctx.shim, a["run_id"], "run.replay", None))["runId"]
    s.runs.add(replay)
    _announce_run(s, replay, _model_of_run(s, a["run_id"]))
    return await _await_run(s, replay, min(a.get("wait_s", 300), 900))


async def stop_paused_runs(s: Any) -> None:
    """A closed chat leaves no paused run of its own behind; a paused run holds its worker task."""
    store = runs._store_for(s.ctx.app)
    for run_id in list(s.runs):
        state = store.get(run_id)
        if state is not None and state.last_paused is not None:
            with suppress(HTTPException, WorkerError):
                await runs.cancel_run(run_id, s.ctx.shim)


# ---------------------------------------------------------------------------- dispatch


def names() -> list[str]:
    return sorted(TOOLS)


async def call(s: Any, name: str, args: Any) -> tuple[dict[str, Any], bool]:
    """Run one tool; every failure is a result the model can act on, never an exception."""
    definition = TOOLS.get(name)
    if definition is None:
        return {"error": f"unknown tool {name!r}"}, True
    if not isinstance(args, dict):
        return {"error": "the arguments must be a JSON object"}, True
    if definition.needs_project and s.project is None:
        return {"error": "no project is open: create one with create_project first"}, True
    if s.question is not None and not definition.while_asking:
        return {"error": "the user has not answered your question yet: end your turn now"}, True
    try:
        jsonschema.validate(args, definition.schema)
    except jsonschema.ValidationError as exc:
        where = "/".join(str(part) for part in exc.path)
        return {"error": f"bad arguments at {where or 'the top level'}: {exc.message}"}, True
    try:
        return await definition.handler(s, args), False
    except ToolError as exc:
        return {"error": exc.message, **exc.details}, True
    except WorkerRpcFailure as exc:
        return {"error": exc.message, "diagnostics": _trim_diagnostics(exc.diagnostics)}, True
    except HTTPException as exc:
        return {"error": _error_text(exc)}, True
    except ValidationError as exc:
        first = exc.errors()[0]
        return {"error": f"{'.'.join(str(p) for p in first.get('loc', ()))}: {first.get('msg')}"}, True
