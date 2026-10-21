"""Worker supervisor tests (plan 3.6 and section 6).

Framing, request/response correlation with two in-flight requests, the notification
fan-out, per-method timeouts, binary-frame tolerance and auto-restart with backoff.
Everything here runs against the fake worker (or a scripted test worker) over a real
socket; `test_julia_worker.py` runs the same supervisor against the real Julia
process.
"""

from __future__ import annotations

import asyncio
import json
import struct
import time
from contextlib import suppress
from pathlib import Path

import numpy as np
import pytest

from bgsim_server.worker import (
    KIND_BINARY,
    KIND_JSON,
    REQUEST_TIMEOUTS,
    FakeWorker,
    WorkerNotReady,
    WorkerRpcError,
    WorkerSupervisor,
    WorkerTimeout,
    encode_frame,
    read_frame,
)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"
RUN_START_FIXTURE = FIXTURE_DIR / "worker-rpc" / "valid" / "request.run-start.json"


class ScriptedWorker:
    """Test launcher: answers `ping` immediately, delegates the rest to `handler`."""

    def __init__(self, port: int, handler):
        self.port = port
        self._handler = handler
        self._task: asyncio.Task | None = None

    @property
    def alive(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._serve(), name="scripted-worker")

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
                    await self.reply(
                        writer,
                        message["id"],
                        {"version": "0.1.0", "julia": "scripted", "warm": True},
                    )
                else:
                    await self._handler(self, writer, message)
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()

    async def reply(self, writer: asyncio.StreamWriter, request_id: int, result: object) -> None:
        payload = json.dumps({"id": request_id, "result": result}).encode("utf-8")
        writer.write(encode_frame(KIND_JSON, payload))
        await writer.drain()


def _run_params(run_dir: Path, run_id: str) -> dict:
    fixture = json.loads(RUN_START_FIXTURE.read_text(encoding="utf-8"))
    return {
        "runId": run_id,
        "model": fixture["params"]["model"],
        "projectDir": str(run_dir.parent.parent),
        "runDir": str(run_dir),
    }


async def _collect_run(queue: asyncio.Queue, timeout: float = 10.0) -> list[dict]:
    notifications: list[dict] = []
    while True:
        message = await asyncio.wait_for(queue.get(), timeout)
        notifications.append(message)
        if message["method"] == "run.done":
            return notifications


# --------------------------------------------------------------------------- framing


def test_encode_frame_layout() -> None:
    # length counts the kind byte plus the payload (so it is never 0)
    assert encode_frame(KIND_JSON, b'{"id":1}') == struct.pack("<IB", 9, 0) + b'{"id":1}'
    assert encode_frame(KIND_BINARY, b"") == struct.pack("<IB", 1, 1)


async def test_framing_round_trip_over_a_socket() -> None:
    received: list[tuple[int, bytes] | None] = []

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        received.append(await read_frame(reader))
        received.append(await read_frame(reader))
        writer.write(encode_frame(KIND_JSON, b'{"id":7,"result":{"ok":true}}'))
        writer.write(encode_frame(KIND_BINARY, b"\x00\x01\x02"))
        await writer.drain()
        await reader.read(-1)  # keep the connection open until the client is done
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(encode_frame(KIND_JSON, b'{"id":1,"method":"ping","params":{}}'))
        writer.write(encode_frame(KIND_BINARY, b"\xff\x00"))
        await writer.drain()
        assert await read_frame(reader) == (KIND_JSON, b'{"id":7,"result":{"ok":true}}')
        assert await read_frame(reader) == (KIND_BINARY, b"\x00\x01\x02")
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()
    assert received == [
        (KIND_JSON, b'{"id":1,"method":"ping","params":{}}'),
        (KIND_BINARY, b"\xff\x00"),
    ]


def test_request_timeouts_match_the_plan() -> None:
    assert REQUEST_TIMEOUTS["block.check"] == 5.0
    assert REQUEST_TIMEOUTS["model.check"] == 60.0
    assert REQUEST_TIMEOUTS["run.start"] is None  # runs are unlimited


# --------------------------------------------------------------------------- fake worker


async def test_fake_worker_ping_round_trip(fake_settings, schema_validate) -> None:
    supervisor = WorkerSupervisor(fake_settings)
    await supervisor.start()
    try:
        await supervisor.wait_ready(timeout=5.0)
        assert supervisor.state == "ready"
        started = time.perf_counter()
        result = await supervisor.call("ping")
        elapsed = time.perf_counter() - started
        assert result == {"version": "0.1.0", "julia": "fake", "warm": True}
        assert elapsed < 1.0, "the fake answers over the loopback socket, not on a timer"
        schema_validate("worker-rpc", {"id": 1, "result": result})
    finally:
        await supervisor.stop()


