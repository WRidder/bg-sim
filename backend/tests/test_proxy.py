"""Proxy tests (plan sections 3.2, 3.6 and 3.7).

The catalog is proxied and cached per project with an mtime fingerprint over the
project library; the two check endpoints proxy the worker and map its errors
(422 for a worker error object, 504 for the plan's timeouts). Most tests use the
fixture-driven fake worker; the error-mapping tests use a scripted worker over the
same socket.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from bgsim_server.app import create_app
from bgsim_server.contracts import Catalog
from bgsim_server.worker import KIND_JSON, REQUEST_TIMEOUTS, encode_frame, read_frame

FIXTURES = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"
MODEL_FIXTURE = FIXTURES / "model" / "valid" / "model.dcmotor.json"
DIAGNOSTICS_FIXTURE = FIXTURES / "diagnostic" / "valid" / "diagnostics.sample.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _wait_ready(client: TestClient, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.get("/api/health").json()["worker"] == "ready":
            return
        time.sleep(0.02)
    raise AssertionError(f"the worker did not become ready within {timeout:g} s")


def _make_project(settings, name: str = "demo", files: tuple[str, ...] = ("C.jl",)) -> Path:
    """Create ``<projects_root>/<name>/library`` and return the library directory."""
    library = settings.projects_root / name / "library"
    library.mkdir(parents=True, exist_ok=True)
    for file_name in files:
        (library / file_name).write_text("@block Placeholder begin\nend\n", encoding="utf-8")
    return library


class CallLog:
    """Wrap ``WorkerSupervisor.call`` and record every request the app makes."""

    def __init__(self, supervisor) -> None:
        self._original = supervisor.call
        self.calls: list[tuple[str, dict[str, Any]]] = []
        supervisor.call = self  # instance attribute: not bound, __call__ takes method

    async def __call__(self, method: str, params: dict[str, Any] | None = None, **kwargs):
        self.calls.append((method, params or {}))
        return await self._original(method, params, **kwargs)

    def params(self, method: str) -> list[dict[str, Any]]:
        return [params for name, params in self.calls if name == method]


class StubWorker:
    """A scripted worker launcher: answers ``ping``, delegates everything else."""

    def __init__(self, port: int, handler) -> None:
        self.port = port
        self._handler = handler
        self._task: asyncio.Task | None = None

    @property
    def alive(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._serve(), name="stub-worker")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _serve(self) -> None:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        try:
            while True:
                frame = await read_frame(reader)
                if frame is None:
                    break
                message = json.loads(frame[1])
                if message.get("method") == "ping":
                    await self.send(
                        writer,
                        {
                            "id": message["id"],
                            "result": {"version": "0.1.0", "julia": "stub", "warm": True},
                        },
                    )
                else:
                    await self._handler(self, writer, message)
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()

    async def send(self, writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
        writer.write(encode_frame(KIND_JSON, json.dumps(message).encode("utf-8")))
        await writer.drain()

    async def result(self, writer: asyncio.StreamWriter, message: dict[str, Any], result: Any):
        await self.send(writer, {"id": message["id"], "result": result})


# --------------------------------------------------------------------------- catalog


def test_catalog_is_cached_per_project_and_invalidated_by_the_library(
    fake_settings, schema_validate
) -> None:
    library = _make_project(fake_settings)
    app = create_app(fake_settings)
    log = CallLog(app.state.worker)
    with TestClient(app) as client:
        _wait_ready(client)
        first = client.get("/api/catalog", params={"project": "demo"})
        assert first.status_code == 200
        payload = first.json()
        schema_validate("catalog", payload)
        assert len(Catalog.model_validate(payload).blocks) == 36

        calls = log.params("catalog.get")
        assert len(calls) == 1
        assert Path(calls[0]["projectLibraryDir"]) == library.resolve()
        assert Path(calls[0]["projectLibraryDir"]).is_absolute()

        second = client.get("/api/catalog", params={"project": "demo"})
        assert second.status_code == 200
        assert second.json() == payload
        assert len(log.params("catalog.get")) == 1, "a second request must hit the cache"

        # Rewriting a file bumps its mtime: the fingerprint changes and the cache misses.
        rewritten = library / "C.jl"
        stat = rewritten.stat()
        os.utime(rewritten, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        assert client.get("/api/catalog", params={"project": "demo"}).status_code == 200
        assert len(log.params("catalog.get")) == 2, "an mtime change invalidates the cache"

        (library / "X.jl").write_text("@block X begin\nend\n", encoding="utf-8")
        third = client.get("/api/catalog", params={"project": "demo"})
        assert third.status_code == 200
        assert len(log.params("catalog.get")) == 3, "a new library file invalidates the cache"

        # The cache is per project: another project cannot reuse demo's entry.
        other = _make_project(fake_settings, "other")
        assert client.get("/api/catalog", params={"project": "other"}).status_code == 200
        assert len(log.params("catalog.get")) == 4
        assert Path(log.params("catalog.get")[-1]["projectLibraryDir"]) == other.resolve()
        assert client.get("/api/catalog", params={"project": "demo"}).status_code == 200
        assert len(log.params("catalog.get")) == 4, "demo's entry survived the other project"


def test_catalog_without_a_project_asks_for_the_standard_library(fake_settings) -> None:
    app = create_app(fake_settings)
    log = CallLog(app.state.worker)
    with TestClient(app) as client:
        _wait_ready(client)
        response = client.get("/api/catalog")
        assert response.status_code == 200
        assert len(response.json()["blocks"]) == 36
        assert log.params("catalog.get") == [{"projectLibraryDir": None}]

        # An empty query value means "no project" and shares the standard-library entry.
        assert client.get("/api/catalog", params={"project": ""}).status_code == 200
        assert len(log.params("catalog.get")) == 1


def test_catalog_unknown_project_is_a_named_404(fake_settings) -> None:
    app = create_app(fake_settings)
    with TestClient(app) as client:
        _wait_ready(client)
        response = client.get("/api/catalog", params={"project": "nope"})
        assert response.status_code == 404
        assert "nope" in response.json()["detail"]
        for name in ("..", ".", "../escape", "a/b"):
            escaped = client.get("/api/catalog", params={"project": name})
            assert escaped.status_code == 404, f"{name!r} must not be a project"


# --------------------------------------------------------------------------- checks


def test_block_check_proxies_source_and_ref(fake_settings) -> None:
    app = create_app(fake_settings)
    log = CallLog(app.state.worker)
    source = "@block X begin\n    @ports p::Power{Generic}\nend"
    with TestClient(app) as client:
        _wait_ready(client)
        response = client.post("/api/check/block", json={"source": source, "ref": "project:Foo"})
        assert response.status_code == 200
        assert response.json() == {"diagnostics": [], "interface": None}
        assert log.params("block.check") == [{"source": source, "ref": "project:Foo"}]

        minimal = client.post("/api/check/block", json={"source": source})
        assert minimal.status_code == 200
        assert log.params("block.check")[-1] == {"source": source, "ref": None}


def test_model_check_returns_the_worker_result_unchanged(fake_settings, schema_validate) -> None:
    model = _load(MODEL_FIXTURE)
    diagnostics = _load(DIAGNOSTICS_FIXTURE)
    app = create_app(fake_settings)
    log = CallLog(app.state.worker)
    with TestClient(app) as client:
        _wait_ready(client)
        response = client.post("/api/check/model", json={"model": model})
        assert response.status_code == 200
        assert response.json() == {
            "diagnostics": diagnostics,
            "domains": {},
            "causality": {},
            "frames": {},
            "unitFactors": {},
            "signals": [],
            "stats": {"states": 0, "equations": 0},
        }
        schema_validate("worker-rpc", {"id": 1, "result": response.json()})

        params = log.params("model.check")[-1]
        assert Path(params["projectDir"]) == fake_settings.repo_root
        sent = params["model"]
        assert sent["name"] == model["name"]
        assert "from" in sent["diagram"]["connections"][0]
        assert "from_" not in sent["diagram"]["connections"][0]


def test_model_check_derives_or_forwards_project_dir(fake_settings) -> None:
    project = _make_project(fake_settings, "demo").parent
    model = _load(MODEL_FIXTURE)
    app = create_app(fake_settings)
    log = CallLog(app.state.worker)
    with TestClient(app) as client:
        _wait_ready(client)
        derived = client.post("/api/check/model", params={"project": "demo"}, json={"model": model})
        assert derived.status_code == 200
        assert Path(log.params("model.check")[-1]["projectDir"]) == project.resolve()

        explicit = client.post(
            "/api/check/model",
            json={"model": model, "projectDir": "D:/somewhere/else"},
        )
        assert explicit.status_code == 200
        assert log.params("model.check")[-1]["projectDir"] == "D:/somewhere/else"

        unknown = client.post("/api/check/model", params={"project": "nope"}, json={"model": model})
        assert unknown.status_code == 404
        assert "nope" in unknown.json()["detail"]


# --------------------------------------------------------------------------- error mapping


def test_worker_error_becomes_422_with_message_and_diagnostics(fake_settings) -> None:
    diagnostics = _load(DIAGNOSTICS_FIXTURE)

    async def handler(worker: StubWorker, writer, message) -> None:
        await worker.send(
            writer,
            {
                "id": message["id"],
                "error": {
                    "message": "block.check failed: the source is not a block",
                    "diagnostics": [diagnostics[0]],
                },
            },
        )

    app = create_app(fake_settings, worker_factory=lambda port: StubWorker(port, handler))
    with TestClient(app) as client:
        _wait_ready(client)
        response = client.post("/api/check/block", json={"source": "not a block"})
        assert response.status_code == 422
        assert response.json() == {
            "message": "block.check failed: the source is not a block",
            "diagnostics": [diagnostics[0]],
        }


def test_check_timeouts_map_to_504(fake_settings, monkeypatch) -> None:
    model = _load(MODEL_FIXTURE)

    async def handler(worker: StubWorker, writer, message) -> None:
        return None  # never answers

    app = create_app(fake_settings, worker_factory=lambda port: StubWorker(port, handler))
    monkeypatch.setitem(REQUEST_TIMEOUTS, "block.check", 0.05)
    monkeypatch.setitem(REQUEST_TIMEOUTS, "model.check", 0.05)
    with TestClient(app) as client:
        _wait_ready(client)
        started = time.perf_counter()
        block = client.post("/api/check/block", json={"source": "@block X begin\nend"})
        assert block.status_code == 504
        assert "timed out" in block.json()["detail"]
        checked = client.post("/api/check/model", json={"model": model})
        assert checked.status_code == 504
        assert "timed out" in checked.json()["detail"]
        assert time.perf_counter() - started < 3.0


def test_invalid_worker_result_is_502(fake_settings) -> None:
    async def handler(worker: StubWorker, writer, message) -> None:
        await worker.result(writer, message, {})

    app = create_app(fake_settings, worker_factory=lambda port: StubWorker(port, handler))
    with TestClient(app) as client:
        _wait_ready(client)
        response = client.get("/api/catalog")
        assert response.status_code == 502
        assert "contract" in response.json()["detail"]


async def test_proxy_reports_503_before_the_worker_is_ready(fake_settings) -> None:
    # No lifespan: the supervisor is built but never started, so nothing is connected.
    app = create_app(fake_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/catalog")
    assert response.status_code == 503
    assert "not connected" in response.json()["detail"]


def test_unknown_route_does_not_fall_through_to_the_proxy(fake_settings) -> None:
    with TestClient(create_app(fake_settings)) as client:
        assert client.get("/api/catalog/nope").status_code == 404
        assert client.post("/api/check/block", json={}).status_code == 422
