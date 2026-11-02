"""XY plots: whole-row decimation and the ``exact`` live tail.

An XY plot pairs two signals sample by sample. The min/max decimation of a plot against time
keeps each signal's own extremes, so one of its rows can combine samples of different instants.
``decimate_rows`` selects whole recorded rows instead, and a run WebSocket subscription with
``"exact": true`` (the editor sends it while an XY plot is open) uses it for the live tail.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from test_run_tails import SyntheticRunWorker, _app, _make_project, _start, _wait_ready

from bgsim_server.decimate import decimate_rows


def test_decimate_rows_returns_a_small_window_unchanged() -> None:
    t = np.linspace(0.0, 1.0, 500)
    values = np.vstack([np.sin(t), np.cos(t)])
    result = decimate_rows(t, values, 500)
    assert np.array_equal(result.time, t)
    assert np.array_equal(result.values, values)


def test_decimate_rows_keeps_whole_rows_and_every_envelope() -> None:
    rng = np.random.default_rng(7)
    n = 50_000
    t = np.linspace(0.0, 10.0, n)
    t[20_000] = t[19_999]  # an event instant: left and right limit
    x = np.sin(2 * np.pi * t) + 0.01 * rng.standard_normal(n)
    y = np.cos(2 * np.pi * 3 * t) + 0.01 * rng.standard_normal(n)
    values = np.vstack([x, y])
    budget = 4000
    started = time.perf_counter()
    result = decimate_rows(t, values, budget)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    for column, instant in enumerate(result.time):
        candidates = np.flatnonzero(t == instant)
        assert any(
            x[c] == result.values[0, column] and y[c] == result.values[1, column] for c in candidates
        ), f"the row at t={instant} is not a recorded row"
    assert np.all(np.diff(result.time) >= 0.0)
    assert result.n_points <= budget + 4, "the budget holds, plus the exact first/last/event rows"
    assert result.values[0].min() == x.min() and result.values[0].max() == x.max()
    assert result.values[1].min() == y.min() and result.values[1].max() == y.max()
    assert result.time[0] == t[0] and result.time[-1] == t[-1]
    assert np.count_nonzero(result.time == t[19_999]) == 2, "both event limits are kept"
    print(f"\ndecimate_rows: {n} rows x 2 signals -> {result.n_points} rows in {elapsed_ms:.2f} ms")


def test_decimate_rows_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        decimate_rows(np.zeros(3), np.zeros((1, 4)), 10)
    with pytest.raises(ValueError):
        decimate_rows(np.zeros(3), np.zeros((1, 3)), 0)
    assert decimate_rows(np.zeros(0), np.zeros((2, 0)), 10).n_points == 0


def test_an_exact_subscription_receives_every_recorded_row(fake_settings) -> None:
    _make_project(fake_settings)
    workers: list[SyntheticRunWorker] = []
    rows = 1001
    duration = 1.0
    app = _app(fake_settings, workers, rows=rows, duration=duration, batch=50, interval=0.02)
    with TestClient(app) as client:
        _wait_ready(client)
        run_id = _start(client, duration)
        tails: list[dict[str, Any]] = []
        with client.websocket_connect(f"/api/ws/runs/{run_id}") as socket:
            socket.send_json({"subscribe": ["Synthetic/sine", "Synthetic/step"], "exact": True})
            while True:
                message = socket.receive_json()
                if message["method"] == "run.tail":
                    tails.append(message["params"])
                if message["method"] == "run.done":
                    break
    times = np.concatenate([np.asarray(tail["time"]) for tail in tails])
    sine = np.concatenate([np.asarray(tail["values"][0]) for tail in tails])
    assert times.size == rows, "every recorded row arrives once"
    assert np.allclose(times, np.linspace(0.0, duration, rows))
    assert np.allclose(sine, np.sin(2.0 * np.pi * times), atol=1e-12)
