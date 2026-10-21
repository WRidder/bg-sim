"""Decimation and run-file tests (plan 3.5, 3.7 and 6).

The pure function is checked against a brute-force reference that recomputes
every bucket's minimum and maximum with plain array slicing. The run-file
reader is checked against the real contract fixture, not a mock, and the
performance test asserts the plan's target (1e7 points x 10 signals in under
50 ms) with ``time.perf_counter``.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import pytest

from bgsim_server.decimate import (
    Decimated,
    columns_rows,
    decimate,
    open_columns,
    open_stream,
)

FIXTURES = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"
SYNTHETIC_RUN = FIXTURES / "run-manifest" / "valid" / "run.synthetic"


def _buckets(t: np.ndarray, t0: float | None, t1: float | None, px: int):
    """The equal-count buckets of the implementation, computed independently."""
    i0 = int(np.searchsorted(t, t[0] if t0 is None else t0, side="left"))
    i1 = int(np.searchsorted(t, t[-1] if t1 is None else t1, side="right"))
    n = i1 - i0
    k = n // px
    for bucket in range(px):
        start = i0 + bucket * k
        stop = i0 + (bucket + 1) * k if bucket < px - 1 else i1
        yield start, stop


def _assert_envelopes(
    t: np.ndarray,
    values: np.ndarray,
    result: Decimated,
    t0: float | None,
    t1: float | None,
    px: int,
) -> None:
    """Every bucket of the result must span the original bucket's min/max."""
    for bucket, (start, stop) in enumerate(_buckets(t, t0, t1, px)):
        first_time = t[start]
        last_time = t[stop - 1]
        rows = (result.time >= first_time) & (result.time <= last_time)
        assert rows.any(), f"bucket {bucket} has no output rows"
        for signal in range(values.shape[0]):
            expected_min = values[signal, start:stop].min()
            expected_max = values[signal, start:stop].max()
            assert result.values[signal, rows].min() == expected_min, (
                f"bucket {bucket}, signal {signal}: minimum lost"
            )
            assert result.values[signal, rows].max() == expected_max, (
                f"bucket {bucket}, signal {signal}: maximum lost"
            )


# --------------------------------------------------------------------------- fixture files


def test_fixture_columns_and_stream_match_the_generated_layout() -> None:
    columns = open_columns(SYNTHETIC_RUN / "columns.f64", 4)
    stream = open_stream(SYNTHETIC_RUN / "stream.f64", 4)
    assert columns.shape == (5, 1001)
    assert stream.shape == (1001, 5)
    assert columns_rows(SYNTHETIC_RUN / "columns.f64", 4) == 1001
    numpy_columns = np.array(columns)
    numpy_stream = np.array(stream)
    assert np.array_equal(numpy_stream, numpy_columns.T), "stream is the row-major view"

    t = numpy_columns[0]
    assert np.allclose(numpy_columns[1], np.sin(2.0 * np.pi * t))
    assert numpy_columns[2][249] == 0.0 and numpy_columns[2][250] == 2.0
    assert numpy_columns[3][999] == 9.0 and numpy_columns[3][1000] == 10.0
    assert numpy_columns[4][499] == 0.0 and numpy_columns[4][500] == 1.0
    assert numpy_columns.dtype == np.float64 and numpy_columns.dtype.byteorder in "=<"


def test_run_files_reject_a_partial_row(tmp_path: Path) -> None:
    path = tmp_path / "columns.f64"
    path.write_bytes(b"\x00" * 8)
    with pytest.raises(ValueError, match="whole number"):
        open_columns(path, 1)
    path.write_bytes(b"\x00" * 16)
    assert columns_rows(path, 1) == 1
    path.write_bytes(b"\x00" * 32)
    with pytest.raises(ValueError, match="asked for 3 rows"):
        open_stream(path, 1, rows=3)


# --------------------------------------------------------------------------- pure decimation


def test_decimation_matches_a_brute_force_reference() -> None:
    rng = np.random.default_rng(20261021)
    n = 5000
    px = 97
    t = np.linspace(0.0, 1.0, n)
    values = rng.standard_normal((3, n))
    # Spikes, a slow drift and a constant signal exercise all comparisons.
    values[0, 1234] = 1.0e9
    values[1, 4321] = -1.0e9
    values[2] = np.linspace(-2.0, 2.0, n)

    result = decimate(t, values, px=px)

    assert result.time.ndim == 1 and result.values.shape == (3, result.n_points)
    assert result.n_points <= 2 * px + 2
    assert np.all(np.diff(result.time) >= 0.0), "time is non-decreasing"
    _assert_envelopes(t, values, result, None, None, px)

    # The first and last samples of the window are exact rows (plan 6).
    assert result.time[0] == t[0] and result.time[-1] == t[-1]
    assert np.array_equal(result.values[:, 0], values[:, 0])
    assert np.array_equal(result.values[:, -1], values[:, -1])


def test_every_injected_spike_survives_decimation() -> None:
    rng = np.random.default_rng(7)
    n = 10_000
    px = 50
    t = np.linspace(0.0, 10.0, n)
    values = rng.standard_normal((2, n))
    spikes = {}
    k = n // px
    for bucket in range(px):
        index = bucket * k + k // 2
        values[0, index] = 1.0e6 + bucket
        spikes[bucket] = values[0, index]

    result = decimate(t, values, px=px)
    for value in spikes.values():
        assert np.count_nonzero(result.values[0] == value) == 1, f"spike {value} was lost"
    assert result.values[0].max() == max(spikes.values())


