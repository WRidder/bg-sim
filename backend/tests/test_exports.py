"""Export API tests (plan/EXPORT_PLAN.md P-EX1, W-EX1).

The HTTP tests run against the fake export runner (``BGSIM_FAKE_WORKER``: no Julia, no
compiler), which follows the real interface and refusal rules. ``test_source_only_build``
runs the real ``fmu_build`` without a compiler (D-EX15), and the ``julia``-marked test at
the end runs the whole real pipeline on a small scoped model.
"""

from __future__ import annotations

import copy
import io
import json
import time
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bgsim_server import exports, fmu_build
from bgsim_server.app import create_app

TESTS_DIR = Path(__file__).resolve().parent
REPO = TESTS_DIR.parents[1]
FIXTURES = REPO / "contracts" / "fixtures"
SCOPE_REQUEST = FIXTURES / "export-request" / "valid" / "export-request.scope.json"


def _request() -> dict[str, Any]:
    doc = json.loads(SCOPE_REQUEST.read_text(encoding="utf-8"))
    doc.pop("$comment", None)
    return doc


def _model() -> dict[str, Any]:
    return _request()["model"]


def _with_markers(model: dict[str, Any]) -> dict[str, Any]:
    model = copy.deepcopy(model)
    nodes = model["diagram"]["nodes"]
    nodes.append({"id": "m1", "name": "setpoint", "block": {"ref": "stdlib:converters/ExportInput"},
                  "position": {"x": 0, "y": 0}, "params": {"value": "1.5"}})
    nodes.append({"id": "m2", "name": "speed", "block": {"ref": "stdlib:converters/ExportOutput"},
                  "position": {"x": 0, "y": 0}})
    return model


@pytest.fixture
def client(fake_settings, monkeypatch):
    monkeypatch.setenv("BGSIM_FAKE_EXPORT_S", "0.02")
    (fake_settings.projects_root / "demo").mkdir(parents=True)
    with TestClient(create_app(fake_settings)) as test_client:
        yield test_client


def _start(client: TestClient, body: dict[str, Any], model: str = "plant") -> str:
    response = client.post(f"/api/projects/demo/models/{model}/export", json=body)
    assert response.status_code == 201, response.text
    return response.json()["exportId"]


