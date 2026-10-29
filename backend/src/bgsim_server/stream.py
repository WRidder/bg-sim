"""The viewer stream (spec "Stream format"; plan 3.7; work package P5.1).

``WS /api/ws/stream/{run_id}`` (also mounted at ``/ws/stream/{run_id}``) serves the
spec's stream for a live or a finished run:

1. **Handshake**, one JSON text message, exactly the ``stream-handshake`` contract
   (validated against the generated ``StreamHandshake`` before it is sent)::

       {"signals": [{"id": "...", "unit": "..."}, ...], "rate": 60.0, "mode": "live"}

2. **Frames**, binary messages of little-endian ``Float64`` frames ``[t, v1 ... vn]`` in
   handshake order. One message holds one or more *whole* frames, so its length is a
   multiple of ``8 * (n + 1)``; a client splits it by that size. Frames arrive in time
   order, and the time gap between consecutive frames is at least ``1 / rate`` seconds
   of *simulation* time (the server decimates; a frame is always a recorded sample, the
   server never interpolates), so a stream carries at most ``rate`` (<= 60) frames per
   simulated second. The first and the last recorded row are always sent; only the gap
   before that final frame may be shorter.
3. **End.** The server closes the socket with code 1000 and the reason ``done``,
   ``cancelled`` or ``failed`` (the run status). An unknown run, a bad query or a
   run that cannot be followed closes with a 44xx code and a reason that says what
   to do (4400 bad query, 4404 unknown run, 4409 run not followable or not finished,
   4500 internal contract violation).

Query parameters:

* ``mode`` = ``live`` | ``playback`` (default: ``live`` while the run is running,
  else ``playback``). ``live`` on a run that already finished behaves as ``playback``
  and the handshake says so; ``playback`` on a running run is refused with 4409.
* ``ids`` = the signal subset. Repeat the parameter (``?ids=A/x&ids=A/y``) or comma
  separate (``?ids=A/x,A/y``); commas inside ``[i,j]`` indices are part of an id. The
  frame order is the request order, the default is every manifest signal in manifest
  order. This was chosen over a first client message so the handshake can be sent
  immediately and the contract stays exactly the handshake shape.
* ``rate`` = frames per simulated second, ``0 < rate <= 60`` (default 60). The
  handshake reports it.

Pacing. *Live*: the server follows ``stream.f64`` while the worker appends to it, never
blocking the simulation (it only reads), and sends at most one binary message per
``1 / rate`` wall seconds, each holding the new decimated frames since the last one
(a late joiner first gets the backlog from row 0). *Playback*: the decimated full run
is sent immediately in blocks of at most :data:`BLOCK_FRAMES` frames, without
wall-clock pacing; the web playback clock (W5.3) owns the timing, it needs the data,
not real-time delivery. Backpressure comes from the socket (each send is awaited).

Data access reads the run files with plain file reads (no memory maps), so a finished
run directory can still be deleted on Windows while a viewer is attached.
"""

from __future__ import annotations

import asyncio
import re
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from .contracts import StreamHandshake, StreamMode, StreamSignal
from .runs import _load_manifest, _locate, _RunState, _store_for

#: The display rate in frames per simulated second (the spec's default and the maximum).
MAX_RATE = 60.0
#: The largest number of frames in one binary message.
BLOCK_FRAMES = 2048
#: Rows read from a file per block while thinning.
_READ_ROWS = 65536

router = APIRouter()
#: The same endpoint without the ``/api`` prefix, as in the plan's API table.
alias_router = APIRouter()

_SUBSET_SPLIT = re.compile(r",(?![^\[]*\])")