async def test_fake_worker_answers_from_the_contract_fixtures(fake_settings, schema_validate) -> None:
    supervisor = WorkerSupervisor(fake_settings)
    await supervisor.start()
    try:
        await supervisor.wait_ready(timeout=5.0)
        catalog = await supervisor.call("catalog.get", {"projectLibraryDir": None})
        schema_validate("catalog", catalog)
        assert any(block["ref"] == "stdlib:bondgraph/C" for block in catalog["blocks"])

        check = await supervisor.call(
            "model.check",
            {
                "model": json.loads(RUN_START_FIXTURE.read_text(encoding="utf-8"))["params"][
                    "model"
                ],
                "projectDir": str(fake_settings.projects_root),
            },
        )
        schema_validate("worker-rpc", {"id": 1, "result": check})
        codes = [diagnostic["code"] for diagnostic in check["diagnostics"]]
        assert "E000" in codes and "W206" in codes, "the diagnostics sample is returned"

        block = await supervisor.call("block.check", {"source": "@block X begin\nend", "ref": None})
        schema_validate("worker-rpc", {"id": 1, "result": block})
        assert block == {"diagnostics": [], "interface": None}
    finally:
        await supervisor.stop()


async def test_unknown_method_is_an_error_response(fake_settings, schema_validate) -> None:
    supervisor = WorkerSupervisor(fake_settings)
    await supervisor.start()
    try:
        await supervisor.wait_ready(timeout=5.0)
        with pytest.raises(WorkerRpcError) as info:
            await supervisor.call("no.such.method", {})
        assert "no.such.method" in str(info.value)
        assert info.value.diagnostics == []
        schema_validate(
            "worker-rpc",
            {"id": 1, "error": {"message": str(info.value), "diagnostics": []}},
        )
    finally:
        await supervisor.stop()


# --------------------------------------------------------------------------- correlation


async def test_two_in_flight_requests_correlate(fake_settings) -> None:
    seen: list[tuple[int, str]] = []

    async def handler(worker: ScriptedWorker, writer, message) -> None:
        seen.append((message["id"], message["method"]))
        if len(seen) == 2:  # answer both, in reverse order
            for request_id, method in reversed(seen):
                await worker.reply(writer, request_id, {"method": method})

    supervisor = WorkerSupervisor(
        fake_settings, worker_factory=lambda port: ScriptedWorker(port, handler)
    )
    await supervisor.start()
    try:
        await supervisor.wait_ready(timeout=5.0)
        first, second = await asyncio.gather(
            supervisor.call("block.check", {"source": "a", "ref": None}),
            supervisor.call("model.check", {"model": {}, "projectDir": "."}),
        )
        assert first == {"method": "block.check"}
        assert second == {"method": "model.check"}
        assert [method for _, method in seen] == ["block.check", "model.check"]
    finally:
        await supervisor.stop()


async def test_request_timeout_is_reported(fake_settings) -> None:
    async def handler(worker: ScriptedWorker, writer, message) -> None:
        pass  # never answers

    supervisor = WorkerSupervisor(
        fake_settings, worker_factory=lambda port: ScriptedWorker(port, handler)
    )
    await supervisor.start()
    try:
        await supervisor.wait_ready(timeout=5.0)
        started = time.perf_counter()
        with pytest.raises(WorkerTimeout):
            await supervisor.call("block.check", {"source": "x", "ref": None}, timeout=0.2)
        assert time.perf_counter() - started < 2.0
    finally:
        await supervisor.stop()


# --------------------------------------------------------------------------- binary frames


async def test_worker_tolerates_binary_frames_from_the_backend(fake_settings) -> None:
    supervisor = WorkerSupervisor(fake_settings)
    await supervisor.start()
    try:
        await supervisor.wait_ready(timeout=5.0)
        await supervisor.send_binary(b"\x00\x01\x02\x03")
        assert (await supervisor.call("ping"))["warm"] is True
    finally:
        await supervisor.stop()


async def test_supervisor_tolerates_binary_frames_from_the_worker(fake_settings) -> None:
    async def handler(worker: ScriptedWorker, writer, message) -> None:
        writer.write(encode_frame(KIND_BINARY, b"junk"))
        await writer.drain()
        await worker.reply(writer, message["id"], {"ok": True})

    supervisor = WorkerSupervisor(
        fake_settings, worker_factory=lambda port: ScriptedWorker(port, handler)
    )
    await supervisor.start()
    try:
        await supervisor.wait_ready(timeout=5.0)
        assert await supervisor.call("cache.clear", {}) == {"ok": True}
        assert (await supervisor.call("ping"))["warm"] is True
    finally:
        await supervisor.stop()


# --------------------------------------------------------------------------- restart


