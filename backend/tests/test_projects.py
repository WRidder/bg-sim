"""Projects, models and library endpoints (plan sections 3.3, 3.7 and 6).

Everything here runs without Julia: the app is built with ``create_app`` and the
project router's dependency is replaced by a :class:`ProjectStore` in ``tmp_path``.
The tests cover project CRUD, model CRUD and schema rejection, library CRUD and
catalog-cache invalidation, unsafe names and paths, atomic writes, and
create-from-example. The JSON Schema fixtures and validators come from
``contracts/``, exactly like the contract tests in ``test_contracts.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from bgsim_server import projects
from bgsim_server.app import create_app
from bgsim_server.projects import ProjectStore

TESTS_DIR = Path(__file__).resolve().parent
REPO = TESTS_DIR.parents[1]
FIXTURES = REPO / "contracts" / "fixtures"
SCHEMAS = REPO / "contracts" / "schemas"
MODEL_FIXTURE = FIXTURES / "model" / "valid" / "model.dcmotor.json"
PROJECT_FIXTURE = FIXTURES / "project" / "valid" / "project.dcmotor.json"

DEFAULT_PROJECT = {
    "format": "bgsim.project",
    "language": "0.1.0",
    "name": "demo",
    "models": [],
    "libraryDir": "library",
    "scenesDir": "scenes",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _model() -> dict[str, Any]:
    """A fresh copy of the DC-motor fixture."""
    return _load(MODEL_FIXTURE)


def _project_file(store: ProjectStore, name: str) -> dict[str, Any]:
    return _load(store.projects_root / name / "bgsim.project.json")


def _model_dir(store: ProjectStore, name: str) -> Path:
    return store.projects_root / name / "models"


@pytest.fixture
def store(tmp_path: Path) -> ProjectStore:
    """An isolated store with temporary projects and examples directories."""
    return ProjectStore(tmp_path / "projects", tmp_path / "examples", SCHEMAS)


@pytest.fixture
def app(fake_settings, store: ProjectStore):
    application = create_app(fake_settings)
    application.dependency_overrides[projects.get_project_store] = lambda: store
    return application


@pytest.fixture
def client(app):
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()


def _create(client: TestClient, name: str = "demo", **extra: Any):
    return client.post("/api/projects", json={"name": name, **extra})


# --------------------------------------------------------------------------- projects


def test_create_empty_project_returns_the_open_payload_and_lists_it(
    client: TestClient, store: ProjectStore, schema_validate
) -> None:
    response = _create(client)
    assert response.status_code == 201
    payload = response.json()

    assert payload["name"] == "demo"
    assert payload["path"] == str((store.projects_root / "demo").resolve())
    assert payload["project"] == DEFAULT_PROJECT
    assert payload["models"] == []
    assert payload["library"] == []
    schema_validate("project", payload["project"])

    root = store.projects_root / "demo"
    assert (root / "bgsim.project.json").is_file()
    for directory in ("models", "library", "scenes"):
        assert (root / directory).is_dir(), f"{directory}/ must exist in an empty project"
    assert (root / "bgsim.project.json").read_bytes().endswith(b"\n")
    assert b"\r" not in (root / "bgsim.project.json").read_bytes()

    listed = client.get("/api/projects")
    assert listed.status_code == 200
    assert listed.json()["root"] == str(store.root)
    assert listed.json()["projects"] == [
        {
            "name": "demo",
            "path": str(root.resolve()),
            "language": "0.1.0",
            "models": [],
            "modified": listed.json()["projects"][0]["modified"],
            "valid": True,
            "error": None,
        }
    ]
    assert listed.json()["projects"][0]["modified"]

    opened = client.get("/api/projects/demo")
    assert opened.status_code == 200
    assert opened.json() == payload


def test_list_projects_without_a_root_returns_empty(
    client: TestClient, store: ProjectStore
) -> None:
    response = client.get("/api/projects")
    assert response.status_code == 200
    assert response.json() == {"root": str(store.root), "projects": []}
    assert not store.projects_root.exists(), "listing must not create the root"


def test_create_rejects_duplicates_and_unsafe_names(client: TestClient) -> None:
    assert _create(client).status_code == 201
    duplicate = _create(client)
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]

    for name in ["..", ".", "../x", "..\\x", "C:/x", "C:x", "/abs", "a/b", "a\\b", "CON", "x."]:
        response = _create(client, name)
        assert response.status_code == 400, f"{name!r} must be rejected"
        assert "invalid project name" in response.json()["detail"]

    missing = client.post("/api/projects", json={})
    assert missing.status_code == 422
    extra = client.post("/api/projects", json={"name": "fine", "surprise": True})
    assert extra.status_code == 422


def test_list_skips_non_projects_and_reports_broken_ones(
    client: TestClient, store: ProjectStore
) -> None:
    assert _create(client, "good").status_code == 201
    root = store.projects_root
    (root / "notes.txt").write_text("not a project\n", encoding="utf-8")
    (root / "empty-directory").mkdir()
    broken = root / "broken"
    broken.mkdir()
    (broken / "bgsim.project.json").write_text("{ this is not JSON", encoding="utf-8")

    projects_list = client.get("/api/projects").json()["projects"]
    assert [entry["name"] for entry in projects_list] == ["broken", "good"]
    broken_entry = projects_list[0]
    assert broken_entry["valid"] is False
    assert broken_entry["models"] == []
    assert "not valid JSON" in broken_entry["error"]
    assert projects_list[1]["valid"] is True


def test_open_and_delete_project(
    client: TestClient, store: ProjectStore, schema_validate
) -> None:
    assert _create(client).status_code == 201
    document = _model()
    assert client.put("/api/projects/demo/models/iconic", json=document).status_code == 200
    (store.projects_root / "demo" / "library" / "Gear.jl").write_text(
        "@block Gear begin\nend\n", encoding="utf-8"
    )

    opened = client.get("/api/projects/demo")
    assert opened.status_code == 200
    payload = opened.json()
    assert payload["project"]["name"] == "demo"
    assert [entry["name"] for entry in payload["models"]] == ["iconic"]
    assert payload["models"][0]["inProject"] is True
    assert [entry["name"] for entry in payload["library"]] == ["Gear"]
    schema_validate("project", payload["project"])

    assert client.delete("/api/projects/demo").status_code == 204
    assert not (store.projects_root / "demo").exists()
    assert client.get("/api/projects/demo").status_code == 404
    assert client.delete("/api/projects/demo").status_code == 404
    assert client.get("/api/projects").json()["projects"] == []


def test_put_project_updates_tabs_and_is_schema_validated(
    client: TestClient, schema_validate
) -> None:
    assert _create(client).status_code == 201
    document = _load(PROJECT_FIXTURE)
    document["name"] = "demo"
    document["models"] = ["beta", "alpha"]
    response = client.put("/api/projects/demo", json=document)
    assert response.status_code == 200
    assert response.json()["project"]["models"] == ["beta", "alpha"]
    assert response.json()["project"]["$comment"] == document["$comment"]
    schema_validate("project", response.json()["project"])

    wrong_name = dict(document)
    wrong_name["name"] = "somewhere-else"
    mismatch = client.put("/api/projects/demo", json=wrong_name)
    assert mismatch.status_code == 400
    assert "demo" in mismatch.json()["detail"]

    invalid = dict(document)
    del invalid["libraryDir"]
    rejected = client.put("/api/projects/demo", json=invalid)
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["errors"]
    assert client.get("/api/projects/demo").json()["project"]["models"] == ["beta", "alpha"]

    escaping = dict(document)
    escaping["libraryDir"] = "../outside"
    escaped = client.put("/api/projects/demo", json=escaping)
    assert escaped.status_code == 422
    assert "libraryDir" in escaped.json()["detail"]


def test_open_rejects_a_project_file_that_names_another_directory(
    client: TestClient, store: ProjectStore
) -> None:
    assert _create(client).status_code == 201
    project_file = store.projects_root / "demo" / "bgsim.project.json"
    document = _load(project_file)
    document["name"] = "renamed"
    project_file.write_text(json.dumps(document) + "\n", encoding="utf-8")

    response = client.get("/api/projects/demo")
    assert response.status_code == 422
    assert "renamed" in response.json()["detail"]


# --------------------------------------------------------------------------- models


def test_model_crud_tracks_the_project_tab_list(
    client: TestClient, store: ProjectStore, schema_validate
) -> None:
    assert _create(client).status_code == 201
    document = _model()
    response = client.put("/api/projects/demo/models/iconic", json=document)
    assert response.status_code == 200
    assert response.json() == document

    path = _model_dir(store, "demo") / "iconic.bgmodel.json"
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    assert b"\r" not in raw
    schema_validate("model", json.loads(raw))
    assert _project_file(store, "demo")["models"] == ["iconic"]

    fetched = client.get("/api/projects/demo/models/iconic")
    assert fetched.status_code == 200
    assert fetched.json() == document
    # The .bgmodel.json suffix is accepted on the way in.
    assert client.get("/api/projects/demo/models/iconic.bgmodel.json").json() == document

    second = json.loads(json.dumps(document))
    second["name"] = "SecondModel"
    assert client.put("/api/projects/demo/models/second", json=second).status_code == 200
    assert _project_file(store, "demo")["models"] == ["iconic", "second"]
    listing = client.get("/api/projects/demo").json()["models"]
    assert [entry["name"] for entry in listing] == ["iconic", "second"]
    assert all(entry["inProject"] for entry in listing)

    assert client.delete("/api/projects/demo/models/iconic").status_code == 204
    assert not path.exists()
    assert _project_file(store, "demo")["models"] == ["second"]
    assert client.get("/api/projects/demo/models/iconic").status_code == 404
    assert client.delete("/api/projects/demo/models/iconic").status_code == 404
    assert client.get("/api/projects/demo/models/second").json() == second


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda document: document.pop("settings"), id="missing-required"),
        pytest.param(
            lambda document: document["settings"].__setitem__("reltol", 0.0),
            id="reltol-not-positive",
        ),
        pytest.param(
            lambda document: document.__setitem__("surprise", 1), id="extra-property"
        ),
        pytest.param(
            lambda document: document.__setitem__("plots", None), id="plots-null"
        ),
        pytest.param(
            lambda document: document["diagram"]["connections"][0]["to"].__setitem__(
                "port", None
            ),
            id="port-null",
        ),
        pytest.param(
            lambda document: document["diagram"]["nodes"][0].__setitem__(
                "$comment", None
            ),
            id="comment-null",
        ),
        pytest.param(
            lambda document: document["diagram"]["nodes"][0].__setitem__("rotation", "90"),
            id="rotation-is-a-string",
        ),
    ],
)
def test_model_put_rejects_invalid_documents(
    client: TestClient, store: ProjectStore, mutate
) -> None:
    assert _create(client).status_code == 201
    document = _model()
    mutate(document)
    response = client.put("/api/projects/demo/models/bad", json=document)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["message"]
    assert detail["errors"]
    assert not (_model_dir(store, "demo") / "bad.bgmodel.json").exists()
    assert _project_file(store, "demo")["models"] == []


def test_invalid_model_put_leaves_the_previous_document_untouched(
    client: TestClient, store: ProjectStore
) -> None:
    assert _create(client).status_code == 201
    document = _model()
    assert client.put("/api/projects/demo/models/iconic", json=document).status_code == 200
    path = _model_dir(store, "demo") / "iconic.bgmodel.json"
    before = path.read_bytes()

    broken = _model()
    broken["settings"]["t_end"] = "one second"
    assert client.put("/api/projects/demo/models/iconic", json=broken).status_code == 422
    assert path.read_bytes() == before

    assert (
        client.put(
            "/api/projects/demo/models/iconic",
            content=b"{ not json",
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/projects/demo/models/iconic",
            json=[1, 2, 3],
        ).status_code
        == 422
    )
    assert path.read_bytes() == before


def test_model_get_reports_a_file_that_is_not_json(
    client: TestClient, store: ProjectStore
) -> None:
    assert _create(client).status_code == 201
    path = _model_dir(store, "demo") / "broken.bgmodel.json"
    path.write_text("{ not json", encoding="utf-8")
    response = client.get("/api/projects/demo/models/broken")
    assert response.status_code == 422
    assert "not valid JSON" in response.json()["detail"]


# --------------------------------------------------------------------------- library


def test_library_crud_writes_lf_and_invalidates_the_catalog(
    client: TestClient, store: ProjectStore, app
) -> None:
    assert _create(client).status_code == 201
    source = "@block Gear begin\r\n    @parameters\r\nend\r\n"
    response = client.put(
        "/api/projects/demo/library/Gear",
        content=source,
        headers={"content-type": "text/plain"},
    )
    assert response.status_code == 200
    assert response.json() == {"project": "demo", "name": "Gear", "file": "Gear.jl"}

    path = store.projects_root / "demo" / "library" / "Gear.jl"
    assert path.read_bytes() == b"@block Gear begin\n    @parameters\nend\n"
    assert not list(path.parent.glob(".*.tmp")), "the temp file must be gone"

    fetched = client.get("/api/projects/demo/library/Gear")
    assert fetched.status_code == 200
    assert fetched.headers["content-type"].startswith("text/plain")
    assert fetched.text == path.read_text(encoding="utf-8")
    assert client.get("/api/projects/demo/library/Gear.jl").text == fetched.text
    assert [entry["name"] for entry in client.get("/api/projects/demo").json()["library"]] == [
        "Gear"
    ]

    library_dir = store.projects_root / "demo" / "library"
    cache = app.state.catalog_cache
    cache.store("demo", library_dir, {"catalog": 1})
    assert len(cache) == 1
    assert (
        client.put("/api/projects/demo/library/Gear", content="@block Gear begin\nend\n").status_code
        == 200
    )
    assert len(cache) == 0, "a library write must invalidate the project's catalog"

    cache.store("demo", library_dir, {"catalog": 2})
    assert len(cache) == 1
    assert client.delete("/api/projects/demo/library/Gear").status_code == 204
    assert len(cache) == 0, "a library delete must invalidate the project's catalog"
    assert not path.exists()
    assert client.get("/api/projects/demo/library/Gear").status_code == 404
    assert client.delete("/api/projects/demo/library/Gear").status_code == 404


def test_library_rejects_unsafe_block_names_and_non_utf8(
    client: TestClient, store: ProjectStore
) -> None:
    assert _create(client).status_code == 201
    for block in ["1bad", "Bad-Name", "../x", "..\\x", "a/b", "C:x"]:
        response = client.put(
            f"/api/projects/demo/library/{quote(block, safe='')}",
            content=b"@block X begin\nend\n",
        )
        # A path-shaped name can be resolved by httpx or make the route not match;
        # the store-level rejection below is the one that returns 400.
        assert 400 <= response.status_code < 500, f"{block!r} must be rejected"
    assert not list((store.projects_root / "demo" / "library").iterdir())

    rejected = client.put("/api/projects/demo/library/Bad", content=b"\xff\xfe")
    assert rejected.status_code == 400
    assert "UTF-8" in rejected.json()["detail"]


def test_library_accepts_json_encoded_sources(
    client: TestClient, store: ProjectStore
) -> None:
    assert _create(client).status_code == 201
    wrapped = client.put(
        "/api/projects/demo/library/Wrapped",
        json={"source": "@block Wrapped begin\nend\n"},
    )
    assert wrapped.status_code == 200
    assert (store.projects_root / "demo" / "library" / "Wrapped.jl").read_text(
        encoding="utf-8"
    ) == "@block Wrapped begin\nend\n"

    bare = client.put("/api/projects/demo/library/Bare", json="@block Bare begin\nend\n")
    assert bare.status_code == 200
    assert (store.projects_root / "demo" / "library" / "Bare.jl").read_text(
        encoding="utf-8"
    ) == "@block Bare begin\nend\n"


# --------------------------------------------------------------------------- safety


@pytest.mark.parametrize(
    "name",
    ["../x", "..\\x", "C:/x", "C:x", "/abs", "a/b", "a\\b", "..", "."],
)
def test_project_names_that_escape_are_rejected(
    client: TestClient, store: ProjectStore, name: str
) -> None:
    with pytest.raises(projects.ProjectError) as info:
        store.open_project(name)
    assert info.value.status_code == 400
    assert _create(client, name).status_code == 400
    assert not store.projects_root.exists() or not any(store.projects_root.iterdir())


@pytest.mark.parametrize(
    "name",
    ["../x", "..\\x", "C:/x", "C:x", "/abs", "a/b", "a\\b", "..", "."],
)
def test_model_names_that_escape_are_rejected(
    client: TestClient, store: ProjectStore, name: str
) -> None:
    assert _create(client).status_code == 201
    with pytest.raises(projects.ProjectError) as info:
        store.get_model("demo", name)
    assert info.value.status_code == 400

    if name in {".", ".."}:
        # httpx resolves dot segments before sending; the store check above is the
        # meaningful one. The other names reach the route as a single segment.
        return
    encoded = quote(name, safe="")
    response = client.get(f"/api/projects/demo/models/{encoded}")
    assert response.status_code == 400, f"{name!r} must be rejected with 400"
    assert not (_model_dir(store, "demo") / "x.bgmodel.json").exists()


def test_encoded_project_traversal_is_rejected(client: TestClient, store: ProjectStore) -> None:
    assert _create(client).status_code == 201
    for encoded in ["%2E%2E", "%2E", "..%5Cx", "C%3Ax"]:
        response = client.get(f"/api/projects/{encoded}")
        assert response.status_code == 400, encoded
        assert "invalid project name" in response.json()["detail"]
    assert [entry["name"] for entry in client.get("/api/projects").json()["projects"]] == [
        "demo"
    ]


@pytest.mark.parametrize(
    "name",
    ["../x", "..\\x", "C:/x", "C:x", "/abs", "a/b", "a\\b", "..", ".", "1bad", "Bad-Name", "CON"],
)
def test_block_names_that_escape_are_rejected(store: ProjectStore, name: str) -> None:
    store.create_project("demo")
    with pytest.raises(projects.ProjectError) as info:
        store.put_library("demo", name, "@block X begin\nend\n")
    assert info.value.status_code == 400
    assert not list((store.projects_root / "demo" / "library").iterdir())


# --------------------------------------------------------------------------- atomic writes


def test_replace_failure_leaves_the_old_file_and_no_temp_file(
    client: TestClient, store: ProjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _create(client).status_code == 201
    assert (
        client.put("/api/projects/demo/library/Gear", content="@block Gear begin\nend\n").status_code
        == 200
    )
    path = store.projects_root / "demo" / "library" / "Gear.jl"
    before = path.read_bytes()

    def fail_replace(source, destination):
        raise OSError("the disk is full")

    monkeypatch.setattr(projects.os, "replace", fail_replace)
    response = client.put("/api/projects/demo/library/Gear", content="changed")
    assert response.status_code == 500
    assert "could not write" in response.json()["detail"]
    assert path.read_bytes() == before
    assert not list(path.parent.glob(".*.tmp")), "a failed write must remove its temp file"

    document = _model()
    failed_model = client.put("/api/projects/demo/models/new", json=document)
    assert failed_model.status_code == 500
    assert not (_model_dir(store, "demo") / "new.bgmodel.json").exists()
    assert _project_file(store, "demo")["models"] == []


def test_successful_writes_leave_no_temp_files(
    client: TestClient, store: ProjectStore
) -> None:
    assert _create(client).status_code == 201
    assert (
        client.put("/api/projects/demo/models/iconic", json=_model()).status_code == 200
    )
    assert client.put("/api/projects/demo/library/Gear", content="x").status_code == 200
    for directory in (_model_dir(store, "demo"), store.projects_root / "demo" / "library"):
        assert not list(directory.glob(".*.tmp"))
    assert (store.projects_root / "demo" / "library" / "Gear.jl").read_bytes() == b"x\n"


# --------------------------------------------------------------------------- examples


def _make_example(root: Path) -> Path:
    """A miniature ``examples/dc-motor`` tree for the copy tests."""
    example = root / "dc-motor"
    for directory in ("models", "library", "scenes"):
        (example / directory).mkdir(parents=True)
    project = dict(DEFAULT_PROJECT)
    project["name"] = "dc-motor"
    project["models"] = ["iconic"]
    (example / "bgsim.project.json").write_text(
        json.dumps(project, indent=2) + "\n", encoding="utf-8"
    )
    (example / "models" / "iconic.bgmodel.json").write_text(
        json.dumps(_model(), indent=2) + "\n", encoding="utf-8"
    )
    (example / "library" / "Gear.jl").write_text(
        "@block Gear begin\nend\n", encoding="utf-8"
    )
    (example / "scenes" / "demo.sdf").write_text("<sdf/>\n", encoding="utf-8")
    return example


def test_create_from_example_copies_the_tree_and_renames_the_project(
    client: TestClient, store: ProjectStore, schema_validate
) -> None:
    source = _make_example(store.examples_root)
    response = client.post("/api/projects", json={"name": "my-motor", "example": "dc-motor"})
    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "my-motor"
    assert payload["project"]["name"] == "my-motor"
    assert payload["project"]["models"] == ["iconic"]
    schema_validate("project", payload["project"])

    destination = store.projects_root / "my-motor"
    copied = destination / "models" / "iconic.bgmodel.json"
    assert copied.read_bytes() == (source / "models" / "iconic.bgmodel.json").read_bytes()
    assert (destination / "library" / "Gear.jl").is_file()
    assert (destination / "scenes" / "demo.sdf").is_file()
    assert [entry["name"] for entry in payload["library"]] == ["Gear"]

    # The copy is independent of the example tree.
    (destination / "library" / "Gear.jl").write_text("changed\n", encoding="utf-8")
    assert (source / "library" / "Gear.jl").read_text(encoding="utf-8") == "@block Gear begin\nend\n"

    assert client.get("/api/projects/my-motor/models/iconic").status_code == 200


def test_create_from_example_unknown_names_the_available_examples(
    client: TestClient, store: ProjectStore
) -> None:
    response = client.post("/api/projects", json={"name": "x", "example": "nope"})
    assert response.status_code == 404
    assert "available examples: (none)" in response.json()["detail"]

    _make_example(store.examples_root)
    response = client.post("/api/projects", json={"name": "x", "example": "nope"})
    assert response.status_code == 404
    assert "available examples: dc-motor" in response.json()["detail"]

    unsafe = client.post("/api/projects", json={"name": "x", "example": "../dc-motor"})
    assert unsafe.status_code == 400
    assert not (store.projects_root / "x").exists()


def test_create_from_example_without_a_project_file_builds_one(
    client: TestClient, store: ProjectStore
) -> None:
    example = store.examples_root / "bare"
    (example / "models").mkdir(parents=True)
    (example / "models" / "only.bgmodel.json").write_text(
        json.dumps(_model()) + "\n", encoding="utf-8"
    )
    response = client.post("/api/projects", json={"name": "from-bare", "example": "bare"})
    assert response.status_code == 201
    payload = response.json()
    assert payload["project"]["name"] == "from-bare"
    assert payload["project"]["models"] == ["only"]
    assert (store.projects_root / "from-bare" / "library").is_dir()
    assert (store.projects_root / "from-bare" / "scenes").is_dir()


def test_create_from_example_with_an_invalid_project_file_cleans_up(
    client: TestClient, store: ProjectStore
) -> None:
    example = store.examples_root / "broken"
    example.mkdir(parents=True)
    (example / "bgsim.project.json").write_text("{ not json", encoding="utf-8")
    response = client.post("/api/projects", json={"name": "nope", "example": "broken"})
    assert response.status_code == 422
    assert "not valid JSON" in response.json()["detail"]
    assert not (store.projects_root / "nope").exists()
    assert not list(store.projects_root.glob(".nope.creating-*"))