class StreamRefused(Exception):
    """A request the stream cannot serve; carries the close code and reason."""

    def __init__(self, code: int, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


# --------------------------------------------------------------------------- query


def parse_ids(values: list[str]) -> list[str]:
    """The requested ids from repeated and/or comma separated ``ids`` parameters."""
    wanted: list[str] = []
    for value in values:
        wanted.extend(part.strip() for part in _SUBSET_SPLIT.split(value) if part.strip())
    return wanted


def _parse_rate(text: str | None) -> float:
    if text is None or not text.strip():
        return MAX_RATE
    try:
        rate = float(text)
    except ValueError:
        rate = float("nan")
    if not (0.0 < rate <= MAX_RATE):
        raise StreamRefused(
            4400, f"rate={text!r} is not allowed; use a number above 0 and at most {MAX_RATE:g}"
        )
    return rate


def _parse_mode(text: str | None) -> str | None:
    if text is None or not text.strip():
        return None
    if text not in {"live", "playback"}:
        raise StreamRefused(4400, f"mode={text!r} is not allowed; use mode=live or mode=playback")
    return text


# --------------------------------------------------------------------------- files


@dataclass
class RunFile:
    """Row access to ``columns.f64`` (column-major) or ``stream.f64`` (row-major)."""

    run_dir: Path
    n_signals: int
    prefer_columns: bool

    @property
    def width(self) -> int:
        return 1 + self.n_signals

    def _path(self) -> tuple[Path, bool] | None:
        columns = self.run_dir / "columns.f64"
        stream = self.run_dir / "stream.f64"
        order = [(columns, True), (stream, False)]
        if not self.prefer_columns:
            order.reverse()
        for path, is_columns in order:
            if path.is_file():
                return path, is_columns
        return None

    def rows(self) -> int:
        """The number of complete rows currently on disk."""
        found = self._path()
        if found is None:
            return 0
        try:
            return int(found[0].stat().st_size // (self.width * 8))
        except OSError:
            return 0

    def read(self, start: int, end: int, chosen: list[int]) -> np.ndarray:
        """Rows ``[start, end)`` as ``(k, 1 + len(chosen))`` ``[t, v...]`` Float64."""
        found = self._path()
        if found is None or end <= start:
            return np.empty((0, 1 + len(chosen)), dtype=np.float64)
        path, is_columns = found
        count = end - start
        width = self.width
        with path.open("rb") as handle:
            if is_columns:
                total = int(path.stat().st_size // (width * 8))
                out = np.empty((count, 1 + len(chosen)), dtype=np.float64)
                for slot, column in enumerate([0, *[c + 1 for c in chosen]]):
                    handle.seek((column * total + start) * 8)
                    out[:, slot] = np.fromfile(handle, dtype="<f8", count=count)
                return out
            handle.seek(start * width * 8)
            block = np.fromfile(handle, dtype="<f8", count=count * width).reshape(-1, width)
        return np.ascontiguousarray(block[:, [0, *[c + 1 for c in chosen]]], dtype=np.float64)


class Thinner:
    """Keeps rows whose time is at least ``1 / rate`` after the previously kept row."""

    def __init__(self, rate: float):
        # A tiny tolerance so t = k / rate grids are not lost to rounding.
        self.gap = 1.0 / rate * (1.0 - 1e-9)
        self.last_sent: float | None = None
        self.last_row: np.ndarray | None = None

    def pick(self, block: np.ndarray) -> np.ndarray:
        """The kept rows of ``block`` (time ordered), updating the cursor."""
        if block.shape[0] == 0:
            return block
        time_column = block[:, 0]
        indices: list[int] = []
        index = 0
        count = block.shape[0]
        if self.last_sent is None:
            indices.append(0)
            self.last_sent = float(time_column[0])
            index = 1
        while index < count:
            index = int(np.searchsorted(time_column, self.last_sent + self.gap, side="left"))
            if index >= count:
                break
            indices.append(index)
            self.last_sent = float(time_column[index])
            index += 1
        self.last_row = block[-1]
        return block[indices]

    def final_row(self) -> np.ndarray | None:
        """The last recorded row when it was not sent (so the run end is always sent)."""
        if self.last_row is None or self.last_sent is None:
            return None
        if float(self.last_row[0]) > self.last_sent:
            self.last_sent = float(self.last_row[0])
            return self.last_row[None, :]
        return None


async def _send_frames(websocket: WebSocket, frames: np.ndarray) -> None:
    """Send ``frames`` as binary messages of at most :data:`BLOCK_FRAMES` frames."""
    for begin in range(0, frames.shape[0], BLOCK_FRAMES):
        block = np.ascontiguousarray(frames[begin : begin + BLOCK_FRAMES], dtype="<f8")
        await websocket.send_bytes(block.tobytes())


# --------------------------------------------------------------------------- handshake


def _choose(signals: list[dict[str, Any]], wanted: list[str]) -> list[int]:
    if not wanted:
        return list(range(len(signals)))
    lookup = {str(signal["id"]): index for index, signal in enumerate(signals)}
    for name in wanted:
        if name not in lookup:
            known = ", ".join(repr(str(signal["id"])) for signal in signals[:6])
            raise StreamRefused(
                4400,
                f"unknown signal id {name!r}; this run records {known}"
                + (" ..." if len(signals) > 6 else ""),
            )
    return [lookup[name] for name in wanted]


def build_handshake(
    signals: list[dict[str, Any]], chosen: list[int], rate: float, mode: str
) -> dict[str, Any]:
    """The validated handshake document for the chosen signals."""
    try:
        handshake = StreamHandshake(
            signals=[
                StreamSignal(id=str(signals[i]["id"]), unit=signals[i].get("unit"))
                for i in chosen
            ],
            rate=rate,
            mode=StreamMode(mode),
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        raise StreamRefused(
            4500,
            "a signal id of this run does not fit the stream contract "
            f"({first.get('msg', 'invalid')}); rename the signal in the model",
        ) from None
    return handshake.model_dump(mode="json", by_alias=True, exclude_unset=True)


# --------------------------------------------------------------------------- serving


async def _wait_for_signals(state: _RunState, queue: asyncio.Queue) -> list[dict[str, Any]]:
    """The manifest signals of a live run, waiting for the worker to publish them."""
    while True:
        signals = list(state.manifest_document().get("signals") or [])
        if signals:
            return signals
        if state.done is not None:
            raise StreamRefused(
                4409, f"run {state.run_id!r} finished without recording signals; nothing to stream"
            )
        with suppress(TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=0.05)


async def _playback(
    websocket: WebSocket, run_dir: Path, signals: list[dict[str, Any]], chosen: list[int], rate: float
) -> None:
    data = RunFile(run_dir, len(signals), prefer_columns=True)
    total = data.rows()
    thinner = Thinner(rate)
    cursor = 0
    while cursor < total:
        end = min(total, cursor + _READ_ROWS)
        block = await asyncio.to_thread(data.read, cursor, end, chosen)
        cursor = end
        await _send_frames(websocket, thinner.pick(block))
    final = thinner.final_row()
    if final is not None:
        await _send_frames(websocket, final)


async def _live(
    websocket: WebSocket,
    state: _RunState,
    queue: asyncio.Queue,
    signals: list[dict[str, Any]],
    chosen: list[int],
    rate: float,
) -> None:
    interval = 1.0 / rate
    data = RunFile(state.run_dir, len(signals), prefer_columns=False)
    thinner = Thinner(rate)
    cursor = 0
    last_message = 0.0
    while True:
        finished = state.done is not None  # read before the rows: done follows the last write
        total = data.rows()
        if total > cursor:
            wait = last_message + interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
                continue
            end = min(total, cursor + _READ_ROWS)
            block = await asyncio.to_thread(data.read, cursor, end, chosen)
            cursor = end
            frames = thinner.pick(block)
            if frames.shape[0]:
                await _send_frames(websocket, frames)
                last_message = time.monotonic()
            continue
        if finished:
            final = thinner.final_row()
            if final is not None:
                await _send_frames(websocket, final)
            return
        with suppress(TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=interval)


def _end_reason(status: str) -> str:
    return status if status in {"done", "cancelled", "failed"} else "done"


async def _serve(websocket: WebSocket, run_id: str) -> tuple[int, str]:
    """Handshake and frames; returns the close ``(code, reason)``."""
    params = websocket.query_params
    try:
        rate = _parse_rate(params.get("rate"))
        mode = _parse_mode(params.get("mode"))
        wanted = parse_ids(params.getlist("ids"))
        try:
            run_dir, state = _locate(websocket, run_id)
        except HTTPException as exc:
            raise StreamRefused(4404, f"{exc.detail}; start a run first or check the run id") from None

        if state is None:
            document = _load_manifest(run_dir)
            if document.get("status") == "running":
                raise StreamRefused(
                    4409,
                    f"run {run_id!r} is not being followed by this backend (it was not started "
                    "here); wait for it to finish and use mode=playback",
                )
            signals = list(document.get("signals") or [])
            status = str(document.get("status"))
        elif state.done is not None:
            document = state.manifest_document()
            signals = list(document.get("signals") or [])
            status = str(state.done.get("status") or state.status)
        else:
            document = None
            signals = []
            status = "running"

        if status != "running":
            if not signals:
                raise StreamRefused(
                    4409, f"run {run_id!r} recorded no signals; nothing to stream"
                )
            chosen = _choose(signals, wanted)
            await websocket.send_json(build_handshake(signals, chosen, rate, "playback"))
            await _playback(websocket, run_dir, signals, chosen, rate)
            return 1000, _end_reason(status)

        # A running run, followed by this backend.
        assert state is not None
        if mode == "playback":
            raise StreamRefused(
                4409,
                f"run {run_id!r} is still running; use mode=live or wait until it has finished",
            )
        queue = _store_for(websocket.app).subscribe(state)
        try:
            signals = await _wait_for_signals(state, queue)
            chosen = _choose(signals, wanted)
            await websocket.send_json(build_handshake(signals, chosen, rate, "live"))
            await _live(websocket, state, queue, signals, chosen, rate)
        finally:
            _store_for(websocket.app).unsubscribe(state, queue)
        done = state.done or {}
        return 1000, _end_reason(str(done.get("status") or state.status))
    except StreamRefused as refusal:
        return refusal.code, refusal.reason
    except HTTPException as exc:
        return 4500, f"cannot read run {run_id!r}: {exc.detail}"


async def _watch_disconnect(websocket: WebSocket) -> None:
    """Return when the client goes away; messages from the client are ignored."""
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return


async def _serve_stream(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    server = asyncio.create_task(_serve(websocket, run_id), name=f"stream-{run_id}")
    watcher = asyncio.create_task(_watch_disconnect(websocket), name=f"stream-watch-{run_id}")
    try:
        await asyncio.wait({server, watcher}, return_when=asyncio.FIRST_COMPLETED)
        if not server.done():
            server.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await server
            return
        watcher.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await watcher
        try:
            code, reason = server.result()
        except (WebSocketDisconnect, RuntimeError):
            return  # the client left while frames were being sent
        with suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close(code=code, reason=reason[:120])
    finally:
        for task in (server, watcher):
            if not task.done():
                task.cancel()


@router.websocket("/ws/stream/{run_id}")
async def stream_socket(websocket: WebSocket, run_id: str) -> None:
    """Spec "Stream format": handshake JSON, then binary ``[t, v1 ... vn]`` frames."""
    await _serve_stream(websocket, run_id)


@alias_router.websocket("/ws/stream/{run_id}")
async def stream_socket_alias(websocket: WebSocket, run_id: str) -> None:
    await _serve_stream(websocket, run_id)
