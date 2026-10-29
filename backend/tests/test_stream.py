"""The viewer stream (P5.1): handshake, frame layout, decimation, playback and live."""

from __future__ import annotations

import json
import struct
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from test_run_tails import SyntheticRunWorker, _app, _make_project, _start, _wait_ready

from bgsim_server.app import create_app
from bgsim_server.contracts import StreamHandshake
from bgsim_server.stream import Thinner, parse_ids

REPO = Path(__file__).resolve().parents[2]
MANIFEST_FIXTURE = (
    REPO / "contracts" / "fixtures" / "run-manifest" / "valid" / "run.synthetic" / "manifest.json"
)


def _columns(n: int, duration: float) -> np.ndarray:
    t = np.linspace(0.0, duration, n)
    return np.vstack(
        (t, np.sin(2 * np.pi * t), np.where(t >= 0.5, 2.0, 0.0), np.floor(t * 10), t >= 0.25)
    ).astype("<f8")


def _make_run(
    settings,
    run_id: str,
    n: int = 1001,
    duration: float = 1.0,
    status: str = "done",
    layouts: tuple[str, ...] = ("columns", "stream"),
) -> np.ndarray:
    """A synthetic finished run in ``projects/demo/runs/<id>``; returns the columns."""
    run_dir = settings.projects_root / "demo" / "runs" / run_id
    run_dir.mkdir(parents=True)
    manifest = json.loads(MANIFEST_FIXTURE.read_text(encoding="utf-8"))
    manifest.update(id=run_id, status=status)
    manifest["time"] = {"n": n, "t0": 0.0, "t1": duration}
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    data = _columns(n, duration)
    if "columns" in layouts:
        data.tofile(run_dir / "columns.f64")
    if "stream" in layouts:
        np.ascontiguousarray(data.T).tofile(run_dir / "stream.f64")
    return data


def _read_all(socket) -> tuple[Any, list[bytes], int, str]:
    """``(handshake or None, binary messages, close code, reason)`` of one session."""
    handshake = None
    chunks: list[bytes] = []
    while True:
        message = socket.receive()
        if message["type"] == "websocket.close":
            return handshake, chunks, message["code"], message.get("reason") or ""
        if message.get("text") is not None:
            assert handshake is None, "the handshake is sent exactly once"
            handshake = json.loads(message["text"])
        else:
            chunks.append(message["bytes"])


def _frames(chunks: list[bytes], n_signals: int) -> np.ndarray:
    width = 1 + n_signals
    for chunk in chunks:
        assert len(chunk) % (8 * width) == 0, "a message holds whole frames"
    raw = b"".join(chunks)
    return np.frombuffer(raw, dtype="<f8").reshape(-1, width)


@pytest.fixture
def client(fake_settings):
    with TestClient(create_app(fake_settings)) as test_client:
        yield test_client


def _stream(client: TestClient, run_id: str, query: str = "", prefix: str = "/api"):
    with client.websocket_connect(f"{prefix}/ws/stream/{run_id}{query}") as socket:
        return _read_all(socket)


def _wait_finished(client: TestClient, run_id: str) -> None:
    deadline = time.monotonic() + 10
    while client.get(f"/api/runs/{run_id}").json()["status"] == "running":
        assert time.monotonic() < deadline, "the run did not finish"
        time.sleep(0.02)


# --------------------------------------------------------------------------- pure helpers


def test_ids_split_on_commas_outside_brackets() -> None:
    assert parse_ids(["A/x,A/y"]) == ["A/x", "A/y"]
    assert parse_ids(["A/m[1,2]", "A/z"]) == ["A/m[1,2]", "A/z"]
    assert parse_ids(["A/m[1,2],A/n[3]"]) == ["A/m[1,2]", "A/n[3]"]
    assert parse_ids([""]) == []


def test_thinner_keeps_the_spacing_across_blocks() -> None:
    thinner = Thinner(10.0)
    t = np.arange(0.0, 0.955, 0.01)
    block = np.column_stack((t, t * 2))
    kept = np.vstack([thinner.pick(block[:37]), thinner.pick(block[37:])])
    assert kept[0, 0] == 0.0
    assert np.all(np.diff(kept[:, 0]) >= 0.1 * (1 - 1e-6))
    assert len(kept) == 10  # 0.0, 0.1, ... 0.9; the last row is added by final_row
    final = thinner.final_row()
    assert final is not None
    assert final[0, 0] == pytest.approx(0.95)


# --------------------------------------------------------------------------- playback


def test_playback_handshake_matches_the_contract(client, fake_settings, schema_validate) -> None:
    _make_run(fake_settings, "run-a")
    handshake, chunks, code, reason = _stream(client, "run-a")
    schema_validate("stream-handshake", handshake)
    StreamHandshake.model_validate(handshake)
    assert handshake == {
        "signals": [
            {"id": "Synthetic/sine", "unit": "V"},
            {"id": "Synthetic/step", "unit": "V"},
            {"id": "Synthetic/counter", "unit": None},
            {"id": "Synthetic/flag", "unit": None},
        ],
        "rate": 60.0,
        "mode": "playback",
    }
    assert chunks
    assert (code, reason) == (1000, "done")


