"""The example runner's ``fft_peak``, ``period`` and ``energy`` checks.

``examples/run_checks.py`` is an inline ``uv`` script, not an installed module, so
the tests load it by path.  The spectral helper is checked against synthetic
signals with a known frequency; the check wrappers get a fake ``Run`` and the
real ``Report``, so a PASS/FAIL line and its tolerance are exercised without a
worker, a backend or a run file.  The energy cases use a synthetic planar
pendulum with an exactly constant budget (and a drifting one for the failure).
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


# --------------------------------------------------------------------- period


def test_period_check_measures_two_consecutive_crossings(runner):
    time = np.arange(0.0, 3.0, 1e-3)
    run = _run(time, np.sin(2.0 * np.pi * 2.0 * time))
    good = {
        "kind": "period", "signal": "sig", "direction": "up", "n": 1,
        "value": 0.5, "rtol": 1e-6,
    }
    report = runner.Report()
    runner._period_check(report, "project", "model", run, good)
    assert report.checks == 1 and report.failures == 0

    report = runner.Report()
    runner._period_check(report, "project", "model", run, dict(good, value=0.4))
    assert report.checks == 1 and report.failures == 1

    report = runner.Report()
    runner._period_check(report, "project", "model", run, dict(good, n=99))
    assert report.checks == 1 and report.failures == 1


def test_period_check_rejects_bad_parameters(runner):
    time = np.arange(0.0, 1.0, 1e-3)
    run = _run(time, np.sin(2.0 * np.pi * 5.0 * time))
    for entry in (
        {"signal": "sig", "rtol": 0.05},                           # no value
        {"signal": "missing", "value": 0.2, "rtol": 0.05},         # no signal
        {"signal": "sig", "value": 0.2},                           # no tolerance
        {"signal": "sig", "value": 0.0, "rtol": 0.05},             # zero period
        {"signal": "sig", "value": 0.2, "rtol": 0.05, "direction": "left"},
        {"signal": "sig", "value": 0.2, "rtol": 0.05, "n": 0},
    ):
        report = runner.Report()
        runner._period_check(report, "project", "model", run, entry)
        assert report.checks == 1 and report.failures == 1, entry


# --------------------------------------------------------------------- energy


def _pendulum_run(*, drift: float = 0.0):
    """A synthetic planar pendulum with an exactly constant total energy.

    ``q(t) = q0 cos(omega t)`` sets the potential; the speed is chosen from the
    energy budget, so ``KE + PE`` is constant to rounding.  ``drift`` scales the
    momenta linearly to give the failing case a real energy drift.
    """
    inertia, mass, length, gravity, q0 = 1e-4, 1.0, 0.5, 9.81, 0.01
    time = np.linspace(0.0, 10.0, 10001)
    q = q0 * np.cos(np.sqrt(mass * gravity * length / (inertia + mass * length**2)) * time)
    potential = -mass * gravity * length * np.cos(q)
    energy0 = -mass * gravity * length * np.cos(q0)
    speed = np.sqrt(
        2.0 * np.maximum(energy0 - potential, 0.0) / (inertia + mass * length**2)
    )
    factor = 1.0 + drift * time / time[-1]
    signals = {
        "Body/P[1]": inertia * speed * factor,
        "Body/P[2]": np.zeros_like(time),
        "Body/P[3]": mass * length * speed * factor,
        "Joint/qout": q,
        "Compose/g[3]": potential / (mass * gravity),
        "Joint/dout[1]": np.zeros_like(time),
        "Joint/dout[2]": np.zeros_like(time),
    }
    swing = mass * gravity * length * (1.0 - np.cos(q0))
    run = SimpleNamespace(model="pendulum", run_id="0" * 12, manifest={},
                          time=time, signals=signals)
    return run, swing


def _energy_entry(**overrides):
    entry = {
        "kind": "energy",
        "p": ["Body/P[1]", "Body/P[2]", "Body/P[3]"],
        "q": "Joint/qout",
        "pose": "Compose/g",          # the base id: the y component is used
        "d": ["Joint/dout[1]", "Joint/dout[2]"],
        "J": 1e-4, "m": 1.0, "L": 0.5, "g0": 9.81, "kt": 1e8,
        "q0": 0.01, "tol": 1e-6,
    }
    entry.update(overrides)
    return entry


def test_energy_check_passes_a_conservative_pendulum(runner):
    run, swing = _pendulum_run()
    report = runner.Report()
    runner._energy_check(report, "project", "pendulum-10s", run, _energy_entry())
    assert report.checks == 1 and report.failures == 0
    assert swing == pytest.approx(0.00024524795625688323)


def test_energy_check_fails_a_drifting_pendulum(runner):
    run, _ = _pendulum_run(drift=0.01)
    report = runner.Report()
    runner._energy_check(report, "project", "pendulum-10s", run, _energy_entry())
    assert report.checks == 1 and report.failures == 1


def test_energy_check_includes_the_spring_energy(runner):
    # A run whose total energy is constant only when 1/2 kt |d|^2 is counted:
    # q = 0, the pose cancels d2, d1 oscillates and the momenta carry E0 - spring.
    inertia, mass, stiffness, amplitude, omega = 1e-4, 1.0, 1e8, 1e-6, 10.0
    time = np.linspace(0.0, 0.5, 501)
    d1 = amplitude * np.sin(omega * time)
    spring = 0.5 * stiffness * d1**2
    ceiling = 0.5 * stiffness * amplitude**2
    speed = np.sqrt(2.0 * (ceiling - spring) / (inertia + mass * 0.5**2))
    signals = {
        "Body/P[1]": inertia * speed,
        "Body/P[2]": np.zeros_like(time),
        "Body/P[3]": mass * 0.5 * speed,
        "Joint/qout": np.zeros_like(time),
        "Compose/g[3]": np.zeros_like(time),
        "Joint/dout[1]": d1,
        "Joint/dout[2]": np.zeros_like(time),
    }
    run = SimpleNamespace(model="pendulum", run_id="0" * 12, manifest={},
                          time=time, signals=signals)
    report = runner.Report()
    runner._energy_check(report, "project", "pendulum", run,
                         _energy_entry(kt=stiffness))
    assert report.checks == 1 and report.failures == 0

    # The same signals without the spring term in the budget drift by 0.5 kt A^2.
    report = runner.Report()
    runner._energy_check(report, "project", "pendulum", run, _energy_entry(kt=0.0))
    assert report.checks == 1 and report.failures == 1


def test_energy_check_rejects_bad_parameters(runner):
    run, _ = _pendulum_run()
    for broken in (
        _energy_entry(pose="Compose/missing"),
        _energy_entry(d=["Joint/dout[1]", "Joint/missing"]),
        _energy_entry(p=["Body/P[1]", "Body/P[2]"]),
        _energy_entry(J=0.0),
        _energy_entry(tol=0.0),
        _energy_entry(q0=0.0),
    ):
        report = runner.Report()
        runner._energy_check(report, "project", "pendulum", run, broken)
        assert report.checks == 1 and report.failures == 1, broken