def test_event_duplicate_is_preserved_and_not_split() -> None:
    n = 100
    px = 5
    t = np.linspace(0.0, 1.0, n)
    values = np.zeros((2, n))
    t[n // 2 + 1] = t[n // 2]  # the event instant, recorded twice
    values[0, n // 2] = 0.0
    values[0, n // 2 + 1] = 5.0  # a step
    values[1] = np.sin(t)

    result = decimate(t, values, px=px)
    event_time = t[n // 2]
    at_event = result.time == event_time
    assert np.count_nonzero(at_event) == 2, "both the left and right limits must remain"
    assert np.array_equal(result.values[0, at_event], np.array([0.0, 5.0]))
    assert result.n_points <= 2 * px + 2 + 2

    # A window of exactly the event instant keeps its two limits, even at px=0
    # and when the rest of the data would be decimated away.
    exact = decimate(t, values, t0=event_time, t1=event_time, px=0)
    assert exact.n_points == 2
    assert np.array_equal(exact.time, np.array([event_time, event_time]))
    assert np.array_equal(exact.values[0], np.array([0.0, 5.0]))


def test_a_duplicate_group_of_three_is_kept_whole() -> None:
    t = np.array([0.0, 1.0, 2.0, 2.0, 2.0, 3.0])
    values = np.array([[0.0, 1.0, 2.0, 3.0, 4.0, 5.0]])
    result = decimate(t, values, px=0)
    assert np.array_equal(result.time, t)
    result = decimate(t, values, t0=2.0, t1=2.0, px=1)
    assert np.array_equal(result.values[0], np.array([2.0, 3.0, 4.0]))


def test_window_clipping_and_px_zero() -> None:
    rng = np.random.default_rng(3)
    n = 2000
    t = np.linspace(0.0, 2.0, n)
    values = rng.standard_normal((2, n))

    raw = decimate(t, values, t0=0.5, t1=1.5, px=0)
    i0 = int(np.searchsorted(t, 0.5, side="left"))
    i1 = int(np.searchsorted(t, 1.5, side="right"))
    assert raw.n_points == i1 - i0
    assert np.array_equal(raw.time, t[i0:i1])
    assert np.array_equal(raw.values, values[:, i0:i1])

    windowed = decimate(t, values, t0=0.5, t1=1.5, px=40)
    assert windowed.time[0] == t[i0] and windowed.time[-1] == t[i1 - 1]
    assert np.all((windowed.time >= 0.5) & (windowed.time <= 1.5))
    _assert_envelopes(t, values, windowed, 0.5, 1.5, 40)

    # Fewer raw points than the budget: return them all, no synthetic rows.
    small = decimate(t[:100], values[:, :100], px=1600)
    assert small.n_points == 100


def test_irregular_time_grid_is_bucketed_by_sample_count() -> None:
    rng = np.random.default_rng(11)
    n = 3000
    t = np.sort(rng.uniform(0.0, 5.0, n))
    t[0], t[-1] = 0.0, 5.0
    values = np.vstack((np.sin(t), np.cos(3.0 * t), rng.standard_normal(n)))
    values[1, 2999] = 42.0

    result = decimate(t, values, px=33)
    assert result.n_points <= 2 * 33 + 2
    _assert_envelopes(t, values, result, None, None, 33)


def test_empty_window_and_invalid_inputs() -> None:
    t = np.linspace(0.0, 1.0, 10)
    values = np.zeros((2, 10))
    empty = decimate(t, values, t0=-5.0, t1=-1.0)
    assert empty.n_points == 0 and empty.values.shape == (2, 0)
    assert decimate(np.empty(0), np.empty((2, 0))).n_points == 0

    with pytest.raises(ValueError, match="one-dimensional"):
        decimate(np.zeros((2, 2)), values)
    with pytest.raises(ValueError, match="two-dimensional"):
        decimate(t, values[0])
    with pytest.raises(ValueError, match="samples"):
        decimate(t, np.zeros((2, 9)))
    with pytest.raises(ValueError, match="negative"):
        decimate(t, values, px=-1)
    with pytest.raises(ValueError, match="finite"):
        decimate(t, values, t0=float("nan"))
    with pytest.raises(ValueError, match="less than"):
        decimate(t, values, t0=0.8, t1=0.2)


# --------------------------------------------------------------------------- performance


@pytest.mark.skipif(
    os.environ.get("BGSIM_SKIP_PERF") == "1",
    reason="BGSIM_SKIP_PERF=1 skips the section 6 performance gate",
)
def test_performance_target_1e7_points_10_signals_under_50_ms() -> None:
    """Plan section 6: 1e7 points x 10 signals in under 50 ms (measured here)."""
    n = 10_000_000
    px = 1600
    rng = np.random.default_rng(0)
    t = np.linspace(0.0, 100.0, n)
    values = rng.standard_normal((10, n))

    decimate(t, values, px=px)  # warm the pool, the caches and the allocator
    timings = []
    for _ in range(3):
        started = time.perf_counter()
        result = decimate(t, values, px=px)
        timings.append(time.perf_counter() - started)
    timings.sort()
    print(
        f"\ndecimation 1e7 x 10 @ px={px}: "
        f"min {timings[0] * 1000:.2f} ms, median {timings[1] * 1000:.2f} ms, "
        f"max {timings[-1] * 1000:.2f} ms, {result.n_points} points"
    )
    assert result.n_points <= 2 * px + 2
    assert timings[1] < 0.050, f"median {timings[1] * 1000:.2f} ms exceeds the 50 ms target"
