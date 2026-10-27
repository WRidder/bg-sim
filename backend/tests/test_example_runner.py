"""The example runner's ``fft_peak`` check (plan 9.4 / X2.3 follow-up).

``examples/run_checks.py`` is an inline ``uv`` script, not an installed module, so
the tests load it by path.  The spectral helper is checked against synthetic
signals with a known frequency; the check wrapper gets a fake ``Run`` and the
real ``Report``, so a PASS/FAIL line and its tolerance are exercised without a
worker, a backend or a run file.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

RUNNER = Path(__file__).resolve().parents[2] / "examples" / "run_checks.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("bgsim_example_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return _load_runner()


def _run(time: np.ndarray, signal: np.ndarray):
    return SimpleNamespace(
        model="model",
        run_id="0" * 12,
        manifest={},
        time=time,
        signals={"sig": signal},
    )


def test_fft_peak_finds_a_known_sine(runner):
    time = np.arange(0.0, 2.0, 1e-3)
    signal = 0.4 + 0.25 * np.sin(2.0 * np.pi * 4.0 * time)
    samples, dt = runner._resample_window(time, signal)
    measured = runner._fft_peak_frequency(samples, dt)
    assert measured == pytest.approx(4.0, rel=5e-3)


def test_fft_peak_collapses_event_rows_and_resamples(runner):
    # Every event instant appears twice (left/right limits) and one row is missing,
    # so the raw grid is not uniform; the helper must still recover the frequency.
    time = np.arange(0.0, 2.0, 1e-3)
    keep = np.ones(time.size, dtype=bool)
    keep[500] = False
    time = np.concatenate([time[keep], [0.25, 0.75]])
    time.sort()
    signal = np.sin(2.0 * np.pi * 6.0 * time)
    samples, dt = runner._resample_window(time, signal)
    assert samples.size > 1000
    measured = runner._fft_peak_frequency(samples, dt)
    assert measured == pytest.approx(6.0, rel=5e-3)


def test_fft_peak_rejects_a_dc_only_window(runner):
    samples, dt = runner._resample_window(np.arange(0.0, 1.0, 1e-3), np.full(1000, 3.0))
    assert runner._fft_peak_frequency(samples, dt) is None
    assert runner._fft_peak_frequency(np.ones(3), 1e-3) is None


def test_fft_peak_highpass_removes_a_decay_envelope(runner):
    frequency, damping = 10.0, 8.0
    time = np.arange(0.0, 1.2, 1e-3)
    envelope = np.exp(-damping * time)
    signal = 0.2 + 0.1 * envelope * np.sin(2.0 * np.pi * frequency * time)
    samples, dt = runner._resample_window(time, signal)
    measured = runner._fft_peak_frequency(samples, dt, highpass_hz=4.0, min_hz=5.0)
    assert measured == pytest.approx(frequency, rel=0.03)


def test_fft_peak_check_passes_and_fails(runner):
    time = np.arange(0.0, 2.0, 1e-3)
    run = _run(time, np.sin(2.0 * np.pi * 5.0 * time))
    good = {
        "kind": "fft_peak", "signal": "sig", "value": 5.0, "rtol": 0.05,
        "from_t": 0.0, "to_t": 2.0,
    }
    report = runner.Report()
    runner._fft_peak_check(report, "project", "model", run, good)
    assert report.checks == 1 and report.failures == 0

    bad = dict(good, value=8.0)
    report = runner.Report()
    runner._fft_peak_check(report, "project", "model", run, bad)
    assert report.checks == 1 and report.failures == 1


def test_fft_peak_check_rejects_bad_parameters(runner):
    time = np.arange(0.0, 1.0, 1e-3)
    run = _run(time, np.sin(2.0 * np.pi * 5.0 * time))
    for entry in (
        {"signal": "sig", "rtol": 0.05},                            # no value
        {"signal": "missing", "value": 5.0, "rtol": 0.05},          # no signal
        {"signal": "sig", "value": 5.0},                            # no tolerance
        {"signal": "sig", "value": 5.0, "rtol": 0.05, "detrend": "cubic"},
        {"signal": "sig", "value": 5.0, "rtol": 0.05, "min_hz": 9.0, "max_hz": 2.0},
        {"signal": "sig", "value": 5.0, "rtol": 0.05, "highpass_hz": -1.0},
    ):
        report = runner.Report()
        runner._fft_peak_check(report, "project", "model", run, entry)
        assert report.checks == 1 and report.failures == 1, entry