async def test_worker_restart_with_backoff(fake_settings, wait_until) -> None:
    supervisor = WorkerSupervisor(fake_settings)
    general = supervisor.subscribe_notifications()
    await supervisor.start()
    try:
        await supervisor.wait_ready(timeout=5.0)
        worker = supervisor.worker
        assert isinstance(worker, FakeWorker)
        await worker.crash()
        await wait_until(lambda: supervisor.state != "ready", timeout=3.0)
        await supervisor.wait_ready(timeout=10.0)
        assert (await supervisor.call("ping"))["warm"] is True
        messages = []
        while not general.empty():
            messages.append(general.get_nowait())
        restarts = [m for m in messages if m["method"] == "worker_restarted"]
        assert restarts, "the restart is reported to the UI (plan 2.1)"
        assert restarts[0]["params"]["attempt"] == 1
    finally:
        supervisor.unsubscribe_notifications(general)
        await supervisor.stop()


async def test_call_before_start_is_not_ready(fake_settings) -> None:
    supervisor = WorkerSupervisor(fake_settings)
    with pytest.raises(WorkerNotReady):
        await supervisor.call("ping")


# --------------------------------------------------------------------------- fake runs


async def test_fake_run_writes_a_valid_manifest_and_synthetic_data(
    fake_settings, schema_validate
) -> None:
    supervisor = WorkerSupervisor(fake_settings)
    await supervisor.start()
    try:
        await supervisor.wait_ready(timeout=5.0)
        run_id = "run-test-0001"
        run_dir = fake_settings.projects_root / "demo" / "runs" / run_id
        queue = supervisor.subscribe(run_id)
        started = time.perf_counter()
        try:
            assert await supervisor.call("run.start", _run_params(run_dir, run_id)) == {
                "accepted": True
            }
            notifications = await _collect_run(queue)
        finally:
            supervisor.unsubscribe(run_id, queue)
        elapsed = time.perf_counter() - started
        assert 0.5 < elapsed < 10.0, "the fake paces the run in real time"

        methods = [message["method"] for message in notifications]
        assert methods.count("run.done") == 1
        assert "run.phase" in methods and "run.progress" in methods
        phases = [m["params"]["phase"] for m in notifications if m["method"] == "run.phase"]
        assert phases[0] == "simulate" and "write" in phases
        progress = [m["params"] for m in notifications if m["method"] == "run.progress"]
        assert [p["rows"] for p in progress] == sorted(p["rows"] for p in progress)
        done = notifications[-1]["params"]
        assert done["runId"] == run_id
        assert done["status"] == "done"
        assert done["diagnostics"] == []
        schema_validate("worker-rpc", {"method": "run.done", "params": done})
        schema_validate(
            "worker-rpc",
            {"method": "run.progress", "params": progress[0]},
        )

        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        schema_validate("run-manifest", manifest)
        assert manifest["id"] == run_id
        assert manifest["status"] == "done"
        assert manifest["time"] == {"n": 1001, "t0": 0.0, "t1": 1.0}

        columns = np.fromfile(run_dir / "columns.f64", dtype="<f8").reshape(5, 1001)
        stream = np.fromfile(run_dir / "stream.f64", dtype="<f8").reshape(-1, 5)
        assert np.array_equal(stream, columns.T), "stream.f64 is the row-major view"
        t = columns[0]
        assert np.allclose(columns[1], np.sin(2.0 * np.pi * t))
        assert columns[2][249] == 0.0 and columns[2][250] == 2.0
        assert columns[3][1000] == 10.0
        assert columns[4][499] == 0.0 and columns[4][500] == 1.0
    finally:
        await supervisor.stop()


async def test_fake_run_cancel(fake_settings, schema_validate) -> None:
    supervisor = WorkerSupervisor(fake_settings)
    await supervisor.start()
    try:
        await supervisor.wait_ready(timeout=5.0)
        run_id = "run-test-cancel"
        run_dir = fake_settings.projects_root / "demo" / "runs" / run_id
        queue = supervisor.subscribe(run_id)
        try:
            await supervisor.call("run.start", _run_params(run_dir, run_id))
            first = await asyncio.wait_for(queue.get(), 5.0)
            assert first["method"] == "run.phase"
            assert await supervisor.call("run.cancel", {"runId": run_id}) == {"ok": True}
            notifications = await _collect_run(queue)
        finally:
            supervisor.unsubscribe(run_id, queue)
        done = notifications[-1]["params"]
        assert done["status"] == "cancelled"
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        schema_validate("run-manifest", manifest)
        assert manifest["status"] == "cancelled"
        assert 0 < manifest["time"]["n"] < 1001
        assert await supervisor.call("run.cancel", {"runId": "run-does-not-exist"}) == {"ok": False}
    finally:
        await supervisor.stop()