def _wait(client: TestClient, export_id: str, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    doc: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/exports/{export_id}")
        assert response.status_code == 200, response.text
        doc = response.json()
        if doc["status"] in ("done", "refused", "failed", "cancelled"):
            return doc
        time.sleep(0.02)
    raise AssertionError(f"export {export_id} did not finish: {doc}")


def test_whole_model_export_and_download(client, fake_settings, schema_validate) -> None:
    export_id = _start(client, {"model": _with_markers(_model()),
                                "settings": {"method": "auto", "dt": None}})
    doc = _wait(client, export_id)
    schema_validate("export-job", doc)
    assert doc["status"] == "done", doc
    assert doc["scope"] is None and doc["model"] == "plant" and doc["project"] == "demo"
    report = doc["report"]
    assert [i["name"] for i in report["inputs"]] == ["setpoint"]
    assert report["inputs"][0]["start"] == 1.5
    assert [o["name"] for o in report["outputs"]] == ["speed"]
    assert report["build"]["sourceOnly"] is True and report["build"]["note"]
    assert doc["fmu"] == {"file": "ScopeModel.fmu", "bytes": doc["fmu"]["bytes"], "sourceOnly": True}
    assert any(note.startswith("Source-only FMU") for note in doc["notes"])
    assert {"juliaS", "flattenS", "referenceS", "exportS", "buildS", "totalS"} <= set(doc["timings"])

    fmu = client.get(f"/api/exports/{export_id}/fmu")
    assert fmu.status_code == 200
    assert fmu.headers["content-disposition"].endswith('filename="ScopeModel.fmu"')
    with zipfile.ZipFile(io.BytesIO(fmu.content)) as archive:
        names = archive.namelist()
        assert "modelDescription.xml" in names and "sources/model.c" in names
        assert b'name="setpoint"' in archive.read("modelDescription.xml")

    # The job is stored under the project and still served by a new backend process.
    job_dir = fake_settings.projects_root / "demo" / "exports" / export_id
    stored = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    assert stored["status"] == "done"
    request = json.loads((job_dir / "request.json").read_text(encoding="utf-8"))
    assert request["projectDir"] == str((fake_settings.projects_root / "demo").resolve())
    assert request["referenceBudgetS"] == 120.0
    with TestClient(create_app(fake_settings)) as fresh:
        assert fresh.get(f"/api/exports/{export_id}").json()["status"] == "done"
        assert fresh.get(f"/api/exports/{export_id}/fmu").status_code == 200


def test_no_markers_warns_w209(client) -> None:
    doc = _wait(client, _start(client, {"model": _model()}))
    assert doc["status"] == "done"
    assert "W209" in {d["code"] for d in doc["diagnostics"]}
    assert doc["report"]["inputs"] == [] and doc["report"]["outputs"] == []


def test_scoped_export_publishes_the_ports(client, schema_validate) -> None:
    body = _request()
    body["settings"] = {"method": "rk4", "dt": 0.0001}
    doc = _wait(client, _start(client, body))
    schema_validate("export-job", doc)
    assert doc["status"] == "done" and doc["scope"] == "Plant"
    report = doc["report"]
    assert report["name"] == "ScopeModel_Plant" and doc["fmu"]["file"] == "ScopeModel_Plant.fmu"
    assert {i["name"]: i["start"] for i in report["inputs"]} == {"u": 2.0, "p_e": 0.0}
    assert [o["name"] for o in report["outputs"]] == ["y", "p_f"]
    assert report["method"] == "rk4" and report["dt"] == 0.0001

    body["powerInputs"] = {"p": "flow"}
    report = _wait(client, _start(client, body))["report"]
    assert {i["name"] for i in report["inputs"]} == {"u", "p_f"}
    assert [o["name"] for o in report["outputs"]] == ["y", "p_e"]


def test_refusals_are_diagnostics_not_failures(client, schema_validate) -> None:
    body = _request()
    body["powerInputs"] = {}
    doc = _wait(client, _start(client, body))
    schema_validate("export-job", doc)
    assert doc["status"] == "refused"
    assert doc["error"] == "the power port `p` needs the variable the host imposes"
    assert [(d["code"], d["path"]) for d in doc["diagnostics"]] == [("E112", "Plant/p")]
    assert doc["report"] is None and doc["fmu"] is None
    assert client.get(f"/api/exports/{doc['id']}/fmu").status_code == 404

    body["scope"] = "Drive"
    doc = _wait(client, _start(client, body))
    assert doc["status"] == "refused" and doc["diagnostics"][0]["code"] == "E112"
    assert "is not a subsystem" in doc["error"]

    # A CSV source inside what is exported is E110 at its path.
    model = _model()
    inner = model["diagram"]["nodes"][1]["block"]["subsystem"]["diagram"]["nodes"]
    inner.append({"id": "s3", "name": "Table", "block": {"ref": "stdlib:sources/CsvSource"},
                  "position": {"x": 0, "y": 0}})
    doc = _wait(client, _start(client, {"model": model, "scope": "Plant",
                                        "powerInputs": {"p": "effort"}}))
    assert doc["status"] == "refused"
    assert [(d["code"], d["path"]) for d in doc["diagnostics"]] == [("E110", "Plant/Table")]


def test_cancel_a_running_export(client, monkeypatch) -> None:
    monkeypatch.setenv("BGSIM_FAKE_EXPORT_S", "1.0")
    store = exports._store_for(client.app)
    store.runner.delay = 1.0
    export_id = _start(client, {"model": _model()})
    time.sleep(0.1)
    assert client.get(f"/api/exports/{export_id}").json()["status"] == "running"
    assert client.delete(f"/api/exports/{export_id}").json() == {"ok": True}
    doc = client.get(f"/api/exports/{export_id}").json()
    assert doc["status"] == "cancelled" and doc["finished"] is not None
    assert client.delete(f"/api/exports/{export_id}").json() == {"ok": False}


def test_jobs_wait_for_the_one_export_slot(client) -> None:
    store = exports._store_for(client.app)
    store.runner.delay = 0.2
    first = _start(client, {"model": _model()})
    second = _start(client, {"model": _model()})
    time.sleep(0.05)
    assert client.get(f"/api/exports/{second}").json()["status"] == "queued"
    assert _wait(client, first)["status"] == "done"
    assert _wait(client, second)["status"] == "done"


def test_unknown_project_model_and_export(client) -> None:
    assert client.post("/api/projects/nope/models/m/export",
                       json={"model": _model()}).status_code == 404
    assert client.post("/api/projects/demo/models/a..b/export",
                       json={"model": _model()}).status_code == 404
    assert client.post("/api/projects/demo/models/m/export",
                       json={"model": _model(), "settings": {"method": "tsit5"}}).status_code == 422
    assert client.get("/api/exports/export-missing").status_code == 404
    assert client.get("/api/exports/..").status_code == 404


def test_history_is_pruned_per_model(fake_settings, tmp_path) -> None:
    exports_dir = tmp_path / "exports"
    for k in range(12):
        job = exports_dir / f"export-{k:02d}"
        job.mkdir(parents=True)
        (job / "job.json").write_text(json.dumps({
            "model": "plant" if k < 11 else "other", "status": "done",
            "created": f"2026-10-30T10:{k:02d}:00Z"}), encoding="utf-8")
    exports._prune(exports_dir, "plant", exports.EXPORT_HISTORY, active={"export-00"})
    left = sorted(p.name for p in exports_dir.iterdir())
    # the newest 9 of `plant` plus the new one make 10; the active and the other model stay
    assert left == ["export-00"] + [f"export-{k:02d}" for k in range(2, 12)]


def _fake_export_dir(path: Path) -> Path:
    report = json.loads((FIXTURES / "export-report" / "valid" / "export-report.rk4.json")
                        .read_text(encoding="utf-8"))
    report.pop("build")
    (path / "sources").mkdir(parents=True)
    (path / "sources" / "model.c").write_text("/* model */\n", encoding="utf-8")
    (path / "modelDescription.xml").write_text("<fmiModelDescription/>\n", encoding="utf-8")
    (path / "export.json").write_text(json.dumps(report), encoding="utf-8")
    return path


def test_source_only_build_without_a_compiler(tmp_path, monkeypatch, schema_validate) -> None:
    """D-EX15: without a compiler the build still writes a source-only FMU, and says so."""
    monkeypatch.setattr(fmu_build, "find_compiler", lambda: None)
    export_dir = _fake_export_dir(tmp_path / "export")
    result = fmu_build.build_fmu(export_dir, runtime_dir=tmp_path)
    assert result.ok and result.fmu is not None
    with zipfile.ZipFile(result.fmu) as archive:
        assert not any(n.startswith("binaries/") for n in archive.namelist())
    report = json.loads((export_dir / "export.json").read_text(encoding="utf-8"))
    schema_validate("export-report", report)
    build = report["build"]
    assert build["compilerFound"] is False and build["sourceOnly"] is True
    assert build["note"] == fmu_build.SOURCE_ONLY_NOTE
    assert build["allocationsAfterInstantiate"] is None and build["symbolCheck"] is None


def test_compiler_lookup(monkeypatch, tmp_path) -> None:
    cc = tmp_path / "mycc.exe"
    cc.write_text("", encoding="utf-8")
    monkeypatch.setenv("BGSIM_CC", str(cc))
    assert fmu_build.find_compiler() == str(cc)
    monkeypatch.setenv("BGSIM_CC", str(tmp_path / "missing.exe"))
    assert fmu_build.find_compiler() is None
    env = fmu_build._tool_env(str(cc))
    assert env is not None and env["PATH"].startswith(str(tmp_path))
    assert fmu_build.harness_steps_for(1) == 20_000
    assert fmu_build.harness_steps_for(12_500) == 1_600
    assert fmu_build.harness_steps_for(10**9) == 200


@pytest.mark.julia
def test_real_export_of_a_scoped_model(real_settings, schema_validate) -> None:
    """The whole pipeline: a Julia process per job, the real build, the contract shapes."""
    (real_settings.projects_root / "demo").mkdir(parents=True)
    with TestClient(create_app(real_settings)) as client:
        body = _request()
        body["settings"] = {"method": "auto", "dt": None}
        doc = _wait(client, _start(client, body), timeout=900)
        schema_validate("export-job", doc)
        assert doc["status"] == "done", doc
        assert {i["name"] for i in doc["report"]["inputs"]} == {"u", "p_e"}
        assert doc["timings"]["juliaS"] > 0
        build = doc["report"]["build"]
        if build["compilerFound"]:
            assert build["ok"] and build["allocationsAfterInstantiate"] == 0
            assert doc["fmu"]["sourceOnly"] is False
        fmu = client.get(f"/api/exports/{doc['id']}/fmu")
        assert fmu.status_code == 200 and fmu.content[:2] == b"PK"
