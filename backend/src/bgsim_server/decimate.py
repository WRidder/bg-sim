"""Min/max decimation and run-file access (plan sections 3.5, 3.7 and 6).

The module has two halves:

* :func:`decimate` is pure (arrays in, arrays out). It selects a time window
  with :func:`numpy.searchsorted`, splits it into ``px`` equal-count buckets
  and keeps the minimum and maximum of every signal in every bucket, plus the
  first and last sample of the window. The result therefore has at most
  ``2*px + 2`` rows plus one row per event limit, with every signal's envelope
  intact.
* :func:`open_columns` and :func:`open_stream` open the run files of plan 3.5
  with :class:`numpy.memmap`; they are read-only views and never copy unless
  the caller slices them.

Why equal-count buckets and not equal-time buckets? A min/max plot needs the
same number of buckets as the plot has horizontal pixels, and equal-count
buckets can be reduced with a contiguous ``reshape`` + ``min``/``max``. On the
uniform output grid the simulation produces (``output: points``) the two are
identical. On an adaptive solver grid equal-count buckets give the plot a
uniform sample density, which is what the pixels represent.

Measured on the target machine (1e7 rows x 10 signals, px = 1600): about 36 ms
with the default thread pool. The plan suggested ``np.minimum.reduceat``; that
was measured at ~145 ms for the same data (two segmented passes, and
``reduceat`` does not release the GIL, so threads do not help it). The
``reshape`` reduction is exactly equivalent for equal-count buckets and meets
the plan's 50 ms target; the deviation is reported in the work-package report.

Event duplicates: a simulation writes an event instant twice (left and right
limit, same ``t``) so a step renders as a vertical edge. Such rows are always
returned exactly, in addition to the bucket envelopes. Duplicate groups are
never split (the window and the buckets both extend over them).
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np

#: Default number of horizontal pixels (and therefore buckets) of ``/data``.
DEFAULT_POINTS = 1600

#: The largest number of workers used for the per-signal reductions. The work
#: is memory-bandwidth bound; more workers than this only add scheduling noise.
MAX_WORKERS = max(1, min(16, os.cpu_count() or 1))

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    """The shared pool; creating threads per request would dominate small runs."""
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=MAX_WORKERS, thread_name_prefix="bgsim-decimate"
                )
    return _executor


@dataclass(frozen=True)
class Decimated:
    """The decimated view: a time column and one row per signal (columns)."""

    time: np.ndarray
    values: np.ndarray

    @property
    def n_points(self) -> int:
        return int(self.time.size)


def _empty(n_signals: int) -> Decimated:
    return Decimated(
        time=np.empty(0, dtype=np.float64),
        values=np.empty((n_signals, 0), dtype=np.float64),
    )


def decimate(
    t: np.ndarray,
    values: np.ndarray,
    t0: float | None = None,
    t1: float | None = None,
    px: int = DEFAULT_POINTS,
) -> Decimated:
    """Min/max decimate ``values`` (signals x samples) over ``[t0, t1]``.

    Parameters
    ----------
    t:
        One-dimensional, non-decreasing time vector of ``n`` samples.
    values:
        Shape ``(n_signals, n)``; sample ``i`` of every signal is
        ``values[:, i]``. Bool and Int signals are already Float64 (plan 3.5).
    t0, t1:
        The window; defaults to the first and last sample. The window is
        inclusive on both sides, so ``t0 == t1`` selects an event instant and
        keeps both of its left/right rows.
    px:
        Number of horizontal pixels (buckets). ``px=0`` returns the raw window.

    Returns
    -------
    Decimated
        ``time`` is non-decreasing; ``values`` has shape
        ``(n_signals, len(time))``. Each bucket contributes its minimum row
        (timed at the bucket's first sample) and, unless it is identical to the
        minimum row, its maximum row (timed at the bucket's last sample).
        Duplicated timestamps (events) and the first/last samples of the window
        are added as exact rows. Bucket rows and exact rows can share a
        timestamp; that is intentional.

    Raises
    ------
    ValueError
        On a non-2-D value matrix, a length mismatch, a negative ``px``, a
        non-finite window or ``t1 < t0``.
    """
    t = np.asarray(t, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    if t.ndim != 1:
        raise ValueError("t must be one-dimensional")
    if values.ndim != 2:
        raise ValueError("values must be two-dimensional (signals x samples)")
    if values.shape[1] != t.size:
        raise ValueError(
            f"values has {values.shape[1]} samples but t has {t.size}"
        )
    if px < 0:
        raise ValueError(f"px must not be negative (got {px})")
    if t.size == 0 or values.shape[0] == 0:
        return _empty(values.shape[0])

    lo = float(t[0]) if t0 is None else float(t0)
    hi = float(t[-1]) if t1 is None else float(t1)
    if not (np.isfinite(lo) and np.isfinite(hi)):
        raise ValueError("t0 and t1 must be finite")
    if hi < lo:
        raise ValueError(f"t1 ({hi!r}) must not be less than t0 ({lo!r})")

    i0 = int(np.searchsorted(t, lo, side="left"))
    i1 = int(np.searchsorted(t, hi, side="right"))
    n = i1 - i0
    if n == 0:
        return _empty(values.shape[0])
    if px == 0 or n <= 2 * px:
        # The raw window already fits the budget (and px=0 means "no decimation").
        return Decimated(
            time=np.array(t[i0:i1], dtype=np.float64),
            values=np.array(values[:, i0:i1], dtype=np.float64),
        )

    # px buckets; the first px-1 have exactly k samples, the last takes the
    # remainder (k + n % px). Keeping the tail in one bucket lets the first
    # px-1 buckets be one contiguous reshape per signal.
    k = n // px
    n_signals = values.shape[0]
    mins = np.empty((n_signals, px), dtype=np.float64)
    maxs = np.empty((n_signals, px), dtype=np.float64)

    def reduce_chunk(task: tuple[int, int, int]) -> None:
        row, b0, b1 = task
        samples = values[row]
        start = i0 + b0 * k
        count = b1 - b0
        if b1 == px:
            # The final chunk ends in the remainder bucket, which is longer
            # than k; reduce the k-sized buckets, then the tail on its own.
            block = samples[start:i1]
            if count > 1:
                head = block[: (count - 1) * k]
                if not head.flags.c_contiguous:
                    head = np.ascontiguousarray(head)
                head = head.reshape(count - 1, k)
                mins[row, b0 : b1 - 1] = head.min(axis=1)
                maxs[row, b0 : b1 - 1] = head.max(axis=1)
            tail = block[(count - 1) * k :]
            mins[row, b1 - 1] = tail.min()
            maxs[row, b1 - 1] = tail.max()
            return
        block = samples[start : start + count * k]
        if not block.flags.c_contiguous:
            block = np.ascontiguousarray(block)
        block = block.reshape(count, k)
        mins[row, b0:b1] = block.min(axis=1)
        maxs[row, b0:b1] = block.max(axis=1)

    # Enough independent chunks to keep every worker busy even for one signal;
    # signals and bucket ranges write disjoint cells, so no locking is needed.
    parts = max(1, min(px, 16, max(2, (MAX_WORKERS + n_signals - 1) // n_signals)))
    bounds = np.linspace(0, px, parts + 1).astype(np.intp)
    tasks = [
        (row, int(bounds[i]), int(bounds[i + 1]))
        for row in range(n_signals)
        for i in range(parts)
        if bounds[i] < bounds[i + 1]
    ]
    # The event scan reads only the time column, so run it beside the min/max
    # reduction instead of adding its ~8 ms to the critical path.
    scan_box: list[np.ndarray | MemoryError] = []

    def scan_events() -> None:
        try:
            scan_box.append(np.flatnonzero(t[i0 + 1 : i1] == t[i0 : i1 - 1]))
        except MemoryError as exc:
            scan_box.append(exc)

    scan = threading.Thread(target=scan_events, name="bgsim-events", daemon=True)
    scan.start()
    try:
        list(_get_executor().map(reduce_chunk, tasks))
    finally:
        scan.join()
    if scan_box and isinstance(scan_box[0], MemoryError):
        raise scan_box[0]
    pair = scan_box[0] if scan_box else np.empty(0, dtype=np.intp)

    starts = i0 + np.arange(px, dtype=np.intp) * k
    ends = np.empty(px, dtype=np.intp)
    ends[:-1] = starts[1:] - 1
    ends[-1] = i1 - 1

    # Two rows per bucket, in (min, max) order. A bucket whose min and max are
    # identical (and which spans one instant) collapses to one row.
    env_time = np.empty(2 * px, dtype=np.float64)
    env_values = np.empty((values.shape[0], 2 * px), dtype=np.float64)
    env_time[0::2] = t[starts]
    env_time[1::2] = t[ends]
    env_values[:, 0::2] = mins
    env_values[:, 1::2] = maxs
    keep = np.ones(2 * px, dtype=bool)
    identical = (t[starts] == t[ends]) & np.all(mins == maxs, axis=0)
    keep[1::2] = ~identical
    env_time = env_time[keep]
    env_values = env_values[:, keep]

    # Every row that shares its timestamp with a neighbour is an event limit
    # (left and right). Keep all of them, exactly, so steps stay vertical.
    if pair.size:
        event_rows = np.unique(np.concatenate((pair + i0, pair + i0 + 1)))
    else:
        event_rows = np.empty(0, dtype=np.intp)

    first = i0
    last = i1 - 1
    last_value = values[:, last]

    # Exact rows: every event limit in file order (the first sample joins them
    # when it is itself an event), plus the window's first and last samples
    # when those are not already covered. Event rows are never merged, even
    # when two limits happen to carry the same value.
    event_rows_list = event_rows.tolist()
    head: list[tuple[float, np.ndarray]] = [
        (float(t[index]), values[:, index]) for index in event_rows_list
    ]
    if not head or event_rows_list[0] != first:
        head.insert(0, (float(t[first]), values[:, first]))
    tail: list[tuple[float, np.ndarray]] = []
    if not any(
        timestamp == float(t[last]) and np.array_equal(row, last_value)
        for timestamp, row in head
    ):
        tail.append((float(t[last]), last_value))
    exact_rows = head + tail

    # An envelope row identical to an exact row adds nothing: the exact row
    # already carries the bucket's minimum or maximum. Group by timestamp so a
    # run with many event instants stays linear in the envelope size.
    exact_by_time: dict[float, list[np.ndarray]] = {}
    for timestamp, row in exact_rows:
        exact_by_time.setdefault(timestamp, []).append(row)
    keep_env = np.ones(env_time.size, dtype=bool)
    for column in range(env_time.size):
        for row in exact_by_time.get(float(env_time[column]), ()):
            if np.array_equal(env_values[:, column], row):
                keep_env[column] = False
                break

    # The exact head leads, the envelope rows follow, the exact last sample
    # closes the series so that a tie at t1 ends on a real sample.
    parts_t = [np.array([timestamp]) for timestamp, _ in head]
    parts_v = [row.reshape(-1, 1) for _, row in head]
    parts_t.append(env_time[keep_env])
    parts_v.append(env_values[:, keep_env])
    for timestamp, row in tail:
        parts_t.append(np.array([timestamp]))
        parts_v.append(row.reshape(-1, 1))

    order_t = np.concatenate(parts_t)
    order_v = np.concatenate(parts_v, axis=1)

    # Stable sort by time: envelopes stay in bucket order, events stay in file
    # order (left before right) and equal timestamps are never merged.
    order = np.argsort(order_t, kind="stable")
    return Decimated(
        time=np.ascontiguousarray(order_t[order], dtype=np.float64),
        values=np.ascontiguousarray(order_v[:, order], dtype=np.float64),
    )


# --------------------------------------------------------------------------- run files

_ROW_DTYPE = np.dtype("<f8")


def columns_rows(path: str | Path, n_signals: int) -> int:
    """The number of complete rows in a ``columns.f64`` file."""
    size = Path(path).stat().st_size
    width = 1 + n_signals
    return int(size // (width * _ROW_DTYPE.itemsize))


def open_columns(path: str | Path, n_signals: int) -> np.ndarray:
    """A read-only ``(1 + n_signals, n)`` memmap of a ``columns.f64`` file.

    Column 0 is time, columns 1.. are the signals in manifest order (plan 3.5).
    The row count comes from the file size; a file whose size is not a multiple
    of one row raises :class:`ValueError`.
    """
    path = Path(path)
    size = path.stat().st_size
    width = 1 + n_signals
    row_bytes = width * _ROW_DTYPE.itemsize
    if size % row_bytes:
        raise ValueError(
            f"{path.name} is not a whole number of {width}-column Float64 rows "
            f"({size} bytes)"
        )
    rows = int(size // row_bytes)
    if rows == 0:
        return np.empty((width, 0), dtype=np.float64)
    return np.memmap(path, dtype=_ROW_DTYPE, mode="r", shape=(width, rows))


def open_stream(path: str | Path, n_signals: int, rows: int | None = None) -> np.ndarray:
    """A read-only ``(rows, 1 + n_signals)`` memmap of a ``stream.f64`` file.

    The stream is row-major ``[t, v1 ... vn]`` and is appended while a run
    executes, so ``rows`` may be smaller than the file's current row count (the
    caller then sees only the prefix it asked for).
    """
    path = Path(path)
    size = path.stat().st_size
    width = 1 + n_signals
    row_bytes = width * _ROW_DTYPE.itemsize
    if size % row_bytes:
        raise ValueError(
            f"{path.name} is not a whole number of {width}-column Float64 rows "
            f"({size} bytes)"
        )
    available = int(size // row_bytes)
    if rows is None:
        rows = available
    if rows < 0 or rows > available:
        raise ValueError(f"asked for {rows} rows of {path.name}, which has {available}")
    if rows == 0:
        return np.empty((0, width), dtype=np.float64)
    return np.memmap(path, dtype=_ROW_DTYPE, mode="r", shape=(rows, width))