def test_frame_layout_order_and_values(client, fake_settings) -> None:
    data = _make_run(fake_settings, "run-a")
    handshake, chunks, _, _ = _stream(client, "run-a")
    frames = _frames(chunks, len(handshake["signals"]))
    # little-endian Float64: check the raw bytes of the first frame by hand
    first = struct.unpack_from("<5d", chunks[0], 0)
    assert first == tuple(data[:, 0])
    # every frame is an unmodified recorded row: [t, v1 ... vn] in handshake order
    rows = {float(t): data[:, i] for i, t in enumerate(data[0])}
    for frame in frames:
        assert np.array_equal(frame, rows[float(frame[0])])
    assert frames[0, 0] == 0.0
    assert frames[-1, 0] == 1.0
    assert np.all(np.diff(frames[:, 0]) > 0)


def test_subset_order_follows_the_request(client, fake_settings) -> None:
    data = _make_run(fake_settings, "run-a")
    for query in (
        "?ids=Synthetic/step&ids=Synthetic/sine",
        "?ids=Synthetic/step,Synthetic/sine",
    ):
        handshake, chunks, code, _ = _stream(client, "run-a", query)
        assert [s["id"] for s in handshake["signals"]] == ["Synthetic/step", "Synthetic/sine"]
        frames = _frames(chunks, 2)
        rows = {float(t): (data[2, i], data[1, i]) for i, t in enumerate(data[0])}
        for frame in frames:
            assert (frame[1], frame[2]) == rows[float(frame[0])]
        assert code == 1000


def test_decimation_is_at_most_60_hz_of_simulation_time(client, fake_settings) -> None:
    # 10 s of simulation recorded at 1 kHz (10001 rows) -> at most 60 frames per second.
    _make_run(fake_settings, "run-fast", n=10001, duration=10.0)
    handshake, chunks, _, _ = _stream(client, "run-fast")
    frames = _frames(chunks, 4)
    assert handshake["rate"] == 60.0
    assert len(frames) <= 60 * 10 + 1
    assert len(frames) > 500, "the decimation keeps close to 60 Hz, not far fewer"
    assert np.min(np.diff(frames[:-1, 0])) >= 1 / 60 * (1 - 1e-6)  # the last gap may be shorter
    # every 1 s window of simulation time holds at most 60 frames
    for start in frames[:, 0]:
        assert np.count_nonzero((frames[:, 0] >= start) & (frames[:, 0] < start + 1.0)) <= 60
    assert frames[-1, 0] == 10.0, "the final sample is always sent"
    # a lower requested rate decimates further and is reported in the handshake
    handshake, chunks, _, _ = _stream(client, "run-fast", "?rate=10")
    slow = _frames(chunks, 4)
    assert handshake["rate"] == 10.0
    assert len(slow) <= 101
    assert np.min(np.diff(slow[:-1, 0])) >= 0.1 * (1 - 1e-6)


def test_sparse_runs_are_not_resampled(client, fake_settings) -> None:
    data = _make_run(fake_settings, "run-sparse", n=11, duration=10.0)  # 1 Hz
    _, chunks, _, _ = _stream(client, "run-sparse")
    assert np.array_equal(_frames(chunks, 4).T, data)


def test_stream_only_layout_gives_the_same_frames(client, fake_settings) -> None:
    _make_run(fake_settings, "run-c", n=3001, duration=3.0)
    _make_run(fake_settings, "run-s", n=3001, duration=3.0, layouts=("stream",))
    _, from_columns, _, _ = _stream(client, "run-c")
    _, from_stream, _, _ = _stream(client, "run-s")
    assert b"".join(from_columns) == b"".join(from_stream)


def test_unprefixed_alias_serves_the_same_stream(client, fake_settings) -> None:
    _make_run(fake_settings, "run-a")
    _, prefixed, _, _ = _stream(client, "run-a")
    _, alias, code, _ = _stream(client, "run-a", prefix="")
    assert b"".join(alias) == b"".join(prefixed)
    assert code == 1000


def test_failed_and_cancelled_runs_close_with_their_status(client, fake_settings) -> None:
    _make_run(fake_settings, "run-failed", n=101, status="failed")
    _make_run(fake_settings, "run-cancelled", n=101, status="cancelled")
    assert _stream(client, "run-failed")[2:] == (1000, "failed")
    assert _stream(client, "run-cancelled")[2:] == (1000, "cancelled")


@pytest.mark.parametrize(
    ("run_id", "query", "code", "hint"),
    [
        ("run-nope", "", 4404, "unknown run"),
        ("-bad", "", 4404, "unknown run"),
        ("run-a", "?ids=Synthetic/missing", 4400, "unknown signal id"),
        ("run-a", "?rate=61", 4400, "rate"),
        ("run-a", "?rate=0", 4400, "rate"),
        ("run-a", "?rate=fast", 4400, "rate"),
        ("run-a", "?mode=replay", 4400, "mode"),
    ],
)
def test_refusals_close_cleanly_with_a_reason(
    client, fake_settings, run_id, query, code, hint
) -> None:
    _make_run(fake_settings, "run-a")
    handshake, chunks, got, reason = _stream(client, run_id, query)
    assert handshake is None
    assert chunks == []
    assert got == code
    assert hint in reason


