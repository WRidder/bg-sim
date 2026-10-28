"""Julia worker supervision (plan sections 2.1, 3.6 and 6).

The backend listens on a random localhost TCP port, starts the Julia worker with
``BGSIM_PORT=<port>`` and the worker connects back. Every frame on the socket is

    u32 LE length | u8 kind | payload

where ``length`` counts the kind byte plus the payload bytes (so it is always at
least 1), and ``kind`` is 0 for a JSON message and 1 for binary. Requests are
``{"id", "method", "params"}``, responses ``{"id", "result"}`` or
``{"id", "error": {"message", "diagnostics"}}``, and notifications carry no ``id``.

The supervisor owns request/response correlation, the per-method timeouts
(``block.check`` 5 s, ``model.check`` 60 s, runs unlimited), a notification fan-out
with one :class:`asyncio.Queue` per run, the health state machine and auto-restart
with backoff.

``BGSIM_FAKE_WORKER=1`` replaces the Julia process with :class:`FakeWorker`: an
in-process stand-in that connects over a real socket and speaks the same framing,
answering ``ping``, ``catalog.get``, ``block.check`` and ``model.check`` from
``contracts/fixtures`` and writing a synthetic run (sines and steps, real timing)
for ``run.start``.
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
import os
import struct
import sys
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .config import BACKEND_VERSION, Settings

KIND_JSON = 0
KIND_BINARY = 1

# Per-method request timeouts of plan section 6: "block.check 5 s, model.check 60 s,
# runs unlimited". Everything else gets DEFAULT_TIMEOUT.
DEFAULT_TIMEOUT = 30.0
REQUEST_TIMEOUTS: dict[str, float | None] = {
    "block.check": 5.0,
    "model.check": 60.0,
    "run.start": None,
    "run.cancel": 10.0,
}

_RESTART_BASE_DELAY = 0.25
_RESTART_MAX_DELAY = 5.0
_READY_POLL_INTERVAL = 0.05

_DEFAULT_TIMEOUT = object()


# --------------------------------------------------------------------------- errors


class WorkerError(RuntimeError):
    """Base class for worker supervision errors."""


class WorkerNotReady(WorkerError):
    """The worker is not connected (or the connection just died)."""


class WorkerTimeout(WorkerError):
    """The worker did not answer within the per-method timeout."""


class WorkerProtocolError(WorkerError):
    """A malformed frame arrived from the worker."""


class WorkerRpcError(WorkerError):
    """The worker answered with ``{"error": {"message", "diagnostics"}}``."""

    def __init__(self, message: str, diagnostics: list[Any] | None = None):
        super().__init__(message)
        self.diagnostics: list[Any] = list(diagnostics or [])


# --------------------------------------------------------------------------- framing


def encode_frame(kind: int, payload: bytes) -> bytes:
    """One frame: ``u32 LE length`` (kind + payload), kind byte, payload."""
    if not 0 <= kind <= 0xFF:
        raise ValueError(f"frame kind out of range: {kind}")
    return struct.pack("<IB", len(payload) + 1, kind) + payload


async def read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes] | None:
    """Read one frame; ``None`` on a clean EOF before the header is complete."""
    try:
        header = await reader.readexactly(4)
    except asyncio.IncompleteReadError as exc:
        if exc.partial:
            raise WorkerProtocolError("truncated frame header") from exc
        return None
    (length,) = struct.unpack("<I", header)
    if length < 1:
        raise WorkerProtocolError(f"invalid frame length {length}")
    try:
        body = await reader.readexactly(length)
    except asyncio.IncompleteReadError as exc:
        raise WorkerProtocolError("truncated frame payload") from exc
    return body[0], bytes(body[1:])


# --------------------------------------------------------------------------- launchers


class WorkerLauncher(Protocol):
    """What the supervisor needs from a worker: start, stop and liveness."""

    @property
    def alive(self) -> bool: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class JuliaWorker:
    """The real worker process (plan section 6).

    Spawns ``julia --project=<repo>/julia/BGSim --threads=2 -e "using BGSim;
    BGSim.Worker.main()"`` with ``BGSIM_PORT`` set, capturing stdout/stderr into the
    worker log (they are never protocol).
    """

    def __init__(self, settings: Settings, port: int):
        self.settings = settings
        self.port = port
        self._proc: asyncio.subprocess.Process | None = None
        self._log = None

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        log_path = self.settings.worker_log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = log_path.open("ab")
        env = dict(os.environ)
        env["BGSIM_PORT"] = str(self.port)
        argv = [
            self.settings.julia,
            f"--project={self.settings.julia_project}",
            "--threads=2",
            "-e",
            "using BGSim; BGSim.Worker.main()",
        ]
        self._log.write(
            f"\n=== {_utc_now()} starting: {' '.join(argv)} (BGSIM_PORT={self.port})\n".encode()
        )
        self._log.flush()
        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(self.settings.repo_root),
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=self._log,
            stderr=self._log,
        )

    async def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None and proc.returncode is None:
            with suppress(ProcessLookupError):
                proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 10.0)
            except TimeoutError:
                with suppress(ProcessLookupError):
                    proc.kill()
                with suppress(Exception):
                    await proc.wait()
        if self._log is not None:
            self._log.close()
            self._log = None


_SYNTHETIC_SIGNALS = [
    {"id": "Synthetic/sine", "unit": "V", "kind": "output", "path": "Synthetic", "type": "Real"},
    {"id": "Synthetic/step", "unit": "V", "kind": "output", "path": "Synthetic", "type": "Real"},
    {
        "id": "Synthetic/counter",
        "unit": None,
        "kind": "state",
        "path": "Synthetic",
        "type": "Int",
    },
    {
        "id": "Synthetic/flag",
        "unit": None,
        "kind": "algebraic",
        "path": "Synthetic",
        "type": "Bool",
    },
]

_DEFAULT_RUN_SETTINGS = {
    "t_start": 0.0,
    "t_end": 1.0,
    "solver": "auto",
    "reltol": 1e-6,
    "abstol": 1e-8,
    "max_step": None,
    "output": {"mode": "points", "points": 1001},
    "event_limit": 10000,
}


def _synthetic_columns() -> np.ndarray:
    """The fixture's five columns (time, sine, step, counter, flag), little-endian.

    The same formulas as ``contracts/fixtures/run-manifest/valid/run.synthetic/
    generate.py``, so the fake's runs match the contract fixture.
    """
    t = np.linspace(0.0, 1.0, 1001)
    sine = np.sin(2.0 * np.pi * t)
    step = np.where(t >= 0.25, 2.0, 0.0)
    counter = np.floor(t / 0.1)
    flag = np.where(t >= 0.5, 1.0, 0.0)
    return np.stack([t, sine, step, counter, flag]).astype("<f8")


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class _FakeError(Exception):
    """A method the fake cannot answer; turned into an error response."""


class FakeWorker:
    """Fixture-driven stand-in for the Julia worker (plan section 2.3, 6).

    It connects to the supervisor over a real socket and speaks the same framing, so
    the fake exercises the exact transport path of the Julia process. Runs write a
    synthetic ``stream.f64``/``columns.f64`` (sines and steps) with real timing and
    emit ``run.phase``/``run.progress``/``run.done`` notifications.
    """

    def __init__(self, settings: Settings, port: int):
        self.settings = settings
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._run_tasks: dict[str, asyncio.Task] = {}
        self._cancelled: set[str] = set()
        self._stopping = False

    @property
    def alive(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="fake-worker")

    async def stop(self) -> None:
        self._stopping = True
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
        for task in list(self._run_tasks.values()):
            task.cancel()
        self._run_tasks.clear()

    async def crash(self) -> None:
        """Drop the connection abruptly, as a crashing worker process would."""
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.close()

    async def _run(self) -> None:
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        except OSError as exc:
            print(f"[fake-worker] connect failed: {exc}", file=sys.stderr)
            return
        self._reader, self._writer = reader, writer
        try:
            while not self._stopping:
                frame = await read_frame(reader)
                if frame is None:
                    break
                kind, payload = frame
                if kind == KIND_BINARY:
                    print(
                        f"[fake-worker] ignoring binary frame ({len(payload)} bytes)",
                        file=sys.stderr,
                    )
                    continue
                await self._handle_message(payload)
        except (ConnectionError, OSError, WorkerProtocolError):
            pass
        finally:
            for task in list(self._run_tasks.values()):
                task.cancel()
            self._run_tasks.clear()

    async def _handle_message(self, payload: bytes) -> None:
        try:
            message = json.loads(payload)
        except ValueError:
            print("[fake-worker] ignoring malformed JSON frame", file=sys.stderr)
            return
        if not isinstance(message, dict):
            print("[fake-worker] ignoring frame that is not a JSON object", file=sys.stderr)
            return
        request_id = message.get("id")
        if request_id is None:
            print("[fake-worker] ignoring notification from the backend", file=sys.stderr)
            return
        method = message.get("method")
        params = message.get("params") or {}
        try:
            result = await self._dispatch(method, params)
        except _FakeError as exc:
            await self._send({"id": request_id, "error": {"message": str(exc), "diagnostics": []}})
            return
        await self._send({"id": request_id, "result": result})

    async def _dispatch(self, method: Any, params: dict[str, Any]) -> Any:
        if method == "ping":
            # The build stamp of this repository; the real worker reports pkgversion(BGSim).
            return {"version": BACKEND_VERSION, "julia": "fake", "warm": True}
        if method == "catalog.get":
            return self._load_fixture("catalog", "valid", "catalog.min.json")
        if method == "block.check":
            return {"diagnostics": [], "interface": None}
        if method == "model.check":
            return {
                "diagnostics": self._load_fixture(
                    "diagnostic", "valid", "diagnostics.sample.json"
                ),
                "domains": {},
                "causality": {},
                "frames": {},
                "unitFactors": {},
                "signals": [],
                "stats": {"states": 0, "equations": 0},
            }
        if method == "run.start":
            run_id = params.get("runId")
            run_dir = params.get("runDir")
            if not run_id or not run_dir:
                raise _FakeError("run.start needs runId and runDir")
            self._cancelled.discard(run_id)
            self._run_tasks[run_id] = asyncio.create_task(
                self._run_synthetic(run_id, params), name=f"fake-run-{run_id}"
            )
            return {"accepted": True}
        if method == "run.cancel":
            run_id = params.get("runId")
            task = self._run_tasks.get(run_id)
            if task is None or task.done():
                return {"ok": False}
            self._cancelled.add(run_id)
            return {"ok": True}
        if method == "cache.clear":
            return {"ok": True}
        raise _FakeError(f"method {method!r} is not implemented by the fake worker")

    def _load_fixture(self, *parts: str) -> Any:
        path = self.settings.repo_root / "contracts" / "fixtures"
        for part in parts:
            path = path / part
        return json.loads(path.read_text(encoding="utf-8"))

    async def _run_synthetic(self, run_id: str, params: dict[str, Any]) -> None:
        """Write a synthetic run (real timing) and send the run notifications."""
        run_dir = Path(params["runDir"])
        run_dir.mkdir(parents=True, exist_ok=True)
        model = params.get("model") if isinstance(params.get("model"), dict) else {}
        data = _synthetic_columns()
        n = data.shape[1]
        t = data[0]
        started = time.perf_counter()
        status = "done"
        await self._notify("run.phase", {"runId": run_id, "phase": "simulate", "t_s": 0.0})
        rows = 0
        try:
            with (run_dir / "stream.f64").open("wb") as stream:
                chunk = max(1, n // 10)  # 10 progress notifications over ~1 s of wall time
                for begin in range(0, n, chunk):
                    end = min(n, begin + chunk)
                    np.ascontiguousarray(data[:, begin:end].T).tofile(stream)
                    stream.flush()
                    rows = end
                    await self._notify(
                        "run.progress",
                        {"runId": run_id, "t": float(t[end - 1]), "rows": rows},
                    )
                    if run_id in self._cancelled:
                        status = "cancelled"
                        break
                    delay = (float(t[end - 1]) - float(t[0])) - (time.perf_counter() - started)
                    if delay > 0:
                        await asyncio.sleep(delay)
            np.ascontiguousarray(data[:, :rows]).tofile(run_dir / "columns.f64")
            await self._notify(
                "run.phase", {"runId": run_id, "phase": "write", "t_s": float(t[rows - 1])}
            )
            stats = {
                "compile_s": 0.0,
                "sim_s": round(time.perf_counter() - started, 3),
                "steps": max(rows - 1, 0),
                "events": 2,
                "states": 2,
                "equations": 7,
            }
            manifest = {
                "id": run_id,
                "model": str(model.get("name") or "SyntheticSignals"),
                "modelHash": hashlib.sha256(
                    json.dumps(model, sort_keys=True).encode("utf-8")
                ).hexdigest(),
                "created": _utc_now(),
                "status": status,
                "settings": model.get("settings") or _DEFAULT_RUN_SETTINGS,
                "stats": stats,
                "signals": _SYNTHETIC_SIGNALS,
                "time": {"n": rows, "t0": float(t[0]), "t1": float(t[rows - 1])},
                "diagnostics": [],
                "layout": "columnar-f64-v1",
            }
            temp = run_dir / "manifest.json.tmp"
            temp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            os.replace(temp, run_dir / "manifest.json")
        except Exception as exc:  # noqa: BLE001 - keep the fake alive; report like the worker
            status = "failed"
            stats = {
                "compile_s": 0.0,
                "sim_s": round(time.perf_counter() - started, 3),
                "steps": 0,
                "events": 0,
                "states": 0,
                "equations": 0,
            }
            print(f"[fake-worker] run {run_id} failed: {exc}", file=sys.stderr)
        finally:
            self._run_tasks.pop(run_id, None)
            self._cancelled.discard(run_id)
        await self._notify(
            "run.done",
            {"runId": run_id, "status": status, "stats": stats, "diagnostics": []},
        )

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._send({"method": method, "params": params})

    async def _send(self, message: dict[str, Any]) -> None:
        writer = self._writer
        if writer is None:
            return
        payload = json.dumps(message).encode("utf-8")
        try:
            writer.write(encode_frame(KIND_JSON, payload))
            await writer.drain()
        except (ConnectionError, OSError):
            pass  # the supervisor is gone; nothing left to tell


# --------------------------------------------------------------------------- supervisor


@dataclass
class _PendingCall:
    method: str
    future: asyncio.Future


class WorkerSupervisor:
    """Owns the worker process (or the fake), the connection and the protocol."""

    def __init__(
        self,
        settings: Settings,
        worker_factory: Callable[[int], WorkerLauncher] | None = None,
    ):
        self.settings = settings
        self._worker_factory = worker_factory
        self._state = "starting"
        self._server: asyncio.Server | None = None
        self._port: int | None = None
        self._worker: WorkerLauncher | None = None
        self._client: asyncio.StreamWriter | None = None
        self._read_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None
        self._pending: dict[int, _PendingCall] = {}
        self._ids = itertools.count(1)
        self._run_queues: dict[str, list[asyncio.Queue]] = {}
        self._notification_queues: set[asyncio.Queue] = set()
        self._restart_attempt = 0
        self._stopping = False
        self._ready = asyncio.Event()
        self._julia_version: str | None = None
        self._spawned_at = 0.0

    # ------------------------------------------------------------------ properties

    @property
    def state(self) -> str:
        """``starting`` | ``warming`` | ``ready`` | ``crashed`` (plan 3.7)."""
        return self._state

    @property
    def julia_version(self) -> str | None:
        return self._julia_version

    @property
    def port(self) -> int | None:
        return self._port

    @property
    def worker(self) -> WorkerLauncher | None:
        return self._worker

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("the worker supervisor is already running")
        self._stopping = False
        self._server = await asyncio.start_server(self._on_connection, self.settings.host, 0)
        sockets = self._server.sockets or ()
        self._port = int(sockets[0].getsockname()[1])
        if self._worker_factory is not None:
            self._worker = self._worker_factory(self._port)
        elif self.settings.fake_worker:
            self._worker = FakeWorker(self.settings, self._port)
        else:
            self._worker = JuliaWorker(self.settings, self._port)
        await self._spawn()
        self._monitor_task = asyncio.create_task(self._monitor_loop(), name="worker-monitor")

    async def stop(self) -> None:
        self._stopping = True
        self._ready.clear()
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._monitor_task
            self._monitor_task = None
        await self._drop_client("supervisor is stopping", crashed=False)
        if self._read_task is not None:
            with suppress(Exception):
                await asyncio.wait_for(self._read_task, 2.0)
            self._read_task = None
        if self._server is not None:
            self._server.close()
            with suppress(Exception):
                await self._server.wait_closed()
            self._server = None
        if self._worker is not None:
            with suppress(Exception):
                await self._worker.stop()
            self._worker = None

    async def _spawn(self) -> None:
        if self._worker is None:
            return
        await self._worker.start()
        self._spawned_at = time.perf_counter()

    async def wait_ready(self, timeout: float = 30.0) -> None:
        """Wait until the worker has connected and answered a warm ``ping``."""
        try:
            await asyncio.wait_for(self._ready.wait(), timeout)
        except TimeoutError:
            raise WorkerTimeout(
                f"the worker did not become ready within {timeout:g} s (state {self._state})"
            ) from None

    # ------------------------------------------------------------------ requests

    async def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None | object = _DEFAULT_TIMEOUT,
    ) -> Any:
        """Send one request and await its result (or raise :class:`WorkerError`)."""
        if timeout is _DEFAULT_TIMEOUT:
            timeout = REQUEST_TIMEOUTS.get(method, DEFAULT_TIMEOUT)
        writer = self._client
        if writer is None:
            raise WorkerNotReady(f"the worker is not connected (state {self._state})")
        request_id = next(self._ids)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = _PendingCall(method=method, future=future)
        payload = json.dumps(
            {"id": request_id, "method": method, "params": params if params is not None else {}}
        ).encode("utf-8")
        try:
            writer.write(encode_frame(KIND_JSON, payload))
            await writer.drain()
        except (ConnectionError, OSError) as exc:
            self._pending.pop(request_id, None)
            raise WorkerNotReady(f"could not send {method}: {exc}") from exc
        if timeout is None:
            return await future
        try:
            return await asyncio.wait_for(future, timeout)
        except TimeoutError:
            self._pending.pop(request_id, None)
            raise WorkerTimeout(
                f"{method} did not answer within {timeout:g} s"
            ) from None

    async def send_binary(self, payload: bytes) -> None:
        """Send a raw binary frame (no correlation); the worker must tolerate it."""
        writer = self._client
        if writer is None:
            raise WorkerNotReady(f"the worker is not connected (state {self._state})")
        writer.write(encode_frame(KIND_BINARY, payload))
        await writer.drain()

    # ------------------------------------------------------------------ notifications

    def subscribe(self, run_id: str) -> asyncio.Queue:
        """One queue per subscriber for the notifications of ``run_id``."""
        queue: asyncio.Queue = asyncio.Queue()
        self._run_queues.setdefault(run_id, []).append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        queues = self._run_queues.get(run_id)
        if queues and queue in queues:
            queues.remove(queue)
            if not queues:
                self._run_queues.pop(run_id, None)

    def subscribe_notifications(self) -> asyncio.Queue:
        """One queue per subscriber for notifications without a ``runId``."""
        queue: asyncio.Queue = asyncio.Queue()
        self._notification_queues.add(queue)
        return queue

    def unsubscribe_notifications(self, queue: asyncio.Queue) -> None:
        self._notification_queues.discard(queue)

    def _route_notification(self, method: str, params: dict[str, Any]) -> None:
        run_id = params.get("runId") if isinstance(params, dict) else None
        if isinstance(run_id, str):
            queues = list(self._run_queues.get(run_id, ()))
        else:
            queues = list(self._notification_queues)
        message = {"method": method, "params": params}
        for queue in queues:
            queue.put_nowait(message)

    def _emit_notification(self, method: str, params: dict[str, Any]) -> None:
        self._route_notification(method, params)

    # ------------------------------------------------------------------ connection

    async def _on_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        if self._stopping:
            writer.close()
            return
        if self._client is not None:
            await self._drop_client("a new worker connection replaced the old one", crashed=False)
        self._client = writer
        self._ready.clear()
        self._state = "warming"
        self._read_task = asyncio.create_task(self._read_loop(reader, writer), name="worker-read")

    async def _read_loop(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                frame = await read_frame(reader)
                if frame is None:
                    break
                kind, payload = frame
                if kind == KIND_BINARY:
                    print(
                        f"[worker] ignoring binary frame ({len(payload)} bytes)", file=sys.stderr
                    )
                    continue
                try:
                    message = json.loads(payload)
                except ValueError as exc:
                    print(f"[worker] ignoring malformed JSON frame: {exc}", file=sys.stderr)
                    continue
                self._handle_message(message)
        except (ConnectionError, OSError) as exc:
            print(f"[worker] connection error: {exc}", file=sys.stderr)
        except WorkerProtocolError as exc:
            print(f"[worker] protocol error: {exc}", file=sys.stderr)
        finally:
            if self._client is writer:
                await self._drop_client("connection closed")

    def _handle_message(self, message: Any) -> None:
        if not isinstance(message, dict):
            print("[worker] ignoring frame that is not a JSON object", file=sys.stderr)
            return
        request_id = message.get("id")
        if request_id is not None:
            call = self._pending.pop(request_id, None)
            if call is None:
                print(f"[worker] response for unknown request id {request_id}", file=sys.stderr)
                return
            if call.future.done():
                return
            error = message.get("error")
            if error is not None:
                call.future.set_exception(
                    WorkerRpcError(
                        str(error.get("message", "worker error")),
                        error.get("diagnostics") or [],
                    )
                )
            else:
                call.future.set_result(message.get("result"))
            return
        method = message.get("method")
        if not isinstance(method, str):
            print("[worker] ignoring notification without a method", file=sys.stderr)
            return
        params = message.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        self._route_notification(method, params)

    async def _drop_client(self, reason: str, *, crashed: bool = True) -> None:
        writer, self._client = self._client, None
        self._ready.clear()
        if crashed and not self._stopping:
            self._state = "crashed"
        self._fail_pending(WorkerError(f"worker connection lost: {reason}"))
        if writer is not None:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    def _fail_pending(self, error: WorkerError) -> None:
        pending, self._pending = self._pending, {}
        for call in pending.values():
            if not call.future.done():
                call.future.set_exception(error)

    # ------------------------------------------------------------------ health and restart

    async def _monitor_loop(self) -> None:
        while True:
            try:
                await self._monitor_tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - the monitor must never die
                print(f"[worker] monitor error: {exc}", file=sys.stderr)
            await asyncio.sleep(_READY_POLL_INTERVAL)

    async def _monitor_tick(self) -> None:
        if self._stopping:
            return
        if self._client is not None:
            if self._state == "ready":
                return
            try:
                result = await self.call("ping", {}, timeout=5.0)
            except WorkerError as exc:
                await self._drop_client(f"ping failed: {exc}")
                return
            if isinstance(result, dict):
                if result.get("julia"):
                    self._julia_version = str(result["julia"])
                if result.get("warm"):
                    self._state = "ready"
                    self._restart_attempt = 0
                    self._ready.set()
                else:
                    self._state = "warming"
            return
        if self._worker is None or self._worker.alive:
            return
        await self._restart("the worker process is gone")

    async def _restart(self, reason: str) -> None:
        self._restart_attempt += 1
        attempt = self._restart_attempt
        delay = min(_RESTART_BASE_DELAY * (2 ** (attempt - 1)), _RESTART_MAX_DELAY)
        self._state = "crashed"
        self._ready.clear()
        self._emit_notification(
            "worker_restarted", {"attempt": attempt, "reason": reason}
        )
        print(
            f"[worker] restarting (attempt {attempt}) after {delay:g} s: {reason}",
            file=sys.stderr,
        )
        await asyncio.sleep(delay)
        if self._stopping:
            return
        if self._worker is not None:
            with suppress(Exception):
                await self._worker.stop()
        await self._spawn()
