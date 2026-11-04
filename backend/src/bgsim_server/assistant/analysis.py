"""Numbers from recorded signals, so the agent reasons on computed values, never on eyeballed
plots. Everything takes the time column and the value column(s) of a run."""

from __future__ import annotations

from typing import Any

import numpy as np


def _number(value: float) -> float | None:
    """JSON has no NaN or Inf: they become null."""
    number = float(value)
    return number if np.isfinite(number) else None


def _trapezoid(y: np.ndarray, t: np.ndarray) -> float:
    return float(np.sum(0.5 * (y[1:] + y[:-1]) * np.diff(t))) if y.size > 1 else 0.0


def signal_stats(time: np.ndarray, values: np.ndarray) -> dict[str, Any]:
    """Range, mean, RMS and time integral over the window, weighted by time, not by sample."""
    if values.size == 0:
        return {"samples": 0}
    finite = np.isfinite(values)
    result: dict[str, Any] = {"samples": int(values.size), "nonFinite": int(values.size - finite.sum())}
    if not finite.any():
        return result
    t, y = time[finite], values[finite]
    span = float(t[-1] - t[0])
    mean = _trapezoid(y, t) / span if span > 0 else float(y.mean())
    rms = np.sqrt(_trapezoid(y * y, t) / span) if span > 0 else np.sqrt(float((y * y).mean()))
    low, high = int(np.argmin(y)), int(np.argmax(y))
    result.update({
        "initial": _number(y[0]),
        "final": _number(y[-1]),
        "min": _number(y[low]),
        "tMin": _number(t[low]),
        "max": _number(y[high]),
        "tMax": _number(t[high]),
        "mean": _number(mean),
        "rms": _number(rms),
        "integral": _number(_trapezoid(y, t)),
    })
    return result


def step_metrics(
    time: np.ndarray, values: np.ndarray, target: float | None = None, band: float = 0.02
) -> dict[str, Any]:
    """Rise time (10-90 %), overshoot and settling time of a response from its first sample."""
    finite = np.isfinite(values)
    t, y = time[finite], values[finite]
    if y.size < 2:
        return {"error": "not enough finite samples"}
    start = float(y[0])
    end = float(y[-1]) if target is None else float(target)
    step = end - start
    result: dict[str, Any] = {"initial": start, "target": end, "final": float(y[-1])}
    result["steadyStateError"] = float(end - y[-1])
    if step == 0:
        result["note"] = "the response starts at its target: no step to measure"
        return result
    normal = (y - start) / step
    above_10 = np.nonzero(normal >= 0.1)[0]
    above_90 = np.nonzero(normal >= 0.9)[0]
    if above_10.size and above_90.size:
        result["riseTime"] = float(t[above_90[0]] - t[above_10[0]])
    else:
        result["riseTime"] = None
    peak = int(np.argmax(normal))
    result["overshootPercent"] = max(0.0, float(normal[peak] - 1.0) * 100.0)
    result["peak"] = float(y[peak])
    result["tPeak"] = float(t[peak])
    outside = np.nonzero(np.abs(normal - 1.0) > band)[0]
    if outside.size == 0:
        result["settlingTime"] = 0.0
    elif outside[-1] == y.size - 1:
        result["settlingTime"] = None
        result["note"] = f"not settled within {band:.0%} of the target by the end of the run"
    else:
        result["settlingTime"] = float(t[outside[-1] + 1] - t[0])
    result["band"] = band
    return result


def resample(time: np.ndarray, values: np.ndarray, points: int) -> tuple[np.ndarray, np.ndarray]:
    """Uniform samples over the window, for reading a curve's shape."""
    if time.size == 0:
        return time, values
    grid = np.linspace(time[0], time[-1], points)
    return grid, np.vstack([np.interp(grid, time, row) for row in values])


def compare(
    time_a: np.ndarray, a: np.ndarray, time_b: np.ndarray, b: np.ndarray
) -> dict[str, Any]:
    """The difference of two signals on the overlap of their time axes."""
    low, high = max(time_a[0], time_b[0]), min(time_a[-1], time_b[-1])
    if high < low:
        return {"error": "the runs do not overlap in time"}
    mask = (time_a >= low) & (time_a <= high)
    t = time_a[mask]
    difference = a[mask] - np.interp(t, time_b, b)
    index = int(np.argmax(np.abs(difference)))
    rms = np.sqrt(np.mean(difference * difference))
    scale = np.sqrt(np.mean(a[mask] * a[mask]))
    return {
        "rmsDifference": _number(rms),
        "relativeRms": _number(rms / scale) if scale > 0 else None,
        "maxDifference": _number(difference[index]),
        "tOfMax": _number(t[index]),
        "finalDifference": _number(difference[-1]),
    }
