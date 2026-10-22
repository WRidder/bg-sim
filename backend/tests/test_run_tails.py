"""Live-tail hardening (P2.1): the 20/s cap and the late-subscriber backlog.

A scripted worker writes a real ``stream.f64`` and emits ``run.progress`` faster
than the plan's 20 messages per second. The run WebSocket must still deliver at
most 20 ``run.tail`` messages per second. A second scenario pauses between
progress notifications so a subscriber can join while no new rows arrive: the
backlog must be sent when the ``subscribe`` message is handled, not when the next
progress notification happens to arrive.
"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from bgsim_server.app import create_app
from bgsim_server.worker import KIND_JSON, encode_frame, read_frame

REPO = Path(__file__).resolve().parents[2]
MODEL_FIXTURE = REPO / "contracts" / "fixtures" / "model" / "valid" / "model.dcmotor.json"


def _model(duration: float) -> dict[str, Any]:
    model = json.loads(MODEL_FIXTURE.read_text(encoding="utf-8"))
    model["settings"]["t_end"] = duration
    return model


def _make_project(settings, name: str = "demo") -> Path:
    project = settings.projects_root / name
    project.mkdir(parents=True, exist_ok=True)
    return project


def _wait_ready(client: TestClient, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.get("/api/health").json()["worker"] == "ready":
            return
        time.sleep(0.02)
    raise AssertionError(f"the worker did not become ready within {timeout:g} s")


def _start(client: TestClient, duration: float) -> str:
    response = client.post("/api/projects/demo/runs", json={"model": _model(duration)})
    assert response.status_code == 201, response.text
    return response.json()["runId"]


def _wait_rows(client: TestClient, run_id: str, minimum: int, timeout: float = 5.0) -> dict[str, Any]:
    """Poll the manifest until the run has reported ``minimum`` recorded rows."""
    deadline = time.monotonic() + timeout
    document: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200, response.text
        document = response.json()
        if document["status"] != "running" or document["time"]["n"] >= minimum:
            return document
        time.sleep(0.01)
    raise AssertionError(f"the run reported only {document.get('time')} rows in {timeout:g} s")


class SyntheticRunWorker:
    """A scripted worker that writes a synthetic run, pausable for the backlog test."""

    def __init__(
        self,
        port: int,
        *,
        rows: int,
        duration: float,
        batch: int,
        interval: float,
        pause_after: int | None = None,
        pause_seconds: float = 0.0,
    ) -> None:
        self.port = port
        self.rows = rows
        self.duration = duration
        self.batch = batch
        self.interval = interval
        self.pause_after = pause_after
        self.pause_seconds = pause_seconds
        self._task: asyncio.Task | None = None
        self._run_tasks: list[asyncio.Task] = []
        self._writer: asyncio.StreamWriter | None = None
        self._cancelled: set[str] = set()

    @property
    def alive(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._serve(), name="synthetic-run-worker")

    async def stop(self) -> None:
        for task in self._run_tasks:
            task.cancel()
        for task in self._run_tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task
        self._run_tasks.clear()
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _serve(self) -> None:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        self._writer = writer
        try:
            while True:
                frame = await read_frame(reader)
                if frame is None:
                    break
                message = json.loads(frame[1])
                method = message.get("method")
                params = message.get("params") or {}
                if method == "ping":
                    await self._send(
                        {
                            "id": message["id"],
                            "result": {"version": "0.1.0", "julia": "synthetic", "warm": True},
                        }
                    )
                elif method == "run.start":
                    await self._send({"id": message["id"], "result": {"accepted": True}})
                    self._run_tasks.append(
                        asyncio.create_task(self._emit(params), name="synthetic-run")
                    )
                elif method == "run.cancel":
                    run_id = str(params.get("runId"))
                    self._cancelled.add(run_id)
                    await self._send({"id": message["id"], "result": {"ok": True}})
                else:
                    await self._send(
                        {
                            "id": message["id"],
                            "error": {
                                "message": f"method {method!r} is not scripted here",
                                "diagnostics": [],
                            },
                        }
                    )
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()

    async def _emit(self, params: dict[str, Any]) -> None:
        run_id = str(params["runId"])
        run_dir = Path(params["runDir"])
        run_dir.mkdir(parents=True, exist_ok=True)
        count = self.rows
        t = np.linspace(0.0, self.duration, count)
        values = np.column_stack(
            (
                t,
                np.sin(2.0 * np.pi * t),
                np.where(t >= 0.5, 2.0, 0.0),
                np.floor(t * 10.0),
                np.where(t >= 0.25, 1.0, 0.0),
            )
        ).astype("<f8")
        status = "done"
        try:
            with (run_dir / "stream.f64").open("wb") as stream:
                paused = False
                for begin in range(0, count, self.batch):
                    end = min(count, begin + self.batch)
                    np.ascontiguousarray(values[begin:end]).tofile(stream)
                    stream.flush()
                    await self._notify(
                        "run.progress",
                        {"runId": run_id, "t": float(t[end - 1]), "rows": end},
                    )
                    if run_id in self._cancelled:
                        status = "cancelled"
                        break
                    if (
                        self.pause_after is not None
                        and not paused
                        and end >= self.pause_after
                    ):
                        paused = True
                        await asyncio.sleep(self.pause_seconds)
                    await asyncio.sleep(self.interval)
            await self._notify(
                "run.phase",
                {"runId": run_id, "phase": "write", "t_s": float(t[max(end - 1, 0)])},
            )
        finally:
            stats = {
                "compile_s": 0.0,
                "sim_s": float(self.duration),
                "steps": count - 1,
                "events": 0,
                "states": 2,
                "equations": 5,
            }
            await self._notify(
                "run.done",
                {
                    "runId": run_id,
                    "status": status,
                    "stats": stats,
                    "diagnostics": [],
                },
            )

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._send({"method": method, "params": params})

    async def _send(self, message: dict[str, Any]) -> None:
        writer = self._writer
        if writer is None:
            return
        writer.write(encode_frame(KIND_JSON, json.dumps(message).encode("utf-8")))
        await writer.drain()


def _app(fake_settings, workers: list[SyntheticRunWorker], **options: Any):
    def factory(port: int) -> SyntheticRunWorker:
        worker = SyntheticRunWorker(port, **options)
        workers.append(worker)
        return worker

    return create_app(fake_settings, worker_factory=factory)


def test_live_tail_is_capped_at_twenty_messages_per_second(fake_settings) -> None:
    _make_project(fake_settings)
    workers: list[SyntheticRunWorker] = []
    # 100 progress notifications over about 2 s = 50/s, above the 20/s cap, so
    # the tail count can only stay at 20/s because the backend throttles it.
    app = _app(
        fake_settings,
        workers,
        rows=1001,
        duration=2.0,
        batch=10,
        interval=0.02,
    )
    with TestClient(app) as client:
        _wait_ready(client)
        run_id = _start(client, 2.0)
        started = time.monotonic()
        arrivals: list[float] = []
        with client.websocket_connect(f"/api/ws/runs/{run_id}") as socket:
            socket.send_json({"subscribe": ["Synthetic/sine"]})
            while True:
                message = socket.receive_json()
                if message["method"] == "run.tail":
                    arrivals.append(time.monotonic() - started)
                if message["method"] == "run.done":
                    break
        elapsed = time.monotonic() - started
        assert elapsed > 0.5, "the scripted run produced a real window to measure"
        assert len(arrivals) >= 5, "the subscription received live tails"
        assert len(arrivals) <= 20 * elapsed + 2, (
            f"{len(arrivals)} tail messages in {elapsed:.3f} s is above 20/s"
        )
        # No one-second window contains more than the cap; the final tail at
        # run.done is deliberately unthrottled and may add one message.
        for index, at in enumerate(arrivals):
            in_window = sum(1 for other in arrivals[index:] if other < at + 1.0)
            assert in_window <= 21, f"{in_window} tail messages within 1 s at {at:.3f} s"
        rate = len(arrivals) / elapsed
        print(
            f"\nrun.tail: {len(arrivals)} messages in {elapsed:.3f} s "
            f"= {rate:.1f} messages/s"
        )


def test_a_late_subscriber_gets_the_backlog_before_the_run_resumes(fake_settings) -> None:
    _make_project(fake_settings)
    workers: list[SyntheticRunWorker] = []
    rows = 400
    pause_after = 200
    duration = 2.0
    app = _app(
        fake_settings,
        workers,
        rows=rows,
        duration=duration,
        batch=20,
        interval=0.05,
        pause_after=pause_after,
        pause_seconds=1.0,
    )
    with TestClient(app) as client:
        _wait_ready(client)
        run_id = _start(client, duration)
        document = _wait_rows(client, run_id, pause_after)
        assert document["time"]["n"] >= pause_after

        tails: list[dict[str, Any]] = []
        with client.websocket_connect(f"/api/ws/runs/{run_id}") as socket:
            socket.send_json({"subscribe": ["Synthetic/sine", "Synthetic/step"]})
            while True:
                message = socket.receive_json()
                if message["method"] == "run.tail":
                    tails.append(message["params"])
                if message["method"] == "run.done":
                    break

        t = np.linspace(0.0, duration, rows)
        assert tails, "the late subscriber received the run"
        first = tails[0]
        assert first["ids"] == ["Synthetic/sine", "Synthetic/step"]
        assert first["t0"] == 0.0, "the backlog starts at the first recorded row"
        assert first["t1"] == pytest.approx(float(t[pause_after - 1])), (
            "the backlog was sent while the run was paused, before new rows arrived"
        )
        assert len(first["time"]) > 0
        assert len(first["values"]) == 2

        times = np.concatenate([np.asarray(tail["time"]) for tail in tails])
        assert np.all(np.diff(times) >= 0.0), "tails follow each other without going back"
        assert tails[-1]["t1"] == pytest.approx(duration), "the final tail reaches t_end"
        sine = np.concatenate([np.asarray(tail["values"][0]) for tail in tails])
        assert np.allclose(sine, np.sin(2.0 * np.pi * times), atol=1e-12)