def test_playback_of_a_run_still_running_is_refused(fake_settings) -> None:
    _make_project(fake_settings)
    workers: list[SyntheticRunWorker] = []
    app = _app(fake_settings, workers, rows=401, duration=2.0, batch=20, interval=0.05)
    with TestClient(app) as client:
        _wait_ready(client)
        run_id = _start(client, 2.0)
        _, _, code, reason = _stream(client, run_id, "?mode=playback")
        assert code == 4409
        assert "still running" in reason


def test_stream_of_a_run_made_by_the_fake_worker(client, fake_settings) -> None:
    _make_project(fake_settings)
    run_id = _start(client, 1.0)
    _wait_finished(client, run_id)
    handshake, chunks, code, reason = _stream(client, run_id)
    frames = _frames(chunks, len(handshake["signals"]))
    assert handshake["mode"] == "playback"
    assert (code, reason) == (1000, "done")
    assert len(frames) > 1
    assert np.all(np.diff(frames[:-1, 0]) >= 1 / 60 * (1 - 1e-6))


# --------------------------------------------------------------------------- live


def test_live_follows_a_growing_run_and_closes_on_done(fake_settings) -> None:
    _make_project(fake_settings)
    workers: list[SyntheticRunWorker] = []
    # 2 s of simulation, written in 20 batches over about 1 s of wall time
    app = _app(fake_settings, workers, rows=2001, duration=2.0, batch=100, interval=0.05)
    with TestClient(app) as client:
        _wait_ready(client)
        run_id = _start(client, 2.0)
        with client.websocket_connect(f"/api/ws/stream/{run_id}?mode=live") as socket:
            started = time.monotonic()
            handshake = json.loads(socket.receive_text())
            arrivals: list[float] = []
            chunks: list[bytes] = []
            while True:
                message = socket.receive()
                if message["type"] == "websocket.close":
                    code, reason = message["code"], message.get("reason")
                    break
                chunks.append(message["bytes"])
                arrivals.append(time.monotonic() - started)
        assert (code, reason) == (1000, "done")
        assert handshake["mode"] == "live"
        assert handshake["rate"] == 60.0
        assert handshake["signals"][0]["id"] == "Synthetic/sine"
        frames = _frames(chunks, len(handshake["signals"]))
        assert frames[0, 0] == 0.0
        assert frames[-1, 0] == 2.0, "the stream covers the whole run"
        assert np.min(np.diff(frames[:-1, 0])) >= 1 / 60 * (1 - 1e-6)
        assert len(frames) <= 60 * 2 + 1
        # the sine was recorded as sin(2 pi t); the frames are the recorded samples
        assert np.allclose(frames[:, 1], np.sin(2 * np.pi * frames[:, 0]))
        # frames followed the growing file: several messages spread over the run time
        assert len(chunks) >= 4, "live data arrived while the run was still writing"
        assert arrivals[-1] - arrivals[0] > 0.3
        # at most one message per 1/60 s of wall time
        assert len(chunks) <= 60 * (arrivals[-1] - arrivals[0]) + 2
        # the run is done now: a later "live" request replays it as playback
        late = _stream(client, run_id, "?mode=live")
        assert late[0]["mode"] == "playback"
        assert late[2:] == (1000, "done")
        assert b"".join(late[1]) == b"".join(chunks)


def test_live_ends_cleanly_when_the_run_is_cancelled(fake_settings) -> None:
    _make_project(fake_settings)
    workers: list[SyntheticRunWorker] = []
    app = _app(fake_settings, workers, rows=4001, duration=4.0, batch=40, interval=0.05)
    with TestClient(app) as client:
        _wait_ready(client)
        run_id = _start(client, 4.0)
        with client.websocket_connect(f"/api/ws/stream/{run_id}") as socket:
            json.loads(socket.receive_text())  # default mode is live for a running run
            socket.receive_bytes()
            assert client.delete(f"/api/runs/{run_id}").status_code == 200
            _, _, code, reason = _read_all(socket)
        assert (code, reason) == (1000, "cancelled")


def test_a_viewer_that_leaves_does_not_stop_the_run(fake_settings) -> None:
    _make_project(fake_settings)
    workers: list[SyntheticRunWorker] = []
    app = _app(fake_settings, workers, rows=401, duration=2.0, batch=20, interval=0.05)
    with TestClient(app) as client:
        _wait_ready(client)
        run_id = _start(client, 2.0)
        with client.websocket_connect(f"/api/ws/stream/{run_id}") as socket:
            json.loads(socket.receive_text())
        _wait_finished(client, run_id)
        assert client.get(f"/api/runs/{run_id}").json()["status"] == "done"
