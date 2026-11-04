"""The draft of one assistant session: models, library blocks and docs pages laid over the
saved project.

A tool changes the draft and nothing else. The saved project changes only in :meth:`Draft.apply`,
when the user applies the proposal. A model that an edit returns to its saved state drops out of
the draft again, so the proposal is always the true difference.
"""

from __future__ import annotations

import copy
import json
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from .. import docs
from ..contracts import Model
from ..projects import ProjectStore, _block_name, _detail_message, _validate
from . import modelops


def _message(exc: HTTPException) -> str:
    return _detail_message(exc.detail)


def _normal(document: dict[str, Any]) -> Any:
    """The document in one form, so key order and defaulted fields never read as a change."""
    try:
        return Model.model_validate(document).model_dump(by_alias=True, mode="json")
    except ValidationError:
        return document


class Draft:
    def __init__(self, store: ProjectStore, project: str):
        self.store = store
        self.project = project
        self.models: dict[str, dict[str, Any] | None] = {}  # None: deleted
        self.library: dict[str, str | None] = {}            # None: deleted
        self.pages: dict[tuple[str | None, str], dict[str, Any]] = {}
        self._base_models: dict[str, dict[str, Any] | None] = {}
        self._base_library: dict[str, str | None] = {}

    # -- reading ------------------------------------------------------------------------------
    def _disk_model(self, name: str) -> dict[str, Any] | None:
        try:
            return json.loads(self.store.get_model(self.project, name))
        except HTTPException as exc:
            if exc.status_code == 404:
                return None
            raise

    def _disk_block(self, name: str) -> str | None:
        try:
            return self.store.get_library(self.project, name)
        except HTTPException as exc:
            if exc.status_code == 404:
                return None
            raise

    def base_model(self, name: str) -> dict[str, Any] | None:
        if name not in self._base_models:
            self._base_models[name] = self._disk_model(name)
        return self._base_models[name]

    def base_block(self, name: str) -> str | None:
        if name not in self._base_library:
            self._base_library[name] = self._disk_block(name)
        return self._base_library[name]

    def model(self, name: str) -> dict[str, Any] | None:
        return self.models[name] if name in self.models else self.base_model(name)

    def block(self, name: str) -> str | None:
        return self.library[name] if name in self.library else self.base_block(name)

    def page(self, owner: str | None, page_id: str) -> str | None:
        """The draft text of a page, or None when the draft has not touched it."""
        entry = self.pages.get((owner, page_id))
        return None if entry is None else entry["text"]

    def listing(self) -> dict[str, list[str]]:
        if not self.project:
            return {"models": [], "library": []}
        opened = self.store.open_project(self.project)
        models = {m["name"] for m in opened["models"]}
        blocks = {b["name"] for b in opened["library"]}
        for name, value in self.models.items():
            (models.add if value is not None else models.discard)(name)
        for name, value in self.library.items():
            (blocks.add if value is not None else blocks.discard)(name)
        return {"models": sorted(models), "library": sorted(blocks)}

    # -- writing ------------------------------------------------------------------------------
    def put_model(self, name: str, document: dict[str, Any] | None) -> None:
        base = self.base_model(name)
        same = (document is None and base is None) or (
            document is not None and base is not None and _normal(document) == _normal(base)
        )
        if same:
            self.models.pop(name, None)
        else:
            self.models[name] = document

    def put_block(self, name: str, source: str | None) -> None:
        name = _block_name(name)
        if source == self.base_block(name):
            self.library.pop(name, None)
        else:
            self.library[name] = source

    def put_page(
        self, owner: str | None, page_id: str, title: str, text: str, parent: str | None
    ) -> None:
        self.pages[(owner, page_id)] = {"title": title, "text": text, "parent": parent}

    def discard(self) -> None:
        self.models.clear()
        self.library.clear()
        self.pages.clear()
        self._base_models.clear()
        self._base_library.clear()

    def refresh(self) -> None:
        """Forget saved copies the draft does not depend on: the next read sees the user's edits."""
        self._base_models = {k: v for k, v in self._base_models.items() if k in self.models}
        self._base_library = {k: v for k, v in self._base_library.items() if k in self.library}

    # -- comparing ----------------------------------------------------------------------------
    @property
    def changed(self) -> bool:
        return bool(self.models or self.library or self.pages)

    def files(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name, document in sorted(self.models.items()):
            base = self.base_model(name)
            change = "added" if base is None else "removed" if document is None else "changed"
            out.append({
                "kind": "model", "name": name, "change": change,
                "rows": modelops.diff_models(base, document),
            })
        for name, source in sorted(self.library.items()):
            base_source = self.base_block(name)
            change = "added" if base_source is None else "removed" if source is None else "changed"
            out.append({"kind": "library", "name": name, "change": change, "rows": []})
        for (owner, page_id), _entry in sorted(self.pages.items(), key=lambda kv: str(kv[0])):
            out.append({
                "kind": "doc", "name": f"{owner or '@project'}/{page_id}", "change": "changed",
                "rows": [],
            })
        return out

    def problems(self) -> list[tuple[str, str]]:
        """``(file, message)`` for what the store would refuse."""
        out: list[tuple[str, str]] = []
        for name, document in self.models.items():
            if document is None:
                continue
            try:
                self.store._check_schema("model", document, "the model document")
                _validate(Model, document, "the model document")
            except HTTPException as exc:
                out.append((f"model:{name}", _message(exc)))
            out.extend((f"model:{name}", text) for text in modelops.lint(document))
        return out

    def conflicts(self) -> list[str]:
        """What changed on disk since the draft was based on it."""
        out = []
        for name in self.models:
            base, disk = self.base_model(name), self._disk_model(name)
            if (base is None) != (disk is None) or (
                base is not None and disk is not None and _normal(base) != _normal(disk)
            ):
                out.append(f"model:{name}")
        for name in self.library:
            if self.base_block(name) != self._disk_block(name):
                out.append(f"library:{name}")
        return out

    # -- applying -----------------------------------------------------------------------------
    def _backup(self, folder: Path, relative: str, content: str) -> None:
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    def apply(self, open_model: str | None, session: str) -> dict[str, Any]:
        """Write the draft; the open model stays with the editor (returned as ``openModel``)."""
        project_dir = self.store._require_project(self.project)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        folder = project_dir / "logs" / "assistant" / f"backup-{stamp}-{session[:8]}"
        applied: list[str] = []
        result: dict[str, Any] = {"applied": applied, "backup": None}
        wrote_backup = False
        for name, document in self.models.items():
            base = self.base_model(name)
            if base is not None:
                self._backup(folder, f"models/{name}.bgmodel.json", json.dumps(base, indent=2) + "\n")
                wrote_backup = True
            if name == open_model and document is not None:
                result["openModel"] = document
            elif document is None:
                self.store.delete_model(self.project, name)
            else:
                self.store.put_model(self.project, name, document)
            applied.append(f"model:{name}")
        for name, source in self.library.items():
            base_source = self.base_block(name)
            if base_source is not None:
                self._backup(folder, f"library/{name}.jl", base_source)
                wrote_backup = True
            if source is None:
                self.store.delete_library(self.project, name)
            else:
                self.store.put_library(self.project, name, source)
            applied.append(f"library:{name}")
        for (owner, page_id), entry in self.pages.items():
            with suppress(HTTPException):
                before = docs.read_page_text(self.store, self.project, owner, page_id)
                self._backup(folder, f"docs/{owner or '@project'}/{page_id}.md", before)
                wrote_backup = True
            docs.write_page_text(
                self.store, self.project, owner, page_id, entry["title"], entry["text"],
                entry["parent"],
            )
            applied.append(f"doc:{owner or '@project'}/{page_id}")
        if wrote_backup:
            result["backup"] = str(folder)
        self._rebase()
        return result

    def _rebase(self) -> None:
        """The applied draft is the new base: the chat goes on with an empty proposal."""
        self._base_models.update({k: copy.deepcopy(v) for k, v in self.models.items()})
        self._base_library.update(self.library)
        self.models.clear()
        self.library.clear()
        self.pages.clear()
